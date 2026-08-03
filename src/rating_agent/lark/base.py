"""Khung client Lark Base (Bitable) — đọc/ghi master data & registry.

Lark Base là "system of record": squads, squad_objectives, agents, agent_skills,
agent_test_cases, agent_test_runs, agent_usage, và các bảng kết quả đánh giá.

Endpoint tham khảo:
- Liệt kê record:  GET  /bitable/v1/apps/{app_token}/tables/{table_id}/records
- Tạo record:      POST /bitable/v1/apps/{app_token}/tables/{table_id}/records
- Cập nhật record: PUT  /bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}

Bản MVP: chữ ký + luồng gọi qua :class:`LarkClient`. Cần app_token + quyền
``bitable:app`` để chạy thật. Có thể thay bằng Lark MCP (base_record_list,
base_record_create) khi chạy trong môi trường có MCP.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .client import LarkClient

# Tên bảng logic → cần map sang table_id thật khi cấu hình.
TABLES = (
    "squads",
    "squad_objectives",
    "employees",
    "agents",
    "agent_skills",
    "agent_test_cases",
    "agent_test_runs",
    "agent_usage",
    "squad_evaluations",
    "agent_evaluations",
)


@dataclass
class LarkBaseClient:
    """Đọc/ghi record trên một app Lark Base.

    ``table_ids`` ánh xạ tên bảng logic (xem :data:`TABLES`) → table_id thật.
    """

    client: LarkClient
    app_token: str
    table_ids: dict[str, str]

    def _table_id(self, table: str) -> str:
        if table not in self.table_ids:
            raise KeyError(f"Chưa cấu hình table_id cho bảng '{table}'")
        return self.table_ids[table]

    def list_records(self, table: str, *, page_size: int = 100) -> list[dict[str, Any]]:
        """Liệt kê record của một bảng (khung, chưa gộp phân trang)."""

        table_id = self._table_id(table)
        data = self.client.get(
            f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records",
            params={"page_size": page_size},
        )
        return data.get("items", [])

    def create_record(self, table: str, fields: dict[str, Any]) -> dict[str, Any]:
        """Tạo một record mới (khung)."""

        table_id = self._table_id(table)
        return self.client.post(
            f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records",
            json_body={"fields": fields},
        )

    def update_record(self, table: str, record_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        """Cập nhật record (khung) — ví dụ set agents.status = deactivated."""

        table_id = self._table_id(table)
        return self.client.request(
            "PUT",
            f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/{record_id}",
            json_body={"fields": fields},
        )

    # -- Tiện ích governance -------------------------------------------
    def deactivate_agent(self, record_id: str, reason: str) -> dict[str, Any]:
        """Đặt agent về trạng thái deactivated kèm lý do."""

        return self.update_record(
            "agents",
            record_id,
            {"status": "deactivated", "deactivate_reason": reason},
        )
