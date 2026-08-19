"""Chat thử với Ploy NGAY TẠI MÁY — không cần platform / token / admin.

Dùng trong lúc chờ go-live: chạy đúng consumer.answer() thật — đủ mọi gate, tool bối
cảnh TH, và model (nếu bật). Khác bản thật duy nhất: ngữ cảnh hội thoại giữ tạm trong
RAM của phiên chạy này (bản thật do platform giữ qua /v1/self/context).

  python3 chat_local.py                            # REPL — gõ 'exit' để thoát
  python3 chat_local.py "câu hỏi một phát"         # hỏi 1 câu rồi thoát
  cat transcript.txt | python3 chat_local.py       # pipe: cả file = MỘT tin nhắn
  LSR_MODEL_MODE=auto python3 chat_local.py        # bật model (máy đã `claude login`)

Dán nội dung NHIỀU DÒNG trong REPL: gõ `<<<` (Enter), dán, rồi gõ `>>>` (Enter) —
tất cả thành một tin nhắn duy nhất (input() thường sẽ cắt mỗi dòng thành 1 lượt).

Lưu ý: các thao tác cần platform (lưu kho brain, đề xuất task) sẽ được in ra dạng
[LOCAL] thay vì gọi API thật — xem _fake_api bên dưới.
"""

from __future__ import annotations

import sys

import consumer
import model


def _fake_api(method: str, path: str, payload=None, timeout: int = 40):
    """Chặn lời gọi platform khi chạy local — in ra để thấy agent ĐỊNH làm gì."""
    print(f"  [LOCAL] {method} {path} — chưa gửi thật (chưa register platform)")
    return {}


consumer.api = _fake_api

_TURNS: list[dict] = []


def _ctx() -> dict:
    # Giữ 12 lượt gần nhất — đủ cho gate confirm biên bản (minutes.find_draft).
    return {"recent_turns": _TURNS[-12:]}


def ask(q: str) -> str:
    # notify = in ngay dòng "em đang làm gì" (giống tin ack gửi ra Lark) rồi mới suy luận.
    ans = consumer.answer(q, _ctx(), {}, notify=lambda t: print("\nploy >", t, flush=True))
    _TURNS.append({"role": "user", "text": q})
    _TURNS.append({"role": "assistant", "text": ans})
    return ans


def _read_multiline() -> str:
    """Sau khi gõ `<<<`: gom mọi dòng cho tới `>>>` (hoặc EOF) thành MỘT tin nhắn."""
    lines = []
    while True:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            break
        if line.strip() == ">>>":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def main() -> None:
    if len(sys.argv) > 1:
        print(ask(" ".join(sys.argv[1:])))
        return
    if not sys.stdin.isatty():
        # Pipe/redirect: toàn bộ stdin là MỘT tin nhắn (vd cat transcript.txt | ...)
        q = sys.stdin.read().strip()
        if q:
            print(ask(q))
        return
    state = "BẬT (subscription)" if model.enabled() else "TẮT — trả lời bằng luật (bật: LSR_MODEL_MODE=auto)"
    print(f"Ploy (local) — model: {state}. Gõ câu hỏi, 'exit' thoát, `<<<` để dán nhiều dòng.")
    while True:
        try:
            q = input("\nbạn > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if q == "<<<":
            q = _read_multiline()
        if not q or q.lower() in ("exit", "quit", "thoát", "thoat"):
            break
        print("\nploy >", ask(q))


if __name__ == "__main__":
    main()
