"""Truy vấn số liệu. C1, C2, C3, C8, C9 trong TESTCASES.md — chạy với nguồn giả."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from data_hub import query
from data_hub.sources.fake import FAKE_TODAY, fake_gsheet, fake_misa
from data_hub.store import MemoryStore
from data_hub.sync import run_sync

TODAY = date.fromisoformat(FAKE_TODAY)
TABLES = ["receivable", "payable", "revenue", "expense"]


@pytest.fixture
def store() -> MemoryStore:
    s = MemoryStore()
    run_sync([fake_gsheet(), fake_misa()], TABLES, s)
    return s


def test_c1_cong_no_qua_han_co_so_tong_va_moc_dong_bo(store):
    figure = query.outstanding_receivable(store, overdue_days=30, as_of=TODAY)

    assert figure.value == Decimal("250000000")     # chỉ INV-005 quá hạn 33 ngày
    assert figure.synced_at is not None
    assert figure.sources == ("gsheet", "misa")


def test_c1_hoa_don_chua_den_han_khong_vao_tong_qua_han(store):
    overdue = query.outstanding_receivable(store, overdue_days=30, as_of=TODAY)
    total = query.outstanding_receivable(store, as_of=TODAY)
    assert overdue.value < total.value


def test_c2_chua_dong_bo_lan_nao_thi_tra_none_khong_tra_0():
    figure = query.outstanding_receivable(MemoryStore(), as_of=TODAY)

    assert figure.value is None
    assert figure.value != Decimal(0)
    assert figure.has_data is False
    assert figure.synced_at is None


def test_c2_dong_bo_xong_nhung_bang_rong_van_la_khong_co_du_lieu():
    store = MemoryStore()
    store.mark_synced("revenue", datetime.now(timezone.utc))

    figure = query.revenue(store, period="2026-07")

    assert figure.value is None
    assert figure.synced_at is not None      # đã đồng bộ, nhưng không có dòng nào


def test_c3_du_lieu_cu_qua_nguong_thi_danh_dau_stale(store):
    old = datetime.now(timezone.utc) - timedelta(days=5)
    fresh = MemoryStore()
    fresh.upsert("receivable", store.all("receivable"))
    fresh.mark_synced("receivable", old)

    figure = query.outstanding_receivable(fresh, as_of=TODAY)

    assert figure.is_stale is True
    assert figure.value is not None          # vẫn trả lời, chỉ cảnh báo là số cũ
    assert figure.synced_at == old


def test_c3_du_lieu_moi_thi_khong_bi_danh_dau_stale(store):
    assert query.outstanding_receivable(store, as_of=TODAY).is_stale is False


def test_c3_nguong_stale_cau_hinh_rieng_tung_bang(monkeypatch, store):
    monkeypatch.setenv("FIN_STALE_HOURS_REVENUE", "720")
    assert query.stale_after_hours("revenue") == 720
    assert query.stale_after_hours("receivable") == query.DEFAULT_STALE_AFTER_HOURS

    old = datetime.now(timezone.utc) - timedelta(days=5)
    stale = MemoryStore()
    stale.upsert("revenue", store.all("revenue"))
    stale.upsert("receivable", store.all("receivable"))
    stale.mark_synced("revenue", old)
    stale.mark_synced("receivable", old)

    # Doanh thu chốt theo tháng: 5 ngày vẫn còn dùng được. Công nợ thì không.
    assert query.revenue(stale, period="2026-07").is_stale is False
    assert query.outstanding_receivable(stale, as_of=TODAY).is_stale is True


def test_c3_nguong_sai_dinh_dang_thi_dung_mac_dinh(monkeypatch):
    monkeypatch.setenv("FIN_STALE_HOURS_RECEIVABLE", "khong-phai-so")
    assert query.stale_after_hours("receivable") == query.DEFAULT_STALE_AFTER_HOURS


def test_c8_cung_hoa_don_o_hai_nguon_so_khop_chi_cong_mot_lan(store):
    raw = [r for r in store.all("receivable") if r.invoice_no == "INV-001"]
    assert len(raw) == 2                     # dữ liệu vẫn giữ cả hai nguồn

    figure = query.outstanding_receivable(store, as_of=TODAY)

    # INV-001 (1.234.567) + INV-004 (80tr) + INV-005 (250tr). INV-002 bị loại vì lệch.
    assert figure.value == Decimal("331234567")
    assert figure.count == 3


def test_c9_cung_hoa_don_so_lech_thi_bi_loai_khoi_tong(store):
    figure = query.outstanding_receivable(store, as_of=TODAY)

    assert figure.excluded == 1
    assert "INV-002" in figure.discrepancy
    # Không tự chọn bên nào: cả hai con số đều không được cộng vào.
    assert figure.value != Decimal("331234567") + Decimal("400000000")
    assert figure.value != Decimal("331234567") + Decimal("350000000")


def test_c9_bao_ro_may_ban_ghi_bi_loai_va_vi_sao(store):
    figure = query.outstanding_receivable(store, as_of=TODAY)

    assert "Đã loại 1 bản ghi" in figure.discrepancy
    assert "gsheet=400.000.000" in figure.discrepancy
    assert "misa=350.000.000" in figure.discrepancy


def test_c9_chi_bao_lech_thuoc_pham_vi_cau_hoi(store):
    """INV-002 quá hạn 59 ngày nên nằm trong phạm vi "trên 30 ngày", nhưng không nằm trong
    phạm vi "trên 90 ngày" — câu hỏi thứ hai không được báo là có loại bản ghi."""
    assert query.outstanding_receivable(store, overdue_days=30, as_of=TODAY).excluded == 1
    assert query.outstanding_receivable(store, overdue_days=90, as_of=TODAY).excluded == 0


def test_doanh_thu_theo_ky_va_theo_kenh(store):
    assert query.revenue(store, period="2026-07").value == Decimal("5100000000")
    assert query.revenue(store, period="2026-07", channel="Online").value == Decimal("1800000000")
    assert query.revenue(store, period="2026-06").value == Decimal("3600000000")


def test_ky_khong_co_du_lieu_tra_ve_0_vi_bang_van_co_du_lieu(store):
    """Khác C2: bảng có dữ liệu, chỉ là kỳ này không có dòng nào → 0 là câu trả lời thật."""
    figure = query.revenue(store, period="2026-01")
    assert figure.value == Decimal(0)
    assert figure.has_data is True


def test_chi_phi_am_duoc_giu_nguyen_dau(store):
    assert query.expense(store, period="2026-07").value == Decimal("448000000")


def test_lai_lo_tinh_luc_truy_van(store):
    pl = query.profit_loss(store, period="2026-07")
    rev = query.revenue(store, period="2026-07")
    exp = query.expense(store, period="2026-07")
    assert pl.value == rev.value - exp.value


def test_lai_lo_thieu_mot_ve_thi_khong_bia_ra_so():
    assert query.profit_loss(MemoryStore(), period="2026-07").value is None


def test_cong_no_phai_thu_va_phai_tra_khong_bao_gio_cong_lan_nhau(store):
    receivable = query.outstanding_receivable(store, as_of=TODAY)
    payable = query.outstanding_payable(store, as_of=TODAY)
    assert receivable.value == Decimal("331234567")
    assert payable.value == Decimal("250000000")
