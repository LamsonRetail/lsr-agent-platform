#!/usr/bin/env python3
"""lsr-agent adopt — đưa một agent ĐANG CHẠY ở dự án khác vào platform.

Chạy TRONG repo của agent đó. Không sửa code, không đổi cấu hình đang chạy:
  1. Dò cấu hình sẵn có (git remote, tên project, MCP servers trong .mcp.json).
  2. Sinh `lsr-agent.yaml` (deployment: external) — khai báo cho platform.
  3. Cài hook telemetry cho Claude Code (.claude/settings.json) — để platform
     nắm request/tool/token mà không đụng logic agent.
  4. Đăng ký với Platform API → nhận TELEMETRY_API_KEY, ghi `.env.lsr` (gitignored).

Chỉ dùng thư viện chuẩn. Dùng:
  python3 lsr_adopt.py --id AG-X --name "Tên" --owner you@lamsonretail.vn \\
      [--squad SQ-SALES] [--platform https://platform...] [--admin-token ...] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

TRACE_SCRIPT = ".lsr/lsr_trace.py"


def detect_repo_url(root: Path) -> str:
    try:
        out = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip()
    except Exception:
        return ""


def detect_project_name(root: Path) -> str:
    for f, key in ((root / "package.json", "name"), (root / "pyproject.toml", None)):
        if f.exists():
            try:
                if key:
                    return json.loads(f.read_text(encoding="utf-8")).get(key, "") or root.name
                m = re.search(r'(?m)^\s*name\s*=\s*"([^"]+)"', f.read_text(encoding="utf-8"))
                if m:
                    return m.group(1)
            except Exception:
                pass
    return root.name


def detect_mcp_skills(root: Path) -> list[str]:
    """Đọc MCP đang khai báo (giữ nguyên, chỉ liệt kê để platform biết)."""

    skills: list[str] = []
    for p in (root / ".mcp.json", root / ".claude" / "settings.json"):
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            skills += list((data.get("mcpServers") or {}).keys())
        except Exception:
            pass
    return sorted(set(skills))


def build_manifest(args, repo_url: str, skills: list[str]) -> str:
    skill_lines = "\n".join(f"  - {{name: {s}, type: mcp}}" for s in skills) or \
                  "  - {name: none, type: mcp}"
    return f"""apiVersion: lsr/v1
agent:
  id: {args.id}
  name: {args.name}
  version: 0.1.0
  owner: {args.owner}
  squad: {args.squad or '""'}
  is_squad_agent: false
  connect_mode: {args.connect_mode}
  description: >
    Agent có sẵn, được adopt vào platform (giữ nguyên cấu hình & nơi chạy).

deployment:
  mode: external            # platform KHÔNG host; team tự vận hành
  repo_url: {repo_url or '""'}
  host_note: "{args.host_note}"

lark:
  connect_mode: {args.connect_mode}

runtime:
  sdk: claude-agent-sdk
  auth: subscription        # auth của OWNER (claude setup-token) — không dùng khoá chung
  model: {args.model}

skills:                     # MCP đang dùng (dò tự động, chỉ khai báo)
{skill_lines}

telemetry:
  enabled: true             # bắt buộc: platform nắm qua trace
  collector: {args.collector}

tests:
  suite: tests/agent_tests.yaml
schedule: []
"""


def install_hooks(root: Path, trace_src: Path | None) -> list[str]:
    """Thêm hook telemetry vào .claude/settings.json (giữ nguyên cấu hình khác)."""

    written = []
    lsr_dir = root / ".lsr"
    lsr_dir.mkdir(exist_ok=True)
    if trace_src and trace_src.exists():
        (lsr_dir / "lsr_trace.py").write_text(trace_src.read_text(encoding="utf-8"),
                                              encoding="utf-8")
        written.append(TRACE_SCRIPT)

    settings_path = root / ".claude" / "settings.json"
    settings_path.parent.mkdir(exist_ok=True)
    settings = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception:
            settings = {}
    hooks = settings.setdefault("hooks", {})
    cmd = f'python3 "$CLAUDE_PROJECT_DIR/{TRACE_SCRIPT}"'
    # Điểm chặn runtime (hỏi Policy API) + telemetry — khớp plugin lsr-telemetry.
    hooks.setdefault("PreToolUse", []).append(
        {"matcher": "*", "hooks": [{"type": "command", "command": f"{cmd} pre-tool"}]})
    hooks.setdefault("UserPromptSubmit", []).append(
        {"hooks": [{"type": "command", "command": f"{cmd} pre-prompt"}]})
    hooks.setdefault("PostToolUse", []).append(
        {"matcher": "*", "hooks": [{"type": "command", "command": f"{cmd} post-tool"}]})
    hooks.setdefault("Stop", []).append(
        {"hooks": [{"type": "command", "command": f"{cmd} stop"}]})
    settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    written.append(".claude/settings.json")
    return written


def _post(platform: str, path: str, token: str, payload: dict) -> dict:
    req = urllib.request.Request(
        platform.rstrip("/") + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {token}"},
        method="POST",
    )
    gw = os.environ.get("LSR_GATEWAY_TOKEN")
    if gw:
        req.add_header("X-Gateway-Token", gw)  # chỉ cần cho /register (admin); enroll thì bỏ qua
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def register(platform: str, admin_token: str, payload: dict) -> dict:
    """Admin đăng ký (đầy đủ quyền)."""
    return _post(platform, "/v1/agents/register", admin_token, payload)


def enroll(platform: str, enroll_token: str, payload: dict) -> dict:
    """Self-service: thành viên tự đăng ký bằng enroll token (agent inactive + cấp key)."""
    return _post(platform, "/v1/agents/enroll", enroll_token, payload)


def main() -> int:
    ap = argparse.ArgumentParser(description="Adopt agent có sẵn vào LSR platform")
    ap.add_argument("--id", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--owner", required=True, help="email owner (auth dùng subscription của người này)")
    ap.add_argument("--squad", default="")
    ap.add_argument("--connect-mode", default="bot", choices=["bot", "user"])
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--host-note", default="team tự host")
    ap.add_argument("--platform", default=os.environ.get("LSR_PLATFORM_URL", ""))
    ap.add_argument("--collector", default=os.environ.get("LSR_COLLECTOR", ""))
    ap.add_argument("--admin-token", default=os.environ.get("PLATFORM_ADMIN_TOKEN", ""))
    ap.add_argument("--enroll-token", default=os.environ.get("LSR_ENROLL_TOKEN", ""),
                    help="token self-service (thành viên tự đăng ký, không cần admin)")
    ap.add_argument("--trace-script", default="", help="đường dẫn lsr_trace.py của platform")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not re.match(r"^[^@]+@[^@]+\.[^@]+$", args.owner):
        print("owner phải là email."); return 1

    root = Path.cwd()
    repo_url = detect_repo_url(root)
    skills = detect_mcp_skills(root)
    print(f"• Repo: {repo_url or '(không có git remote)'}")
    print(f"• Project: {detect_project_name(root)}")
    print(f"• MCP dò được: {', '.join(skills) or '(không thấy)'}")

    manifest = build_manifest(args, repo_url, skills)
    if args.dry_run:
        print("\n--- lsr-agent.yaml (dry-run) ---\n" + manifest)
        return 0

    (root / "lsr-agent.yaml").write_text(manifest, encoding="utf-8")
    print("✓ Ghi lsr-agent.yaml (deployment: external)")

    trace_src = Path(args.trace_script) if args.trace_script else None
    for f in install_hooks(root, trace_src):
        print(f"✓ Cài telemetry: {f}")
    if not trace_src:
        print("  ⚠ Chưa copy lsr_trace.py — chạy lại với --trace-script <đường dẫn> "
              "hoặc lấy từ plugins/lsr-telemetry/scripts/lsr_trace.py")

    payload = {
        "agent_id": args.id, "name": args.name, "owner": args.owner,
        "squad": args.squad, "connect_mode": args.connect_mode,
        "skills": skills, "deployment": "external",
        "repo_url": repo_url, "host_note": args.host_note,
    }
    # Ưu tiên admin-token (đầy đủ); nếu không có thì dùng enroll-token (self-service).
    do_admin = bool(args.platform and args.admin_token)
    do_enroll = bool(args.platform and not args.admin_token and args.enroll_token)
    if do_admin or do_enroll:
        try:
            res = (register(args.platform, args.admin_token, payload) if do_admin
                   else enroll(args.platform, args.enroll_token, payload))
            print(f"  (đăng ký qua {'admin register' if do_admin else 'self-service enroll'})")
            env = root / ".env.lsr"
            env.write_text(
                f"LSR_AGENT_ID={args.id}\n"
                f"LSR_TELEMETRY_API_KEY={res.get('telemetry_key', '')}\n"
                f"LSR_COLLECTOR={args.collector}\n", encoding="utf-8")
            gi = root / ".gitignore"
            body = gi.read_text(encoding="utf-8") if gi.exists() else ""
            if ".env.lsr" not in body:
                gi.write_text(body.rstrip("\n") + "\n.env.lsr\n", encoding="utf-8")
            print(f"✓ Đăng ký: {res.get('agent_id')} · deployment={res.get('deployment')} "
                  f"· schema={res.get('db_schema')}")
            print("✓ Ghi .env.lsr (đã gitignore) — nạp env này khi chạy agent")
        except urllib.error.HTTPError as e:
            print(f"✗ Đăng ký lỗi {e.code}: {e.read().decode()[:200]}")
            return 1
    else:
        print("• Bỏ qua đăng ký (cần --platform + một trong --admin-token/--enroll-token). Chạy lại khi có.")

    print("\nTiếp theo: owner chạy `claude setup-token` (subscription riêng) rồi "
          "nạp .env.lsr khi khởi động agent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
