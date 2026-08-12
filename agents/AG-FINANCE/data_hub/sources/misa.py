"""Nguồn MISA AMIS (cloud, REST API) — Phase 2, Hương.

CHƯA IMPLEMENT. Đang chờ: API key / OAuth client từ người quản trị MISA.

Env cần: MISA_BASE_URL, MISA_CLIENT_ID, MISA_CLIENT_SECRET, MISA_COMPANY_CODE.

CHỈ ĐỌC. Không có hàm ghi, không thêm hàm ghi. Bút toán do kế toán tự làm trên MISA —
xem phần "Ngoài phạm vi" trong USECASE.md.

Việc cần làm:
  B4 — API lỗi 5xx thì raise SourceError, để sync bỏ qua nguồn này và chạy tiếp nguồn khác
  B5 — số lệch với Google Sheet: KHÔNG tự chọn bên nào, xem docs/DATA_MODEL.md
  Phân trang: MISA trả theo trang, phải đọc hết mới coi là thành công
"""

from __future__ import annotations

from .base import FetchResult, Source


class MisaAmisSource(Source):
    name = "misa"

    def supported_tables(self) -> list[str]:
        return ["receivable", "payable", "revenue", "expense", "cashflow"]

    def fetch(self, table: str) -> FetchResult:
        raise NotImplementedError("Phase 2 — chờ credential MISA, xem docstring module")

    def healthcheck(self) -> None:
        raise NotImplementedError("Phase 2 — chờ credential MISA, xem docstring module")
