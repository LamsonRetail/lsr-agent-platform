"""Nơi chứa dữ liệu đã chuẩn hoá (FIN-HUB).

`MemoryStore` dùng cho test và chế độ dữ liệu giả. `LarkBaseStore` (trong
sources/larkbase.py) là bản thật, ghi ra Lark Base cho squad xem — cùng giao diện nên
đổi qua lại không phải sửa sync.py hay query.py.

Ba tính chất bắt buộc, đừng làm mất khi implement bản thật:
  • Upsert theo natural_key: chạy đồng bộ hai lần không nhân đôi dòng (B6).
  • Upsert KHÔNG BAO GIỜ xoá. Nguồn rỗng thì dữ liệu cũ vẫn còn nguyên (B7).
  • Mốc đồng bộ lưu riêng, không suy ra từ dữ liệu. "Đồng bộ xong nhưng 0 dòng" phải
    phân biệt được với "chưa đồng bộ lần nào" (C2).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class Store(ABC):
    @abstractmethod
    def upsert(self, table: str, records: list) -> int:
        """Ghi/cập nhật theo natural_key. Trả số bản ghi đã ghi."""

    @abstractmethod
    def all(self, table: str) -> list:
        """Toàn bộ bản ghi của một bảng. Bảng chưa có dữ liệu thì trả list rỗng."""

    @abstractmethod
    def mark_synced(self, table: str, when: datetime) -> None:
        """Ghi nhận bảng vừa được đồng bộ, kể cả khi nguồn trả về 0 dòng."""

    @abstractmethod
    def last_synced_at(self, table: str) -> datetime | None:
        """Mốc đồng bộ mới nhất. None = chưa đồng bộ lần nào."""


class MemoryStore(Store):
    def __init__(self) -> None:
        self._rows: dict[str, dict[tuple, object]] = {}
        self._synced: dict[str, datetime] = {}

    def upsert(self, table: str, records: list) -> int:
        bucket = self._rows.setdefault(table, {})
        for record in records:
            bucket[record.natural_key] = record
        return len(records)

    def all(self, table: str) -> list:
        return list(self._rows.get(table, {}).values())

    def mark_synced(self, table: str, when: datetime) -> None:
        current = self._synced.get(table)
        if current is None or when > current:
            self._synced[table] = when

    def last_synced_at(self, table: str) -> datetime | None:
        return self._synced.get(table)
