"""AG-EVAL — platform agent chấm chất lượng (P7).

Định kỳ: xem điểm regression của các agent đang chạy prod. Nếu điểm TỤT so với
lần trước → ĐỀ XUẤT rollback version (rủi ro cao → người duyệt).

Không tự chạy golden set thay agent (agent mới có model/tool của nó); AG-EVAL đọc
kết quả đã có + phát hiện xu hướng xấu. Khi cần chấm chủ động, admin chạy
POST /v1/regression/run với agent_version rồi AG-EVAL sẽ so sánh.

Env: LSR_PLATFORM_URL, LSR_AGENT_TOKEN (của AG-EVAL), EVAL_INTERVAL_SECS, EVAL_DROP
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request

PLATFORM = os.environ.get("LSR_PLATFORM_URL", "http://platform_api:8090").rstrip("/")
TOKEN = os.environ.get("LSR_AGENT_TOKEN", "")
INTERVAL = int(os.environ.get("EVAL_INTERVAL_SECS", "3600"))
DROP = float(os.environ.get("EVAL_DROP", "0.1"))     # tụt ≥10% coi là xấu

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ag-eval")


def api(method: str, path: str, payload=None, timeout=30):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(PLATFORM + path, data=data, method=method, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read().decode()
        return json.loads(b) if b else {}


def check_regressions() -> None:
    """So điểm 2 lần chạy gần nhất của từng agent; tụt sâu → đề xuất rollback."""
    runs = api("GET", "/v1/regression/runs?limit=200")
    latest: dict = {}
    for r in runs:                      # API trả mới nhất trước
        tid = r.get("target_id")
        if not tid:
            continue
        latest.setdefault(tid, []).append(r)
    for tid, rs in latest.items():
        if len(rs) < 2:
            continue
        new, old = float(rs[0].get("score") or 0), float(rs[1].get("score") or 0)
        if old > 0 and (old - new) >= DROP:
            api("POST", "/v1/self/actions/propose", {
                "action": "rollback_version",
                "params": {"agent_id": tid, "env": "prod"},
                "risk": "high",
                "reason": f"điểm eval tụt {old:.2f} → {new:.2f} "
                          f"(≥{DROP:.0%}) sau lần publish gần nhất",
            })
            log.info("đề xuất rollback %s (%.2f → %.2f)", tid, old, new)


def main() -> None:
    if not TOKEN:
        log.error("thiếu LSR_AGENT_TOKEN cho AG-EVAL — không chạy được")
    log.info("AG-EVAL khởi động (mỗi %ss) → %s", INTERVAL, PLATFORM)
    while True:
        try:
            check_regressions()
        except Exception as exc:
            log.warning("vòng lặp lỗi: %s", exc)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
