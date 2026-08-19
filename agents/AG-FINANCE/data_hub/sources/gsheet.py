"""Nguồn Google Sheet — Hương.

Phần chuẩn hoá đã xong và đã test (qua `TabularSource` + `mapping.py`). Phần còn thiếu chỉ
là hàm đọc dòng thô, đang chờ service account JSON + sheet được share quyền Viewer.

Env cần: GSHEET_CREDENTIALS_JSON (đường dẫn file), GSHEET_SPREADSHEET_ID,
GSHEET_TAB_<TABLE> (tên tab cho từng bảng, ví dụ GSHEET_TAB_RECEIVABLE).

Khi có credential, chỉ cần cấp `reader` cho constructor — không sửa gì trong file này.
`reader(tab_name)` trả list[dict] {tên cột: giá trị}, dòng header đã bị bỏ.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from .base import SourceError, TabularSource

TABLES = ("receivable", "payable", "revenue", "expense")   # cashflow: Phase 2


class GoogleSheetSource(TabularSource):
    name = "gsheet"
    ref_column = "Số hoá đơn"

    def __init__(self, reader: Callable[[str], list[dict]] | None = None) -> None:
        self._reader = reader

    def supported_tables(self) -> list[str]:
        return list(TABLES)

    def tab_name(self, table: str) -> str:
        tab = os.getenv(f"GSHEET_TAB_{table.upper()}", "").strip()
        if not tab:
            raise SourceError(f"gsheet: chưa cấu hình GSHEET_TAB_{table.upper()}")
        return tab

    def read_rows(self, table: str) -> list[dict]:
        if self._reader is None:
            raise SourceError(
                "gsheet: chưa có service account. Dùng data_hub.sources.fake.fake_gsheet() "
                "cho chế độ dữ liệu giả, hoặc truyền reader vào constructor."
            )
        return self._reader(self.tab_name(table))

    def healthcheck(self) -> None:
        if self._reader is None:
            raise SourceError("gsheet: chưa có service account")
        if not os.getenv("GSHEET_SPREADSHEET_ID", "").strip():
            raise SourceError("gsheet: chưa cấu hình GSHEET_SPREADSHEET_ID")
