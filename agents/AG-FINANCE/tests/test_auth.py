"""Nhóm A trong TESTCASES.md — phân quyền. Phải pass trước khi nạp dữ liệu thật."""

from __future__ import annotations

import pytest

from consumer import answer
from shared.auth import DENY_MESSAGE, is_squad_member

SQUAD_EMAIL = "ketoan@lamsonretail.vn"
OUTSIDER_EMAIL = "sales@lamsonretail.vn"


@pytest.fixture
def squad_configured(monkeypatch):
    monkeypatch.setenv("FIN_SQUAD_EMAILS", f"{SQUAD_EMAIL},truongphong@lamsonretail.vn")
    monkeypatch.setenv("FIN_SQUAD_OPEN_IDS", "ou_squad_member")
    monkeypatch.setenv("FIN_SQUAD_CHAT_IDS", "oc_finance_group")


def test_a1_nguoi_ngoai_squad_khong_nhan_duoc_so_lieu(squad_configured):
    reply = answer("doanh thu tháng 7 bao nhiêu", {}, {"sender_email": OUTSIDER_EMAIL})
    assert reply == DENY_MESSAGE
    assert not any(ch.isdigit() for ch in reply), "câu từ chối không được chứa con số nào"


def test_a2_nguoi_trong_squad_khong_bi_tu_choi(squad_configured):
    reply = answer("doanh thu tháng 7 bao nhiêu", {}, {"sender_email": SQUAD_EMAIL})
    assert reply != DENY_MESSAGE


def test_a3_cau_hoi_vo_hai_khong_can_whitelist(squad_configured):
    reply = answer("bot làm được gì", {}, {"sender_email": OUTSIDER_EMAIL})
    assert reply != DENY_MESSAGE
    assert "công nợ" in reply.lower()


def test_a4_whitelist_rong_thi_tu_choi_tat_ca(monkeypatch):
    """Chưa cấu hình nghĩa là từ chối, không phải cho tất cả."""
    for var in ("FIN_SQUAD_EMAILS", "FIN_SQUAD_OPEN_IDS", "FIN_SQUAD_CHAT_IDS"):
        monkeypatch.delenv(var, raising=False)
    assert is_squad_member(email=SQUAD_EMAIL) is False
    assert answer("công nợ quá hạn bao nhiêu", {}, {"sender_email": SQUAD_EMAIL}) == DENY_MESSAGE


def test_a4b_khong_xac_dinh_duoc_nguoi_hoi_thi_tu_choi(squad_configured):
    assert answer("công nợ quá hạn bao nhiêu", {}, {}) == DENY_MESSAGE


def test_nhan_dien_qua_open_id_va_chat_id(squad_configured):
    assert is_squad_member(open_id="ou_squad_member") is True
    assert is_squad_member(chat_id="oc_finance_group") is True
    assert is_squad_member(open_id="ou_nguoi_la") is False


def test_email_khong_phan_biet_hoa_thuong(squad_configured):
    assert is_squad_member(email=SQUAD_EMAIL.upper()) is True


def test_cau_hoi_khong_ro_y_dinh_bi_coi_la_cau_hoi_so_lieu(squad_configured):
    """Phân loại sai phải nghiêng về từ chối, không nghiêng về trả lời."""
    assert answer("cho tôi xem cái kia", {}, {"sender_email": OUTSIDER_EMAIL}) == DENY_MESSAGE


@pytest.mark.parametrize(
    "question",
    ["hạch toán giúp bút toán này", "duyệt chi khoản này", "làm báo cáo thuế quý 2"],
)
def test_e1_e2_tu_choi_viec_ngoai_pham_vi(squad_configured, question):
    reply = answer(question, {}, {"sender_email": SQUAD_EMAIL})
    assert "ngoài phạm vi" in reply.lower()
