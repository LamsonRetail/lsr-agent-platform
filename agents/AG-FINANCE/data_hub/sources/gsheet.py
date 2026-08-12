"""Nguồn Google Sheet — Phase 1, Hương.

CHƯA IMPLEMENT. Đang chờ: service account JSON + sheet được share quyền Viewer.

Env cần: GSHEET_CREDENTIALS_JSON (đường dẫn file), GSHEET_SPREADSHEET_ID,
GSHEET_TAB_<TABLE> (tên tab cho từng bảng).

Việc cần làm, theo thứ tự testcase trong TESTCASES.md:
  B1 — map 1 row → schema.Receivable, tiền qua schema.parse_money
  B2 — thiếu cột bắt buộc thì gom vào RowError kèm số dòng, không điền mặc định
  B3 — "1.234.567đ" phải ra 1234567
  B7 — sheet rỗng trả FetchResult(records=[], errors=[]), không raise
"""

from __future__ import annotations

from .base import FetchResult, Source


class GoogleSheetSource(Source):
    name = "gsheet"

    def supported_tables(self) -> list[str]:
        return ["receivable", "payable", "revenue", "expense", "cashflow"]

    def fetch(self, table: str) -> FetchResult:
        raise NotImplementedError("Phase 1 — chờ service account, xem docstring module")

    def healthcheck(self) -> None:
        raise NotImplementedError("Phase 1 — chờ service account, xem docstring module")
