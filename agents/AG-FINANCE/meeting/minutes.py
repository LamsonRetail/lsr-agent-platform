"""Dựng biên bản họp từ transcript. Phase 3, Thái.

CHƯA IMPLEMENT phần sinh nội dung. Các dataclass dưới đây là hợp đồng dữ liệu, đã chốt.

Luật đã chốt trong USECASE.md và system_prompt.md:
  • Biên bản có 4 phần: bối cảnh, nội dung chính, quyết định, đầu việc.
  • Mỗi đầu việc phải có người chịu trách nhiệm và hạn. Transcript không nói rõ thì để
    assignee rỗng và ghi "chưa rõ người phụ trách" — KHÔNG tự gán cho ai (D2).
  • Không có đầu việc nào thì để list rỗng và nói rõ là không có. KHÔNG bịa task cho biên
    bản trông đầy đủ (D7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class ActionItem:
    what: str
    assignee: str = ""          # rỗng = chưa rõ người phụ trách, không được tự gán
    due: date | None = None

    @property
    def is_complete(self) -> bool:
        return bool(self.assignee) and self.due is not None


@dataclass
class Minutes:
    meeting_title: str
    meeting_date: date
    chair_open_id: str          # người chủ trì — CHỈ người này chốt được (D5)
    attendees: list[str] = field(default_factory=list)
    context: str = ""
    key_points: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    action_items: list[ActionItem] = field(default_factory=list)
    confirmed: bool = False     # True sau khi chủ trì chốt. Chưa chốt = chưa tạo task (D3)
    tasks_created: bool = False # chặn tạo task lần hai (D6)


def build_minutes(transcript: str, *, chair_open_id: str, title: str, when: date) -> Minutes:
    """Sinh biên bản từ transcript bằng model.

    Không suy diễn quá transcript. Thông tin không có trong transcript thì để rỗng.
    """
    raise NotImplementedError("Phase 3 — xem docstring module")


def render_for_review(minutes: Minutes) -> str:
    """Dựng bản nháp gửi vào nhóm Lark để chủ trì xem và chốt."""
    raise NotImplementedError("Phase 3 — xem docstring module")
