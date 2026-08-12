#!/usr/bin/env python3
"""Hook handler cho plugin lsr-telemetry.

Được Claude Code gọi qua hooks:
  - PostToolUse -> ghi lại một tool call vào buffer theo session.
  - Stop        -> tổng hợp buffer + parse transcript (token, output cuối) ->
                   dựng AgentRunTrace -> POST về collector -> xoá buffer.

Nguyên tắc: LUÔN best-effort, luôn exit 0 — không được làm hỏng phiên Claude Code
của người dùng. Nếu thiếu cấu hình (LSR_COLLECTOR) thì no-op êm.

Cấu hình qua env (đặt ở môi trường chạy agent):
  LSR_COLLECTOR           = https://collector.lsr.internal
  LSR_TELEMETRY_API_KEY   = lsr_tel_...
  LSR_AGENT_ID            = AG-...
  LSR_TRACE_DIR           = (tuỳ chọn) thư mục buffer, mặc định /tmp/lsr-trace
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import urllib.request


def _buf_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("LSR_TRACE_DIR", "/tmp/lsr-trace"))


def _buf_file(session_id: str) -> pathlib.Path:
    return _buf_dir() / f"{session_id or 'unknown'}.jsonl"


# ----------------------- PreToolUse / UserPromptSubmit (policy) -----------------------

def _policy_check(payload: dict) -> dict:
    """Gọi điểm chặn runtime của platform. Lỗi/không cấu hình → allow (fail-open)."""

    url = os.environ.get("LSR_COLLECTOR")
    if not url:
        return {"decision": "allow"}
    token = os.environ.get("LSR_TELEMETRY_API_KEY", "")
    req = urllib.request.Request(
        url.rstrip("/") + "/v1/policy/check",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        # fail-open mặc định để không làm hỏng phiên; đặt LSR_POLICY_FAIL_OPEN=false để fail-closed.
        if os.environ.get("LSR_POLICY_FAIL_OPEN", "true").lower() == "false":
            return {"decision": "deny", "reason": "policy service không phản hồi (fail-closed)"}
        return {"decision": "allow"}


def pre_tool(evt: dict) -> None:
    """PreToolUse: gate use-case/test-case (local) + hỏi policy (remote). Deny → chặn tool."""

    # --- Gate LOCAL: agent mới phải có USE CASE + TEST CASE trước khi viết code ---
    # Chặn Write/Edit file CODE trong agents/<id>/ nếu thiếu USECASE.md / TESTCASES.md.
    # Viết chính 2 file .md đó (hoặc tests.jsonl, README...) thì luôn cho phép.
    gate = _usecase_gate(evt)
    if gate:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": gate,
        }}, ensure_ascii=False))
        return

    res = _policy_check({
        "agent_id": os.environ.get("LSR_AGENT_ID", "unknown"),
        "phase": "pre_tool",
        "tool": evt.get("tool_name", ""),
        "arguments": json.dumps(evt.get("tool_input") or {}, ensure_ascii=False)[:4000],
    })
    if res.get("decision") == "deny":
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": res.get("reason") or "bị chặn bởi policy LSR",
        }}))
    # allow → không in gì (mặc định cho phép)


_CODE_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".sh", ".go", ".rb", ".java", ".sql"}


def _usecase_gate(evt: dict) -> str | None:
    """Trả message chặn nếu đang viết CODE cho agent chưa có USECASE.md + TESTCASES.md."""

    if evt.get("tool_name") not in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        return None
    fp = (evt.get("tool_input") or {}).get("file_path") or ""
    if not fp:
        return None
    p = pathlib.Path(fp)
    parts = p.parts
    # tìm segment 'agents/<id>/...' trong đường dẫn
    try:
        i = parts.index("agents")
    except ValueError:
        return None
    if i + 2 > len(parts) - 1:          # phải có agents/<id>/<file...>
        return None
    if p.suffix.lower() not in _CODE_EXT:
        return None                      # .md/.jsonl/.yaml... luôn cho phép
    agent_dir = pathlib.Path(*parts[: i + 2])
    missing = [f for f in ("USECASE.md", "TESTCASES.md") if not (agent_dir / f).exists()]
    if not missing:
        return None
    return (f"⛔ Agent '{parts[i+1]}' chưa có {' + '.join(missing)} — theo quy trình platform, "
            f"phải viết USE CASE và TEST CASE trước rồi mới code. "
            f"Tạo {agent_dir}/USECASE.md (bài toán, người dùng, luồng chính) và "
            f"{agent_dir}/TESTCASES.md (bảng case: đầu vào → kỳ vọng) rồi chạy lại. "
            f"Scaffold nhanh: bash scripts/new-agent.sh {parts[i+1]}")


def pre_prompt(evt: dict) -> None:
    """UserPromptSubmit: quét prompt đầu vào. Deny → chặn prompt."""

    res = _policy_check({
        "agent_id": os.environ.get("LSR_AGENT_ID", "unknown"),
        "phase": "pre_prompt",
        "prompt": (evt.get("prompt") or "")[:8000],
    })
    if res.get("decision") == "deny":
        print(json.dumps({"decision": "block",
                          "reason": res.get("reason") or "prompt bị chặn bởi policy LSR"}))


# ----------------------- PostToolUse -----------------------

def tool_outcome(tool_response) -> tuple[bool, bool]:
    """Suy ra (ok, has_result) từ tool_response của Claude Code."""

    ok = True
    if isinstance(tool_response, dict):
        if tool_response.get("error") or tool_response.get("is_error"):
            ok = False
        has_result = bool(
            tool_response.get("content")
            or tool_response.get("stdout")
            or tool_response.get("result")
            or (tool_response and not tool_response.get("error"))
        )
    else:
        has_result = bool(tool_response)
    return ok, has_result


def record_tool(evt: dict) -> None:
    ok, has_result = tool_outcome(evt.get("tool_response"))
    rec = {"name": evt.get("tool_name", ""), "ok": ok, "has_result": has_result}
    d = _buf_dir()
    d.mkdir(parents=True, exist_ok=True)
    with _buf_file(evt.get("session_id", "")).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


# ----------------------- Stop -----------------------

def parse_transcript(path: str) -> tuple[int, int, str]:
    """Duyệt transcript JSONL: tổng token + text trợ lý cuối cùng."""

    input_t = output_t = 0
    final = ""
    if not path:
        return input_t, output_t, final
    try:
        lines = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return input_t, output_t, final
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = obj.get("message") if isinstance(obj, dict) else None
        if not isinstance(msg, dict):
            continue
        usage = msg.get("usage") or {}
        input_t += int(usage.get("input_tokens", 0) or 0)
        output_t += int(usage.get("output_tokens", 0) or 0)
        if msg.get("role") == "assistant":
            for block in msg.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "text":
                    final = block.get("text", final)
    return input_t, output_t, final


def build_trace(
    session_id: str,
    tool_records: list[dict],
    input_tokens: int,
    output_tokens: int,
    final_output: str,
    agent_id: str,
    model: str = "claude",
) -> dict:
    """Dựng dict theo schema AgentRunTrace (khớp collector)."""

    return {
        "run_id": session_id or "unknown",
        "agent_id": agent_id or "unknown",
        "task_id": session_id or "",
        "source": "production",
        "llm_calls": [
            {"model": model, "input_tokens": input_tokens, "output_tokens": output_tokens}
        ],
        "tool_calls": [
            {"name": r.get("name", ""), "ok": r.get("ok", True),
             "has_result": r.get("has_result", True)}
            for r in tool_records
        ],
        "final_output": final_output,
    }


def post_trace(trace: dict) -> bool:
    url = os.environ.get("LSR_COLLECTOR")
    if not url:
        return False
    token = os.environ.get("LSR_TELEMETRY_API_KEY", "")
    req = urllib.request.Request(
        url.rstrip("/") + "/v1/traces",
        data=json.dumps(trace).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=5)
        return True
    except Exception:
        return False


def stop(evt: dict) -> None:
    session_id = evt.get("session_id", "")
    buf = _buf_file(session_id)
    records: list[dict] = []
    if buf.exists():
        for line in buf.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    it, ot, final = parse_transcript(evt.get("transcript_path", ""))
    trace = build_trace(
        session_id, records, it, ot, final, os.environ.get("LSR_AGENT_ID", "unknown")
    )
    post_trace(trace)
    try:
        if buf.exists():
            buf.unlink()
    except OSError:
        pass


# ----------------------- main -----------------------

def main() -> None:
    evt: dict = {}
    try:
        evt = json.load(sys.stdin)
    except Exception:
        evt = {}
    mode = sys.argv[1] if len(sys.argv) > 1 else evt.get("hook_event_name", "")
    try:
        if mode in ("pre-tool", "PreToolUse"):
            pre_tool(evt)
        elif mode in ("pre-prompt", "UserPromptSubmit"):
            pre_prompt(evt)
        elif mode in ("post-tool", "PostToolUse"):
            record_tool(evt)
        elif mode in ("stop", "Stop"):
            stop(evt)
    except Exception:
        pass  # best-effort, không làm hỏng phiên
    sys.exit(0)


if __name__ == "__main__":
    main()
