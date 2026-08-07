"""LSR Brain runner — chạy consolidate ĐỊNH KỲ HÀNG TUẦN (cuối tuần).

Mặc định: Chủ nhật 20:00 (giờ VN) — cấu hình bằng BRAIN_RUN_DOW / BRAIN_RUN_HOUR.

Mỗi lần chạy:
  1. Lấy danh sách team → đọc second brain từng team.
  2. Chắt lọc tri thức dùng chung (bỏ dữ liệu nhạy cảm) → nộp ứng viên
     `POST /v1/knowledge/items` (tự notify reviewer đúng chuyên môn).
  3. Phát hiện mâu thuẫn với shared beliefs → `POST /v1/knowledge/conflicts`
     (notify agent owner để xác nhận).
KHÔNG tự ghi vào shared brain — mọi thứ phải qua người duyệt.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone

import requests

PLATFORM = os.environ.get("LSR_PLATFORM_URL", "http://platform_api:8090").rstrip("/")
ADMIN = os.environ.get("PLATFORM_ADMIN_TOKEN", "")
DOW = int(os.environ.get("BRAIN_RUN_DOW", "6"))    # 0=Thứ2 ... 6=Chủ nhật
HOUR = int(os.environ.get("BRAIN_RUN_HOUR", "20"))  # giờ VN
RUN_ON_START = os.environ.get("BRAIN_RUN_ON_START", "false").lower() == "true"
TZ = timezone(timedelta(hours=7))  # Asia/Ho_Chi_Minh

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("lsr-brain")

_H = {"Authorization": f"Bearer {ADMIN}", "Content-Type": "application/json"}


def seconds_until_next_run(now: datetime | None = None) -> float:
    """Số giây tới lần chạy kế (thứ DOW, giờ HOUR, giờ VN)."""

    now = now or datetime.now(TZ)
    days = (DOW - now.weekday()) % 7
    target = (now + timedelta(days=days)).replace(
        hour=HOUR, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=7)
    return (target - now).total_seconds()


def _get(path: str, **kw):
    r = requests.get(PLATFORM + path, timeout=20, **kw)
    r.raise_for_status()
    return r.json()


def run_once() -> dict:
    """Một lượt consolidate toàn bộ team. Trả về thống kê."""

    from rating_agent.brain import consolidate_team

    beliefs = _get("/v1/shared-brain").get("beliefs", [])
    teams = _get("/v1/teams")
    stats = {"teams": 0, "candidates": 0, "conflicts": 0, "skipped_sensitive": 0}

    for t in teams:
        tid = t.get("team_id")
        if not tid:
            continue
        brain = _get(f"/v1/teams/{tid}/brain")
        res = consolidate_team(tid, brain.get("context", []), beliefs)
        stats["teams"] += 1
        stats["skipped_sensitive"] += res.skipped_sensitive

        if res.candidates:
            r = requests.post(
                PLATFORM + "/v1/knowledge/items", headers=_H, timeout=30,
                json={"items": [c.as_payload() for c in res.candidates]})
            if r.ok:
                stats["candidates"] += len(res.candidates)
            else:
                log.warning("nộp knowledge lỗi %s: %s", r.status_code, r.text[:200])

        for c in res.conflicts:
            r = requests.post(PLATFORM + "/v1/knowledge/conflicts", headers=_H,
                              timeout=20, json=c.as_payload())
            if r.ok:
                stats["conflicts"] += 1

    log.info("Consolidate xong: %s", stats)
    return stats


def main() -> None:
    log.info("LSR Brain runner: chạy hàng tuần (dow=%s, %sh giờ VN), platform=%s",
             DOW, HOUR, PLATFORM)
    if RUN_ON_START:
        try:
            run_once()
        except Exception as exc:
            log.exception("run_once lỗi: %s", exc)
    while True:
        wait = seconds_until_next_run()
        log.info("Lần chạy kế sau %.1f giờ", wait / 3600)
        time.sleep(wait)
        try:
            run_once()
        except Exception as exc:
            log.exception("run_once lỗi: %s", exc)
        time.sleep(60)  # tránh chạy lặp trong cùng giờ


if __name__ == "__main__":
    main()
