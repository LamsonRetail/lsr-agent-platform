"""Hợp đồng dữ liệu — nhóm B trong TESTCASES.md, phần không cần nguồn thật."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from data_hub.schema import (
    Cashflow,
    Expense,
    Provenance,
    Receivable,
    Revenue,
    SchemaError,
    parse_money,
)

TZ = timezone.utc


def prov(ref: str = "INV-001", source: str = "gsheet") -> Provenance:
    return Provenance(source=source, source_ref=ref, synced_at=datetime(2026, 8, 12, tzinfo=TZ))


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1.234.567", "1234567"),
        ("1.234.567đ", "1234567"),
        ("1,234,567", "1234567"),
        ("1 234 567", "1234567"),
        ("(1.234.567)", "-1234567"),
        ("1234567", "1234567"),
        (1234567, "1234567"),
        (Decimal("1234567"), "1234567"),
        ("1.234.567,50", "1234567.50"),
        ("0", "0"),
    ],
)
def test_b3_parse_money_cac_dinh_dang_viet_nam(raw, expected):
    assert parse_money(raw) == Decimal(expected)


def test_b3_dau_cham_nghin_khong_bi_hieu_la_thap_phan():
    """Sai kiểu này biến 1.234 triệu thành 1,234 — phải chặn."""
    assert parse_money("1.234") == Decimal("1234")


@pytest.mark.parametrize("raw", ["", None, "abc", "1.2.3.4đx", "  "])
def test_b3_gia_tri_khong_doc_duoc_thi_bao_loi(raw):
    with pytest.raises(SchemaError):
        parse_money(raw)


def test_tien_khong_duoc_truyen_dang_float():
    with pytest.raises(SchemaError, match="float"):
        parse_money(1234567.89)


def test_b1_receivable_hop_le():
    r = Receivable(
        partner_code="KH001",
        partner_name="Công ty A",
        invoice_no="INV-001",
        invoice_date=date(2026, 7, 1),
        due_date=date(2026, 7, 31),
        amount=Decimal("10000000"),
        paid_amount=Decimal("4000000"),
        outstanding=Decimal("6000000"),
        prov=prov(),
    )
    assert r.natural_key == ("gsheet", "KH001", "INV-001")
    assert r.currency == "VND"


def test_b1_outstanding_khong_khop_thi_bao_loi():
    with pytest.raises(SchemaError, match="outstanding"):
        Receivable(
            partner_code="KH001",
            partner_name="Công ty A",
            invoice_no="INV-001",
            invoice_date=date(2026, 7, 1),
            due_date=date(2026, 7, 31),
            amount=Decimal("10000000"),
            paid_amount=Decimal("4000000"),
            outstanding=Decimal("9999999"),
            prov=prov(),
        )


def test_b2_thieu_truong_bat_buoc_thi_bao_loi_kem_ten_truong():
    with pytest.raises(SchemaError, match="partner_code"):
        Receivable(
            partner_code="",
            partner_name="Công ty A",
            invoice_no="INV-001",
            invoice_date=date(2026, 7, 1),
            due_date=date(2026, 7, 31),
            amount=Decimal("1"),
            paid_amount=Decimal("0"),
            outstanding=Decimal("1"),
            prov=prov(),
        )


def test_provenance_bat_buoc_co_timezone():
    with pytest.raises(SchemaError, match="timezone"):
        Provenance(source="gsheet", source_ref="x", synced_at=datetime(2026, 8, 12))


def test_provenance_bat_buoc_co_nguon():
    with pytest.raises(SchemaError):
        Provenance(source="", source_ref="x", synced_at=datetime(2026, 8, 12, tzinfo=TZ))


@pytest.mark.parametrize("period", ["2026-13", "2026-00", "26-07", "2026/07", ""])
def test_period_sai_dinh_dang_thi_bao_loi(period):
    with pytest.raises(SchemaError, match="YYYY-MM"):
        Revenue(period=period, channel="online", amount=Decimal("1"), prov=prov())


def test_expense_budget_none_khac_budget_bang_khong():
    """None = không có ngân sách. Decimal(0) = ngân sách bằng 0. Hai chuyện khác nhau."""
    khong_co = Expense(
        period="2026-07", account_code="642", account_name="Chi phí quản lý",
        amount=Decimal("1000"), prov=prov(),
    )
    bang_khong = Expense(
        period="2026-07", account_code="642", account_name="Chi phí quản lý",
        amount=Decimal("1000"), prov=prov(), budget_amount=Decimal("0"),
    )
    assert khong_co.budget_amount is None
    assert bang_khong.budget_amount == Decimal("0")


def test_cashflow_chieu_nam_o_direction_khong_dung_so_am():
    with pytest.raises(SchemaError, match="dương"):
        Cashflow(
            txn_date=date(2026, 7, 1), account_code="1121", direction="out",
            amount=Decimal("-500"), prov=prov(),
        )
    with pytest.raises(SchemaError, match="direction"):
        Cashflow(
            txn_date=date(2026, 7, 1), account_code="1121", direction="ra",
            amount=Decimal("500"), prov=prov(),
        )


def test_natural_key_khac_nguon_thi_khac_nhau():
    """B5: cùng hoá đơn từ hai nguồn là hai bản ghi, không đè lên nhau."""
    common = dict(
        partner_code="KH001", partner_name="A", invoice_no="INV-001",
        invoice_date=date(2026, 7, 1), due_date=date(2026, 7, 31),
        amount=Decimal("100"), paid_amount=Decimal("0"), outstanding=Decimal("100"),
    )
    assert Receivable(**common, prov=prov(source="gsheet")).natural_key != Receivable(
        **common, prov=prov(source="misa")
    ).natural_key
