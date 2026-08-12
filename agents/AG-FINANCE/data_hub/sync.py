"""Điều phối đồng bộ: nguồn → chuẩn hoá → FIN-HUB. Hương.

Luật đã chốt trong docs/DATA_MODEL.md, đừng đổi khi implement:
  • Một nguồn chết KHÔNG làm dừng các nguồn còn lại (B4).
  • Hai nguồn lệch số cùng hoá đơn: giữ CẢ HAI bản ghi, ghi sync_log status=partial,
    báo squad. KHÔNG tự chọn nguồn nào đáng tin hơn (B5).
  • Idempotent: chạy hai lần trên cùng dữ liệu nguồn không được nhân đôi dòng (B6).
  • Nguồn rỗng: ghi sync_log "0 dòng", KHÔNG xoá dữ liệu cũ trên FIN-HUB (B7).
  • healthcheck() mọi nguồn trước khi ghi dòng đầu tiên.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from .schema import SyncLog, format_money
from .sources.base import Source, SourceError
from .store import Store


@dataclass(frozen=True)
class Discrepancy:
    """Cùng một hoá đơn, hai nguồn ra hai con số. Giữ nguyên cả hai, không hoà giải."""

    table: str
    key: tuple                      # khoá nghiệp vụ, KHÔNG gồm tên nguồn
    field: str
    values: dict[str, Decimal]      # {tên nguồn: giá trị}

    @property
    def field_note(self) -> str:
        pairs = ", ".join(f"{src}={format_money(val)}" for src, val in sorted(self.values.items()))
        return f"{self.field}: {pairs}"

    def describe(self) -> str:
        return f"{'/'.join(self.key)} — {self.field_note}"


#: Trường nào coi là "số liệu" để đối chiếu giữa các nguồn, theo từng bảng.
COMPARED_FIELDS: dict[str, tuple[str, ...]] = {
    "receivable": ("amount", "paid_amount", "outstanding"),
    "payable": ("amount", "paid_amount", "outstanding"),
    "revenue": ("amount",),
    "expense": ("amount",),
}


def business_key(table: str, record: object) -> tuple:
    """Khoá nghiệp vụ = natural_key bỏ tên nguồn.

    Cùng hoá đơn ở hai nguồn có natural_key khác nhau (vì có source) nhưng business_key
    giống nhau. Đây là chỗ để phát hiện trùng và phát hiện lệch.
    """
    return tuple(record.natural_key[1:])


def run_sync(sources: list[Source], tables: list[str], store: Store) -> list[SyncLog]:
    """Đồng bộ các bảng từ các nguồn vào FIN-HUB. Trả nhật ký từng (nguồn, bảng)."""
    run_id = uuid.uuid4().hex[:12]
    logs: list[SyncLog] = []
    fetched: dict[str, list[object]] = {table: [] for table in tables}

    for source in sources:
        try:
            source.healthcheck()
        except SourceError as exc:
            # Nguồn này bỏ qua, các nguồn còn lại vẫn chạy (B4).
            logs.extend(_failed_logs(run_id, source.name, tables, str(exc)))
            continue

        for table in tables:
            if table not in source.supported_tables():
                continue
            logs.append(_sync_one(run_id, source, table, store, fetched))

    _attach_discrepancies(logs, fetched)
    return logs


def _sync_one(
    run_id: str, source: Source, table: str, store: Store, fetched: dict[str, list[object]]
) -> SyncLog:
    log = SyncLog(
        run_id=run_id, source=source.name, table=table, started_at=datetime.now(timezone.utc)
    )
    try:
        result = source.fetch(table)
    except SourceError as exc:
        log.status = "failed"
        log.error = str(exc)
        log.finished_at = datetime.now(timezone.utc)
        return log

    log.rows_read = len(result.records) + len(result.errors)
    log.status = result.status
    if result.errors:
        log.error = "; ".join(f"{e.row_ref}: {e.reason}" for e in result.errors)

    # Nguồn rỗng: không ghi gì, không xoá gì, nhưng vẫn đánh mốc đồng bộ (B7 + C2).
    if result.records:
        log.rows_written = store.upsert(table, result.records)
        fetched[table].extend(result.records)
    store.mark_synced(table, datetime.now(timezone.utc))

    log.finished_at = datetime.now(timezone.utc)
    return log


def _failed_logs(run_id: str, source: str, tables: list[str], error: str) -> list[SyncLog]:
    now = datetime.now(timezone.utc)
    return [
        SyncLog(
            run_id=run_id, source=source, table=table, started_at=now, finished_at=now,
            status="failed", error=error,
        )
        for table in tables
    ]


def _attach_discrepancies(logs: list[SyncLog], fetched: dict[str, list[object]]) -> None:
    """Gắn mô tả lệch vào nhật ký của TẤT CẢ nguồn liên quan, không chỉ nguồn đọc sau."""
    for table, records in fetched.items():
        for disc in find_discrepancies(table, records):
            message = f"{table} {disc.describe()}"
            for log in logs:
                if log.table == table and log.source in disc.values:
                    log.discrepancies.append(message)
                    if log.status == "ok":
                        log.status = "partial"


def find_discrepancies(table: str, records: list[object]) -> list[Discrepancy]:
    """Tìm các hoá đơn có số khác nhau giữa các nguồn. Không sửa dữ liệu."""
    fields = COMPARED_FIELDS.get(table, ("amount",))
    grouped: dict[tuple, list[object]] = {}
    for record in records:
        grouped.setdefault(business_key(table, record), []).append(record)

    found: list[Discrepancy] = []
    for key, group in sorted(grouped.items()):
        if len(group) < 2:
            continue
        for field in fields:
            values = {r.prov.source: getattr(r, field) for r in group}
            if len(set(values.values())) > 1:
                found.append(Discrepancy(table=table, key=key, field=field, values=values))
    return found


def conflicted_keys(table: str, records: list[object]) -> set[tuple]:
    """Các hoá đơn đang lệch giữa các nguồn — query.py loại chúng khỏi tổng (C9)."""
    return {disc.key for disc in find_discrepancies(table, records)}
