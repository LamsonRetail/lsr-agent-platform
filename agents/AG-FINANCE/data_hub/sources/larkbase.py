"""Lark Base — vừa là nguồn, vừa là MẶT TIỀN FIN-HUB. Hương.

Đang chờ: bot được cấp scope `bitable:app` và app_token của Base FIN-HUB.

Env cần: LARK_BASE_APP_TOKEN, LARK_BASE_TABLE_<TABLE> (table_id cho từng bảng).

Lưu ý quan trọng: `libs/lsr_lark` của platform CHƯA hỗ trợ Bitable — nó chỉ có gửi tin,
resolve open_id và liệt kê chat. Nên phần Bitable phải gọi Lark Open API trực tiếp và code
đó nằm ở đây, trong thư mục agent. Không sửa `libs/lsr_lark` (đó là core).

Cả `LarkBaseSource` và `LarkBaseStore` đều nhận transport từ ngoài vào. Chừng nào chưa có
scope, chạy với `MemoryStore` (store.py) — sync.py và query.py không biết khác biệt.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime

from ..store import Store
from .base import SourceError, TabularSource

TABLES = ("receivable", "payable", "revenue", "expense")   # cashflow: Phase 2


def _table_id(table: str) -> str:
    tid = os.getenv(f"LARK_BASE_TABLE_{table.upper()}", "").strip()
    if not tid:
        raise SourceError(f"larkbase: chưa cấu hình LARK_BASE_TABLE_{table.upper()}")
    return tid


class LarkBaseSource(TabularSource):
    """Đọc các bảng squad đang theo dõi tay trên Lark Base."""

    name = "larkbase"
    ref_column = "record_id"

    def __init__(self, reader: Callable[[str], list[dict]] | None = None) -> None:
        self._reader = reader

    def supported_tables(self) -> list[str]:
        return list(TABLES)

    def read_rows(self, table: str) -> list[dict]:
        if self._reader is None:
            raise SourceError("larkbase: chưa có scope bitable:app")
        return self._reader(_table_id(table))

    def healthcheck(self) -> None:
        if self._reader is None:
            raise SourceError("larkbase: chưa có scope bitable:app")
        if not os.getenv("LARK_BASE_APP_TOKEN", "").strip():
            raise SourceError("larkbase: chưa cấu hình LARK_BASE_APP_TOKEN")


class LarkBaseStore(Store):
    """FIN-HUB thật. Cùng giao diện với MemoryStore nên sync.py/query.py không phải sửa.

    Ba tính chất bắt buộc khi implement `writer`:
      • Tìm dòng theo natural_key rồi update, chỉ tạo mới khi không tìm thấy (B6).
      • KHÔNG có đường nào xoá dòng. Nguồn rỗng thì Base giữ nguyên dữ liệu cũ (B7).
      • Mốc đồng bộ ghi vào bảng sync_log riêng, không suy ra từ dữ liệu (C2).
    """

    def __init__(self, writer=None) -> None:
        self._writer = writer

    def _require_writer(self):
        if self._writer is None:
            raise SourceError("larkbase: chưa có scope bitable:app — tạm dùng MemoryStore")
        return self._writer

    def upsert(self, table: str, records: list) -> int:
        return self._require_writer().upsert(_table_id(table), records)

    def all(self, table: str) -> list:
        return self._require_writer().all(_table_id(table))

    def mark_synced(self, table: str, when: datetime) -> None:
        self._require_writer().mark_synced(table, when)

    def last_synced_at(self, table: str) -> datetime | None:
        return self._require_writer().last_synced_at(table)
