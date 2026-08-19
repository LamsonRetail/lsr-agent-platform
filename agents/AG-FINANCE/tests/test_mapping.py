"""Chuẩn hoá dòng nguồn → schema. B1, B2, B3 trong TESTCASES.md."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from data_hub.mapping import map_row, normalize_header
from data_hub.schema import Provenance, SchemaError

PROV = Provenance(source="gsheet", source_ref="INV-001", synced_at=datetime.now(timezone.utc))

GOOD_ROW = {
    "Mã KH": "KH-001", "Tên khách hàng": "Công ty A",
    "Số hoá đơn": "INV-001", "Ngày hoá đơn": "01/07/2026", "Ngày đến hạn": "31/07/2026",
    "Giá trị": "1.234.567đ", "Đã thu": "0",
}


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Mã Khách  Hàng", "ma khach hang"),
        ("MA KH", "ma kh"),
        ("ma_kh", "ma kh"),
        ("Số hoá đơn", "so hoa don"),
        ("partner_code", "partner code"),
    ],
)
def test_ten_cot_khac_nhau_van_ve_mot_dang(raw, expected):
    assert normalize_header(raw) == expected


def test_b1_chuan_hoa_mot_dong_cong_no():
    record = map_row("receivable", GOOD_ROW, prov=PROV)

    assert record.partner_code == "KH-001"
    assert record.invoice_no == "INV-001"
    assert record.invoice_date == date(2026, 7, 1)
    assert record.due_date == date(2026, 7, 31)
    assert record.amount == Decimal("1234567")
    assert isinstance(record.amount, Decimal) and not isinstance(record.amount, float)
    assert record.outstanding == Decimal("1234567")


def test_b1_ten_cot_kieu_misa_van_map_duoc():
    row = {
        "ma_kh": "KH-001", "ten_kh": "Công ty A", "so_hoa_don": "INV-001",
        "ngay_hoa_don": "2026-07-01", "ngay_den_han": "2026-07-31",
        "so_tien": "1234567", "da_thu": "0",
    }
    assert map_row("receivable", row, prov=PROV).amount == Decimal("1234567")


def test_b2_thieu_cot_bat_buoc_thi_bao_ro_ten_cot():
    row = {k: v for k, v in GOOD_ROW.items() if k != "Ngày đến hạn"}

    with pytest.raises(SchemaError) as err:
        map_row("receivable", row, prov=PROV)

    assert "due_date" in str(err.value)


def test_b2_khong_tu_dien_gia_tri_mac_dinh_cho_cot_thieu():
    row = {k: v for k, v in GOOD_ROW.items() if k != "Giá trị"}

    with pytest.raises(SchemaError):
        map_row("receivable", row, prov=PROV)


def test_b3_tien_dinh_dang_viet_nam_khong_bi_doc_thanh_1234():
    record = map_row("receivable", GOOD_ROW, prov=PROV)
    assert record.amount == Decimal("1234567")
    assert record.amount != Decimal("1.234")


def test_outstanding_suy_ra_khi_sheet_khong_co_cot_do():
    row = {**GOOD_ROW, "Giá trị": "500.000.000", "Đã thu": "100.000.000"}
    assert map_row("receivable", row, prov=PROV).outstanding == Decimal("400000000")


def test_outstanding_trong_sheet_duoc_ton_trong():
    row = {**GOOD_ROW, "Giá trị": "500.000.000", "Đã thu": "100.000.000",
           "Còn lại": "400.000.000"}
    assert map_row("receivable", row, prov=PROV).outstanding == Decimal("400000000")


def test_payable_dung_ma_ncc_chu_khong_phai_ma_kh():
    row = {
        "Mã NCC": "NCC-001", "Tên nhà cung cấp": "NCC X", "Số hoá đơn": "PO-001",
        "Ngày hoá đơn": "01/07/2026", "Ngày đến hạn": "31/07/2026",
        "Giá trị": "300.000.000", "Đã thanh toán": "50.000.000",
    }
    record = map_row("payable", row, prov=PROV)
    assert record.partner_code == "NCC-001"
    assert record.outstanding == Decimal("250000000")


@pytest.mark.parametrize("raw,expected", [("2026-07", "2026-07"), ("07/2026", "2026-07"),
                                          ("7/2026", "2026-07")])
def test_ky_nhieu_kieu_viet_ve_mot_dang(raw, expected):
    row = {"Kỳ": raw, "Kênh": "Online", "Doanh thu": "1.000.000"}
    assert map_row("revenue", row, prov=PROV).period == expected


def test_bang_chua_ho_tro_thi_bao_ro():
    with pytest.raises(SchemaError, match="chưa hỗ trợ bảng"):
        map_row("cashflow", GOOD_ROW, prov=PROV)
