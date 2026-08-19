"""Phân loại ý định trong consumer.py.

Lý do có file này: keyword tiếng Việt rất ngắn, khớp chuỗi con làm "chi phí" trúng keyword
"hi" của nhóm chào hỏi — người hỏi số liệu nhận được lời giới thiệu bot. Các test dưới chốt
lại việc khớp phải theo ranh giới từ.
"""

from __future__ import annotations

import pytest

from consumer import (
    INTENT_FINANCIAL,
    INTENT_MEETING,
    INTENT_OUT_OF_SCOPE,
    INTENT_SMALLTALK,
    classify,
)


@pytest.mark.parametrize(
    "question",
    [
        "chi phí tháng 7/2026",         # "hi" nằm trong "chi"
        "chi phi thang 7/2026",
        "doanh thu tháng 7 bao nhiêu",
        "công nợ quá hạn trên 30 ngày",
        "lãi lỗ tháng 7/2026",
    ],
)
def test_cau_hoi_so_lieu_khong_bi_coi_la_chao_hoi(question):
    assert classify(question, {}) == INTENT_FINANCIAL


@pytest.mark.parametrize("question", ["chào anh", "hi", "hello, anh làm được gì?", "giúp gì được tôi"])
def test_chao_hoi_van_nhan_dung(question):
    assert classify(question, {}) == INTENT_SMALLTALK


def test_ngoai_pham_vi():
    assert classify("hạch toán hoá đơn này vào MISA", {}) == INTENT_OUT_OF_SCOPE


def test_bien_ban_hop():
    assert classify("dựng biên bản cuộc họp hôm nay", {}) == INTENT_MEETING


def test_file_ghi_am_luon_la_bien_ban():
    assert classify("", {"message_type": "audio"}) == INTENT_MEETING


def test_khong_ro_thi_mac_dinh_la_so_lieu():
    """Mặc định phải là số liệu để câu hỏi lạ vẫn đi qua cửa phân quyền, không lọt ra ngoài."""
    assert classify("cái này thế nào", {}) == INTENT_FINANCIAL
