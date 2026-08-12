"""Diễn giải câu hỏi và diễn đạt câu trả lời. C4, C5, C10 và phần diễn đạt của C1-C3."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from data_hub import ask
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


def ask_text(question: str, store) -> str:
    return ask.answer_question(question, store, today=TODAY).text


@pytest.mark.parametrize(
    "question,expected",
    [
        ("công nợ quá hạn trên 30 ngày", "receivable"),
        ("tổng công nợ phải thu", "receivable"),
        ("công nợ phải trả nhà cung cấp", "payable"),
        ("doanh thu tháng 7/2026", "revenue"),
        ("chi phí tháng 7/2026", "expense"),
        ("lãi lỗ tháng 7/2026", "profit_loss"),
        ("thời tiết hôm nay", None),
    ],
)
def test_nhan_dien_loai_so_lieu(question, expected):
    assert ask.detect_metric(question) == expected


@pytest.mark.parametrize(
    "question,expected",
    [
        ("công nợ quá hạn trên 30 ngày", 30),
        ("công nợ quá hạn 60 ngày", 60),
        ("công nợ quá hạn", 0),
        ("tổng công nợ phải thu", None),
    ],
)
def test_nhan_dien_tuoi_no(question, expected):
    assert ask.detect_overdue_days(question) == expected


@pytest.mark.parametrize(
    "question,expected",
    [
        ("doanh thu 2026-07", "2026-07"),
        ("doanh thu tháng 7/2026", "2026-07"),
        ("doanh thu 07/2026", "2026-07"),
        ("doanh thu tháng 12", "2026-12"),
    ],
)
def test_nhan_dien_ky(question, expected):
    assert ask.detect_period(question, today=TODAY).value == expected


def test_khong_neu_ky_thi_khong_doan(store):
    assert ask.detect_period("doanh thu bao nhiêu", today=TODAY) is None


def test_c4_cau_hoi_mo_ho_thi_hoi_lai_khong_tu_doan_thang_nay(store):
    answer = ask.answer_question("doanh thu bao nhiêu", store, today=TODAY)

    assert answer.needs_clarification is True
    assert answer.figure is None
    assert "kỳ" in answer.text
    assert "2026-08" not in answer.text      # không âm thầm mặc định là tháng này


def test_c5_hoi_so_khong_co_trong_nguon_thi_noi_khong_co_khong_bia(store):
    answer = ask.answer_question("lương từng người bao nhiêu", store, today=TODAY)

    assert answer.needs_clarification is True
    assert answer.figure is None
    assert not re.search(r"\d{4,}", answer.text)     # không có con số nào bị bịa ra


def test_c10_neu_thang_khong_neu_nam_thi_noi_ro_ky_da_hieu(store):
    text = ask_text("doanh thu tháng 7", store)

    assert "2026-07" in text
    assert "Tôi hiểu kỳ" in text


def test_c1_cau_tra_loi_co_so_va_co_moc_dong_bo(store):
    text = ask_text("công nợ quá hạn trên 30 ngày", store)

    assert "250.000.000 đ" in text
    assert "mốc đồng bộ" in text
    assert "gsheet" in text and "misa" in text


def test_c2_chua_dong_bo_thi_noi_ro_chua_co_du_lieu():
    text = ask_text("công nợ quá hạn trên 30 ngày", MemoryStore())

    assert "chưa đồng bộ" in text
    assert "không phải bằng 0" in text


def test_c3_so_cu_thi_canh_bao_kem_ngay(store):
    old = datetime.now(timezone.utc) - timedelta(days=5)
    stale = MemoryStore()
    stale.upsert("receivable", store.all("receivable"))
    stale.mark_synced("receivable", old)

    text = ask_text("tổng công nợ phải thu", stale)

    assert "số CŨ" in text
    assert old.astimezone(ask.VN_TZ).strftime("%d/%m/%Y") in text


def test_c9_cau_tra_loi_noi_ro_da_loai_hoa_don_nao(store):
    text = ask_text("tổng công nợ phải thu", store)

    assert "Đã loại 1 bản ghi" in text
    assert "INV-002" in text
    assert "không tự chọn nguồn nào" in text


def test_dinh_dang_tien_theo_kieu_viet_nam():
    assert ask.format_vnd(Decimal("1234567")) == "1.234.567 đ"
    assert ask.format_vnd(Decimal("0")) == "0 đ"
    assert ask.format_vnd(Decimal("-2000000")) == "-2.000.000 đ"


@pytest.mark.parametrize(
    "question,granularity",
    [
        ("chi phí quý 3/2026", "theo quý"),
        ("doanh thu quý 2/2026", "theo quý"),
        ("doanh thu năm 2026", "theo năm"),
        ("doanh thu tuần này", "theo tuần"),
    ],
)
def test_ky_chua_ho_tro_thi_noi_thang_chu_khong_doc_thanh_thang(question, granularity, store):
    """"quý 3/2026" từng bị đọc thành 2026-03 rồi trả "0 đ" — sai mà nghe rất chắc chắn."""
    answer = ask.answer_question(question, store, today=TODAY)

    assert answer.needs_clarification
    assert granularity in answer.text
    assert not re.search(r"\d{4,}", answer.text.replace("7/2026", "")), "không được trả về con số"


def test_thang_kem_nam_thi_khong_bao_la_da_tu_hieu_ky():
    """"tháng 7 năm 2026" đã nêu năm rõ ràng, nói "tôi hiểu kỳ là..." là thừa và gây nghi ngờ."""
    assert ask.detect_period("doanh thu tháng 7 năm 2026") == ask.Period("2026-07")
    assert ask.detect_period("doanh thu tháng 7", today=TODAY).year_assumed is True


def test_cong_no_co_neu_ky_thi_noi_ro_la_khong_loc_theo_ky(store):
    """Công nợ là số dư tại thời điểm. Im lặng bỏ kỳ làm người đọc tưởng số đó của tháng 7."""
    text = ask_text("công nợ phải trả tháng 7/2026", store)

    assert "không lọc theo kỳ" in text
    text_no_period = ask_text("công nợ phải trả", store)
    assert "không lọc theo kỳ" not in text_no_period


def test_qua_han_chung_chung_khong_viet_tren_0_ngay(store):
    text = ask_text("công nợ quá hạn", store)

    assert "quá hạn:" in text
    assert "0 ngày" not in text
