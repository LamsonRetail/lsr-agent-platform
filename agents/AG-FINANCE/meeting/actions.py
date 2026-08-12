"""Tạo task và lưu biên bản sau khi chủ trì chốt. Phase 3, Thái.

CHƯA IMPLEMENT.

Đây là module duy nhất trong luồng họp có tác động ra ngoài (tạo task thật, ghi tài liệu
thật). Vì vậy điều kiện gọi phải chặt:
  • Chỉ gọi khi minutes.confirmed là True (D3).
  • Chỉ gọi khi minutes.tasks_created là False (D6).
  • Đầu việc chưa rõ người phụ trách thì vẫn tạo task nhưng để trống assignee, KHÔNG tự gán.

Dùng skill lark-task và lark-docx khai trong lsr-agent.yaml. Không gọi Lark API bằng
app_secret — đi qua shared/lark.py.
"""

from __future__ import annotations

from .minutes import Minutes


def create_tasks(minutes: Minutes) -> list[str]:
    """Tạo task Lark cho từng đầu việc. Trả danh sách task id.

    Raise nếu minutes chưa được chủ trì chốt hoặc task đã được tạo trước đó.
    """
    raise NotImplementedError("Phase 3 — xem docstring module")


def archive_minutes(minutes: Minutes) -> str:
    """Lưu biên bản để tra cứu lại. Trả link tài liệu."""
    raise NotImplementedError("Phase 3 — xem docstring module")
