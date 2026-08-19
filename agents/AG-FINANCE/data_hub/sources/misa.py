"""Nguồn MISA AMIS (cloud, REST API) — Phase 2, Hương.

Đang chờ: API key / OAuth client từ người quản trị MISA.

Env cần: MISA_BASE_URL, MISA_CLIENT_ID, MISA_CLIENT_SECRET, MISA_COMPANY_CODE.

CHỈ ĐỌC. Không có hàm ghi, không thêm hàm ghi. Bút toán do kế toán tự làm trên MISA —
xem phần "Ngoài phạm vi" trong USECASE.md.

Phần chuẩn hoá dùng chung `TabularSource`, đã test qua `fake.fake_misa()`. Phần còn thiếu là
`reader(table)` gọi API thật. Hai điểm dễ sai khi implement:
  B4 — lỗi 5xx thì raise SourceError, để sync bỏ qua nguồn này và chạy tiếp nguồn khác
  Phân trang — phải đọc HẾT các trang mới coi là thành công, đọc nửa vời còn tệ hơn lỗi
"""

from __future__ import annotations

import os
from collections.abc import Callable

from .base import SourceError, TabularSource

TABLES = ("receivable", "payable", "revenue", "expense")   # cashflow: Phase 2


class MisaAmisSource(TabularSource):
    name = "misa"
    ref_column = "so_hoa_don"

    def __init__(self, reader: Callable[[str], list[dict]] | None = None) -> None:
        self._reader = reader

    def supported_tables(self) -> list[str]:
        return list(TABLES)

    def read_rows(self, table: str) -> list[dict]:
        if self._reader is None:
            raise SourceError("misa: chưa có credential MISA AMIS")
        return self._reader(table)

    def healthcheck(self) -> None:
        if self._reader is None:
            raise SourceError("misa: chưa có credential MISA AMIS")
        for name in ("MISA_BASE_URL", "MISA_CLIENT_ID", "MISA_CLIENT_SECRET"):
            if not os.getenv(name, "").strip():
                raise SourceError(f"misa: chưa cấu hình {name}")
