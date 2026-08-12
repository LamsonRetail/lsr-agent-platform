"""Dựng FIN-HUB và chọn nguồn theo cấu hình. Hương.

Đây là chỗ DUY NHẤT quyết định "đang chạy với dữ liệu giả hay dữ liệu thật". consumer.py,
query.py và ask.py không biết và không cần biết.

  FIN_FAKE_DATA=1  → MemoryStore + nguồn giả, đồng bộ ngay khi khởi động. Dùng để demo và
                     chạy test khi chưa có credential.
  mặc định         → LarkBaseStore + nguồn thật. Thiếu credential thì báo lỗi rõ, KHÔNG âm
                     thầm rơi về dữ liệu giả — số giả lọt ra ngoài còn tệ hơn không trả lời.

Chạy đồng bộ tay:  python3 -m data_hub.runtime
"""

from __future__ import annotations

import os
from functools import lru_cache

from .schema import SyncLog
from .sources.base import Source
from .sources.fake import fake_sources
from .sources.gsheet import GoogleSheetSource
from .sources.larkbase import LarkBaseStore
from .sources.misa import MisaAmisSource
from .store import MemoryStore, Store
from .sync import run_sync

TABLES = ("receivable", "payable", "revenue", "expense")


def fake_mode() -> bool:
    return os.getenv("FIN_FAKE_DATA", "").strip().lower() in ("1", "true", "yes")


def build_sources() -> list[Source]:
    if fake_mode():
        return list(fake_sources())
    return [GoogleSheetSource(), MisaAmisSource()]


def build_store() -> Store:
    return MemoryStore() if fake_mode() else LarkBaseStore()


@lru_cache(maxsize=1)
def hub() -> Store:
    """FIN-HUB dùng chung cho cả tiến trình.

    Ở chế độ giả, MemoryStore nằm trong RAM nên phải đồng bộ ngay lúc khởi động, nếu không
    mọi câu hỏi sẽ trả về "chưa đồng bộ lần nào".
    """
    store = build_store()
    if fake_mode():
        run_sync(build_sources(), list(TABLES), store)
    return store


def refresh(store: Store | None = None) -> list[SyncLog]:
    """Chạy một lượt đồng bộ. Trả nhật ký để in ra hoặc báo squad."""
    return run_sync(build_sources(), list(TABLES), store or hub())


def main() -> None:
    print(f"FIN-HUB đồng bộ — fake_mode={fake_mode()}")
    for log in refresh():
        print(
            f"  {log.source:9} {log.table:11} {log.status:8} "
            f"đọc={log.rows_read} ghi={log.rows_written} {log.error[:80]}"
        )
        for note in log.discrepancies:
            print(f"      lệch: {note}")


if __name__ == "__main__":
    main()
