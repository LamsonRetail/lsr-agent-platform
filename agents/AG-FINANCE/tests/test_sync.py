"""Điều phối đồng bộ. B4, B5, B6, B7 trong TESTCASES.md — chạy với nguồn giả."""

from __future__ import annotations

from data_hub.sources.fake import empty_source, fake_gsheet, fake_misa
from data_hub.store import MemoryStore
from data_hub.sync import find_discrepancies, run_sync

TABLES = ["receivable", "payable", "revenue", "expense"]


def _log(logs, source, table):
    return next(log for log in logs if log.source == source and log.table == table)


def test_b4_mot_nguon_chet_khong_lam_dung_nguon_con_lai():
    logs = run_sync([fake_gsheet(healthy=False), fake_misa()], TABLES, MemoryStore())

    assert _log(logs, "gsheet", "receivable").status == "failed"
    assert _log(logs, "gsheet", "receivable").error
    assert _log(logs, "misa", "receivable").status in ("ok", "partial")
    assert _log(logs, "misa", "receivable").rows_written == 3


def test_b4_nguon_chet_van_ghi_nhat_ky_cho_moi_bang():
    logs = run_sync([fake_gsheet(healthy=False)], TABLES, MemoryStore())
    assert {log.table for log in logs} == set(TABLES)
    assert all(log.status == "failed" for log in logs)


def test_dong_hong_khong_lam_mat_cac_dong_lanh():
    logs = run_sync([fake_gsheet()], ["receivable"], MemoryStore())
    log = _log(logs, "gsheet", "receivable")

    assert log.status == "partial"          # 3 dòng tốt + 1 dòng thiếu due_date
    assert log.rows_read == 4
    assert log.rows_written == 3
    assert "due_date" in log.error


def test_b5_hai_nguon_lech_so_thi_giu_ca_hai_va_bao_lech():
    store = MemoryStore()
    logs = run_sync([fake_gsheet(), fake_misa()], TABLES, store)

    inv002 = [r for r in store.all("receivable") if r.invoice_no == "INV-002"]
    assert len(inv002) == 2                                   # giữ cả hai, không hoà giải
    assert {r.prov.source for r in inv002} == {"gsheet", "misa"}

    for source in ("gsheet", "misa"):
        log = _log(logs, source, "receivable")
        assert log.status == "partial"
        assert any("INV-002" in note for note in log.discrepancies)


def test_b5_bao_lech_neu_ro_ca_hai_con_so_va_ten_nguon():
    logs = run_sync([fake_gsheet(), fake_misa()], ["receivable"], MemoryStore())
    notes = " ".join(_log(logs, "gsheet", "receivable").discrepancies)

    assert "gsheet=400.000.000" in notes
    assert "misa=350.000.000" in notes


def test_b5_khong_bao_lech_khi_hai_nguon_khop_nhau():
    logs = run_sync([fake_gsheet(), fake_misa()], ["receivable"], MemoryStore())
    notes = " ".join(_log(logs, "misa", "receivable").discrepancies)
    assert "INV-001" not in notes


def test_b6_dong_bo_hai_lan_khong_nhan_doi_dong():
    store = MemoryStore()
    sources = [fake_gsheet(), fake_misa()]

    run_sync(sources, TABLES, store)
    after_first = {table: len(store.all(table)) for table in TABLES}
    run_sync(sources, TABLES, store)

    assert {table: len(store.all(table)) for table in TABLES} == after_first


def test_b7_nguon_rong_khong_ghi_gi_va_khong_xoa_du_lieu_cu():
    store = MemoryStore()
    run_sync([fake_gsheet()], ["receivable"], store)
    before = len(store.all("receivable"))

    logs = run_sync([empty_source()], ["receivable"], store)

    assert len(store.all("receivable")) == before
    log = _log(logs, "gsheet", "receivable")
    assert log.status == "ok"
    assert log.rows_read == 0
    assert log.rows_written == 0


def test_b7_dong_bo_0_dong_van_ghi_moc_dong_bo():
    """Phân biệt "đồng bộ xong nhưng rỗng" với "chưa đồng bộ lần nào" (C2)."""
    store = MemoryStore()
    assert store.last_synced_at("receivable") is None

    run_sync([empty_source()], ["receivable"], store)

    assert store.last_synced_at("receivable") is not None


def test_khong_phat_hien_lech_khi_chi_co_mot_nguon():
    records = fake_gsheet().fetch("receivable").records
    assert find_discrepancies("receivable", records) == []
