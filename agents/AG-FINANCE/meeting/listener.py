"""Nhận diện ý định liên quan cuộc họp từ job của platform. Phase 3, Thái.

CHƯA IMPLEMENT phần xử lý. Hằng số dưới đây đã chốt.

Job đến từ mọi kênh qua consumer.py, module này chỉ trả lời "job này là việc gì của luồng
biên bản họp", không tự gửi tin và không tự tạo task.

Luật đã chốt:
  • Chỉ người chủ trì chốt được. Người khác nói "chốt" thì không tính (D5).
  • Đã tạo task rồi thì không tạo lần hai (D6).
"""

from __future__ import annotations

RECORDING_TYPES = frozenset({"audio", "media", "file"})
CONFIRM_WORDS = frozenset({"chốt", "chot", "confirm", "duyệt", "duyet"})

INTENT_RECORDING = "recording"     # có recording mới → dựng biên bản
INTENT_CONFIRM = "confirm"         # có người muốn chốt biên bản
INTENT_TRANSCRIPT = "transcript"   # có người dán transcript thô bằng text
INTENT_NONE = "none"               # không liên quan luồng họp


def detect_intent(payload: dict) -> str:
    """Trả một trong các INTENT_* ở trên."""
    raise NotImplementedError("Phase 3 — xem docstring module")


def is_chair(payload: dict, chair_open_id: str) -> bool:
    """True nếu người gửi job này là người chủ trì cuộc họp (D5)."""
    raise NotImplementedError("Phase 3 — xem docstring module")
