"""Lark Base — vừa là nguồn, vừa là MẶT TIỀN FIN-HUB. Phase 1, Hương.

CHƯA IMPLEMENT. Đang chờ: bot được cấp scope `bitable:app` và app_token của Base FIN-HUB.

Env cần: LARK_BASE_APP_TOKEN, LARK_BASE_TABLE_<TABLE> (table_id cho từng bảng).

Lưu ý quan trọng: `libs/lsr_lark` của platform CHƯA hỗ trợ Bitable — nó chỉ có gửi tin,
resolve open_id và liệt kê chat. Nên phần Bitable phải gọi Lark Open API trực tiếp và code
đó nằm ở đây, trong thư mục agent. Không sửa `libs/lsr_lark` (đó là core).

Việc cần làm:
  Đọc  — làm nguồn cho các bảng đang theo dõi tay trên Lark Base
  Ghi  — upsert theo natural_key. B6 yêu cầu chạy hai lần không nhân đôi dòng
  B7   — nguồn rỗng thì KHÔNG xoá dữ liệu cũ đang có trên Base
"""

from __future__ import annotations

from .base import FetchResult, Source


class LarkBaseSource(Source):
    name = "larkbase"

    def supported_tables(self) -> list[str]:
        return ["receivable", "payable", "revenue", "expense", "cashflow"]

    def fetch(self, table: str) -> FetchResult:
        raise NotImplementedError("Phase 1 — chờ scope bitable:app, xem docstring module")

    def healthcheck(self) -> None:
        raise NotImplementedError("Phase 1 — chờ scope bitable:app, xem docstring module")

    def upsert(self, table: str, records: list[object]) -> int:
        """Ghi vào FIN-HUB theo natural_key. Trả số dòng đã ghi.

        Phải idempotent: cùng natural_key thì cập nhật, không thêm dòng mới (testcase B6).
        """
        raise NotImplementedError("Phase 1 — chờ scope bitable:app, xem docstring module")
