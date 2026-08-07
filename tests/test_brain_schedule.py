"""Test lịch chạy hàng tuần của LSR Brain runner (Chủ nhật 20h giờ VN)."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SCRIPT = (Path(__file__).resolve().parents[1]
           / "infra" / "lsr-platform" / "lsr_brain" / "runner.py")
TZ = timezone(timedelta(hours=7))


def _load():
    spec = importlib.util.spec_from_file_location("brain_runner", _SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


runner = _load()


def _next_run(now):
    return now + timedelta(seconds=runner.seconds_until_next_run(now))


def test_chạy_vào_chủ_nhật_20h():
    # 2026-08-05 là thứ Tư (weekday=2) -> Chủ nhật gần nhất là 09/08, 20:00
    now = datetime(2026, 8, 5, 10, 0, tzinfo=TZ)
    assert now.weekday() == 2
    nxt = _next_run(now)
    assert nxt.weekday() == 6 and nxt.hour == 20
    assert nxt.day == 9


def test_chủ_nhật_trước_giờ_chạy_thì_chạy_trong_ngày():
    now = datetime(2026, 8, 9, 8, 0, tzinfo=TZ)   # Chủ nhật 8h
    nxt = _next_run(now)
    assert nxt.day == 9 and nxt.hour == 20


def test_chủ_nhật_sau_giờ_chạy_thì_dời_sang_tuần_sau():
    now = datetime(2026, 8, 9, 21, 0, tzinfo=TZ)  # Chủ nhật 21h (đã qua 20h)
    nxt = _next_run(now)
    assert nxt.weekday() == 6 and (nxt - now).days == 6  # tuần kế


def test_khoảng_chờ_không_bao_giờ_âm():
    for day in range(1, 15):
        now = datetime(2026, 8, day, 20, 0, tzinfo=TZ)
        assert runner.seconds_until_next_run(now) > 0
