"""Cầu nối model cho Ploy (AG-SQ-THAILAND) — Phase 2: thay luật bằng model, giữ mọi gate.

Vị trí trong answer() của consumer: SAU toàn bộ gate luật (recording, confirm biên bản,
task, save-có-nguồn, chặn nhạy cảm, chào hỏi, tool bối cảnh TH, tri thức đã duyệt) và
TRƯỚC câu trả lời "chưa có dữ liệu". Model tắt / lỗi / trả rỗng → ``None`` → consumer
rơi về luật cũ, nên container và bộ test không có model **giữ nguyên hành vi**.

Auth đúng chuẩn platform (``lsr-agent.yaml: auth: subscription``): gọi **Claude Code CLI**
(``claude -p``) chạy bằng subscription của OWNER (``claude login`` / ``claude setup-token``
trên máy chạy agent). Agent KHÔNG cầm API key. Chỉ stdlib.

Bật/tắt qua env (khai ở .env):
  LSR_MODEL_MODE     off (mặc định) | auto — dùng model nếu tìm thấy CLI
  LSR_MODEL_BIN      tên/đường dẫn CLI (mặc định: claude)
  LSR_MODEL_NAME     ép model cụ thể (mặc định: để CLI tự chọn theo subscription)
  LSR_MODEL_TIMEOUT  giây, mặc định 90

Chủ file: **Data/Tech**. Luồng biên bản (minutes.build_draft) chuyển model sau —
file của Hương, đã có sẵn ``minutes.prompt_for()`` để dùng với ``complete()`` này.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess

_DIR = os.path.dirname(os.path.abspath(__file__))

MODE = os.environ.get("LSR_MODEL_MODE", "off").lower()
BIN = os.environ.get("LSR_MODEL_BIN", "claude")
NAME = os.environ.get("LSR_MODEL_NAME", "")
TIMEOUT = int(os.environ.get("LSR_MODEL_TIMEOUT", "90"))

# Luật cứng ghép vào cuối system prompt — model KHÔNG được nới các gate của luồng luật.
_HARD_RULES = """
## Luật cứng khi trả lời (không được nới)

- Ngữ cảnh không có tri thức đã duyệt liên quan tới câu hỏi số liệu → trả lời đúng ý:
  "Chưa có thông tin đã được duyệt trong kho của squad Thái Lan cho câu này nên tôi
  không đoán" và xin link Lark đối chứng. TUYỆT ĐỐI không bịa số, không lấy kiến thức
  ngoài thay cho số nội bộ.
- Mọi số liệu nêu ra phải kèm nguồn + thời điểm + base target đang dùng (9,3M THB
  tháng · 8,0M THB ngày, rebase 22/07). Số ước tính ghi (ước tính).
- Không tạo task, không lưu biên bản khi chủ trì chưa "chốt". Không hứa gửi tin cho ai.
- Lương / giá vốn / thông tin cá nhân khách hàng: từ chối, chỉ về đúng bộ phận.
"""


def enabled() -> bool:
    return MODE in ("auto", "on") and shutil.which(BIN) is not None


def build_system() -> str:
    """Ghép system prompt đầy đủ: system_prompt.md + persona + skills/*.md + luật cứng."""
    parts = []
    parts.append(_read(os.path.join(_DIR, "system_prompt.md")))

    persona = _read_json(os.path.join(_DIR, "configs", "persona.json"))
    if persona:
        parts.append(
            f"## Persona\n\nTên gọi: **{persona.get('name', 'Ploy')}** — "
            f"{persona.get('full_name', '')}. {persona.get('address_style', '')}; "
            f"{persona.get('tone', '')}.\n"
            + "\n".join(f"- {r}" for r in persona.get("honesty_rules", []))
        )

    skills_dir = os.path.join(_DIR, "skills")
    if os.path.isdir(skills_dir):
        for fn in sorted(os.listdir(skills_dir)):
            if fn.endswith(".md") and fn != "README.md":
                body = _read(os.path.join(skills_dir, fn))
                if body:
                    parts.append(f"## Skill: {fn}\n\n{body[:6000]}")

    parts.append(_HARD_RULES)
    return "\n\n---\n\n".join(p for p in parts if p)


def complete(prompt: str, system: str = "") -> str | None:
    """Gọi model 1 lượt, stateless. Trả None khi tắt/lỗi/timeout/rỗng — caller về luật."""
    if not enabled():
        return None
    full = (system + "\n\n=== CÂU HỎI (trả lời trực tiếp, tiếng Việt) ===\n\n" + prompt
            if system else prompt)
    cmd = [shutil.which(BIN), "-p", full]
    if NAME:
        cmd += ["--model", NAME]
    # stdin phải ĐÓNG (CLI -p sẽ đợi stdin nếu là pipe) + bỏ env CLAUDE* (tránh xung đột
    # khi tiến trình cha cũng là một phiên Claude Code).
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT,
                           stdin=subprocess.DEVNULL, env=env)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if r.returncode != 0:
        return None
    out = (r.stdout or "").strip()
    return out or None


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def _read_json(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None
