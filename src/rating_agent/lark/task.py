"""Khung dịch vụ Lark Task — theo dõi task và trích tín hiệu performance/grow.

Endpoint tham khảo:
- Danh sách task:  GET /task/v2/tasks
- Chi tiết task:   GET /task/v2/tasks/<task_guid>

Trích tín hiệu: tỉ lệ hoàn thành, đúng hạn, độ khó, task phối hợp liên nhóm.
"""

from __future__ import annotations

from dataclasses import dataclass

from .client import LarkClient


@dataclass
class TaskSignal:
    """Tín hiệu task quy về một nhân viên."""

    lark_user_id: str
    tasks_total: int = 0
    tasks_completed: int = 0
    tasks_on_time: int = 0
    cross_team_tasks: int = 0
    avg_complexity: float | None = None

    @property
    def completion_rate(self) -> float:
        if self.tasks_total == 0:
            return 0.0
        return self.tasks_completed / self.tasks_total

    @property
    def on_time_rate(self) -> float:
        if self.tasks_completed == 0:
            return 0.0
        return self.tasks_on_time / self.tasks_completed


class LarkTaskService:
    """Trích tín hiệu performance/grow từ Lark Task."""

    def __init__(self, client: LarkClient) -> None:
        self._client = client

    def list_tasks(self, page_size: int = 50) -> list[dict]:
        """Liệt kê task (khung, chưa xử lý phân trang đầy đủ)."""

        data = self._client.get("/task/v2/tasks", params={"page_size": page_size})
        return data.get("items", [])

    def get_task(self, task_guid: str) -> dict:
        """Lấy chi tiết một task (khung)."""

        return self._client.get(f"/task/v2/tasks/{task_guid}")

    def collect_signals(self) -> dict[str, TaskSignal]:
        """Tổng hợp tín hiệu task theo nhân viên (khung).

        TODO(giai đoạn 2): duyệt task, tính hạn/hoàn thành/độ khó theo người phụ trách.
        """

        signals: dict[str, TaskSignal] = {}
        for _task in self.list_tasks():
            # Điểm cắm: map người phụ trách → cập nhật TaskSignal.
            pass
        return signals
