"""Trả lời câu hỏi số liệu từ FIN-HUB. Hương.

Luật đã chốt, đừng đổi khi implement:
  • Kiểm quyền TRƯỚC khi truy vấn, không phải sau (shared/auth.py).
  • Mọi kết quả mang theo synced_at. Câu trả lời không có mốc thời gian là câu trả lời sai.
  • Bảng chưa có dữ liệu → value=None. KHÔNG trả Decimal(0) (C2).
  • Dữ liệu cũ hơn ngưỡng → vẫn trả nhưng đánh dấu stale kèm ngày (C3).
  • Câu hỏi thiếu kỳ hoặc phạm vi → ask.py hỏi lại, tầng này không tự mặc định (C4).
  • Cùng hoá đơn ở hai nguồn: số khớp thì cộng MỘT lần (C8), số lệch thì LOẠI khỏi tổng và
    báo đã loại mấy cái (C9). Không bao giờ tự chọn nguồn nào đáng tin hơn.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from .store import Store
from .sync import Discrepancy, business_key, find_discrepancies

DEFAULT_STALE_AFTER_HOURS = 24


def stale_after_hours(table: str) -> int:
    """Ngưỡng coi số là cũ, cấu hình riêng từng bảng.

    Công nợ hôm qua là số cũ; doanh thu chốt theo tháng thì để một tháng vẫn đúng. Một ngưỡng
    chung cho mọi bảng sẽ hoặc cảnh báo sai, hoặc bỏ sót — nên FIN_STALE_HOURS_<BẢNG>.
    """
    raw = os.getenv(f"FIN_STALE_HOURS_{table.upper()}", "").strip()
    try:
        return int(raw) if raw else DEFAULT_STALE_AFTER_HOURS
    except ValueError:
        return DEFAULT_STALE_AFTER_HOURS


@dataclass(frozen=True)
class Figure:
    """Một con số trả về người dùng, kèm đủ ngữ cảnh để không bị hiểu sai."""

    value: Decimal | None          # None = không có dữ liệu, khác hoàn toàn với Decimal(0)
    label: str
    synced_at: datetime | None
    is_stale: bool = False
    sources: tuple[str, ...] = ()
    count: int = 0                 # số bản ghi đã cộng vào value
    excluded: int = 0              # số bản ghi bị loại vì các nguồn lệch nhau (C9)
    discrepancy: str = ""          # rỗng nếu các nguồn khớp nhau

    @property
    def has_data(self) -> bool:
        return self.value is not None


def _stale_state(store: Store, table: str) -> tuple[datetime | None, bool]:
    synced_at = store.last_synced_at(table)
    if synced_at is None:
        return None, False
    age = datetime.now(timezone.utc) - synced_at
    return synced_at, age.total_seconds() > stale_after_hours(table) * 3600


def _dedupe(table: str, records: list[object]) -> tuple[list[object], list[Discrepancy]]:
    """Gộp cùng một hoá đơn từ nhiều nguồn thành một bản ghi, tách riêng phần đang lệch.

    Bản ghi đang lệch KHÔNG nằm trong nhóm để cộng — xem C9.
    """
    conflicts = find_discrepancies(table, records)
    bad_keys = {disc.key for disc in conflicts}

    kept: dict[tuple, object] = {}
    for record in records:
        key = business_key(table, record)
        if key in bad_keys:
            continue
        kept.setdefault(key, record)      # các nguồn khớp nhau → lấy một bản, cộng một lần
    return list(kept.values()), conflicts


def _figure(
    store: Store, table: str, label: str, rows: list[object], picked: list[object],
    conflicts: list[Discrepancy], field: str,
) -> Figure:
    synced_at, is_stale = _stale_state(store, table)
    if not rows:
        # Bảng chưa có dòng nào: không có dữ liệu, không phải bằng 0 (C2).
        return Figure(value=None, label=label, synced_at=synced_at, is_stale=is_stale)
    return Figure(
        value=sum((getattr(r, field) for r in picked), Decimal(0)),
        label=label,
        synced_at=synced_at,
        is_stale=is_stale,
        sources=tuple(sorted({r.prov.source for r in rows})),
        count=len(picked),
        excluded=len({d.key for d in conflicts}),
        discrepancy=_describe_excluded(conflicts),
    )


def _describe_excluded(conflicts: list[Discrepancy]) -> str:
    if not conflicts:
        return ""
    by_key: dict[tuple, list[str]] = {}
    for disc in conflicts:
        by_key.setdefault(disc.key, []).append(disc.field_note)
    listed = list(by_key.items())[:3]
    detail = "; ".join(f"{'/'.join(key)} — {', '.join(notes)}" for key, notes in listed)
    return f"Đã loại {len(by_key)} bản ghi khỏi tổng vì các nguồn lệch nhau: {detail}"


def outstanding_receivable(
    store: Store, *, overdue_days: int | None = None, as_of: date | None = None
) -> Figure:
    """Công nợ phải thu còn lại, lọc theo tuổi nợ nếu có (C1)."""
    return _outstanding(store, "receivable", "công nợ phải thu", overdue_days, as_of)


def outstanding_payable(
    store: Store, *, overdue_days: int | None = None, as_of: date | None = None
) -> Figure:
    return _outstanding(store, "payable", "công nợ phải trả", overdue_days, as_of)


def _outstanding(
    store: Store, table: str, label: str, overdue_days: int | None, as_of: date | None
) -> Figure:
    rows = store.all(table)
    picked, conflicts = _dedupe(table, rows)

    if overdue_days is not None:
        today = as_of or datetime.now(timezone.utc).date()
        label = f"{label} quá hạn trên {overdue_days} ngày"

        def overdue(record) -> bool:
            return (today - record.due_date).days > overdue_days

        picked = [r for r in picked if overdue(r)]
        # Chỉ báo "đã loại" những hoá đơn lệch mà cũng thuộc phạm vi câu hỏi.
        conflicts = [
            d for d in conflicts
            if any(overdue(r) for r in rows if business_key(table, r) == d.key)
        ]

    picked = [r for r in picked if r.outstanding != 0]
    return _figure(store, table, label, rows, picked, conflicts, "outstanding")


def revenue(
    store: Store, *, period: str, channel: str | None = None, store_code: str | None = None
) -> Figure:
    return _periodic(store, "revenue", "doanh thu", period, channel=channel, store_code=store_code)


def expense(
    store: Store, *, period: str, account_code: str | None = None, department: str | None = None
) -> Figure:
    return _periodic(
        store, "expense", "chi phí", period, account_code=account_code, department=department
    )


def _periodic(store: Store, table: str, label: str, period: str, **filters) -> Figure:
    rows = store.all(table)
    picked, conflicts = _dedupe(table, rows)

    picked = [r for r in picked if r.period == period]
    for field, wanted in filters.items():
        if wanted:
            picked = [r for r in picked if _matches(getattr(r, field, ""), wanted)]

    parts = [label, f"kỳ {period}"] + [str(v) for v in filters.values() if v]
    conflicts = [d for d in conflicts if d.key[0] == period]
    return _figure(store, table, " ".join(parts), rows, picked, conflicts, "amount")


def _matches(actual: str, wanted: str) -> bool:
    return str(actual).strip().lower() == str(wanted).strip().lower()


def profit_loss(store: Store, *, period: str) -> Figure:
    """Lãi lỗ = revenue - expense, tính lúc truy vấn.

    KHÔNG lưu thành bảng riêng, để hệ thống không bao giờ có hai con số lãi lỗ lệch nhau.
    """
    rev = revenue(store, period=period)
    exp = expense(store, period=period)
    if rev.value is None or exp.value is None:
        return Figure(value=None, label=f"lãi lỗ kỳ {period}", synced_at=rev.synced_at)
    return Figure(
        value=rev.value - exp.value,
        label=f"lãi lỗ kỳ {period}",
        synced_at=min(d for d in (rev.synced_at, exp.synced_at) if d),
        is_stale=rev.is_stale or exp.is_stale,
        sources=tuple(sorted(set(rev.sources) | set(exp.sources))),
        excluded=rev.excluded + exp.excluded,
        discrepancy="; ".join(n for n in (rev.discrepancy, exp.discrepancy) if n),
    )
