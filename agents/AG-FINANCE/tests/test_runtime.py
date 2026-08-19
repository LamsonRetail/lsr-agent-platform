"""Công tắc dữ liệu giả / dữ liệu thật, và hợp đồng của Store."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from data_hub import runtime
from data_hub.sources.base import SourceError
from data_hub.sources.fake import fake_gsheet
from data_hub.store import MemoryStore


@pytest.fixture(autouse=True)
def _clear_hub_cache():
    runtime.hub.cache_clear()
    yield
    runtime.hub.cache_clear()


def test_che_do_gia_dong_bo_ngay_khi_khoi_dong(monkeypatch):
    monkeypatch.setenv("FIN_FAKE_DATA", "1")
    store = runtime.hub()

    assert store.all("receivable")
    assert store.last_synced_at("receivable") is not None


def test_khong_bat_che_do_gia_thi_khong_am_tham_dung_du_lieu_gia(monkeypatch):
    """Thiếu credential phải báo lỗi rõ. Số giả lọt ra ngoài còn tệ hơn không trả lời."""
    monkeypatch.delenv("FIN_FAKE_DATA", raising=False)
    store = runtime.hub()

    with pytest.raises(SourceError):
        store.all("receivable")


@pytest.mark.parametrize("value,expected", [("1", True), ("true", True), ("YES", True),
                                            ("0", False), ("", False)])
def test_doc_co_bat_che_do_gia(monkeypatch, value, expected):
    monkeypatch.setenv("FIN_FAKE_DATA", value)
    assert runtime.fake_mode() is expected


def test_upsert_theo_natural_key_khong_nhan_doi():
    store = MemoryStore()
    records = fake_gsheet().fetch("receivable").records

    store.upsert("receivable", records)
    store.upsert("receivable", records)

    assert len(store.all("receivable")) == len(records)


def test_upsert_khong_bao_gio_xoa_du_lieu_cu():
    store = MemoryStore()
    store.upsert("receivable", fake_gsheet().fetch("receivable").records)
    before = len(store.all("receivable"))

    store.upsert("receivable", [])

    assert len(store.all("receivable")) == before


def test_moc_dong_bo_khong_bi_lui_ve_qua_khu():
    store = MemoryStore()
    now = datetime.now(timezone.utc)
    store.mark_synced("receivable", now)
    store.mark_synced("receivable", now - timedelta(days=1))

    assert store.last_synced_at("receivable") == now
