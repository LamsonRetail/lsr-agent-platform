"""AG-OPS — platform agent canh vận hành (P7).

Chu kỳ: đọc /v1/self/ops/snapshot → so ngưỡng → ĐỀ XUẤT hành động qua HITL.
Nguyên tắc: rủi ro thấp (báo động, replay DLQ) tự chạy + ghi log; rủi ro cao
(tắt agent, rollback version) phải người duyệt. AG-OPS KHÔNG tự duyệt việc của mình.

Env: LSR_PLATFORM_URL, LSR_AGENT_TOKEN (của AG-OPS), OPS_INTERVAL_SECS,
     OPS_DLQ_THRESHOLD, OPS_ERR_THRESHOLD, OPS_POOL_MIN
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
import urllib.error

PLATFORM = os.environ.get("LSR_PLATFORM_URL", "http://platform_api:8090").rstrip("/")
TOKEN = os.environ.get("LSR_AGENT_TOKEN", "")
INTERVAL = int(os.environ.get("OPS_INTERVAL_SECS", "300"))
DLQ_TH = int(os.environ.get("OPS_DLQ_THRESHOLD", "5"))
ERR_TH = int(os.environ.get("OPS_ERR_THRESHOLD", "20"))
POOL_MIN = int(os.environ.get("OPS_POOL_MIN", "1"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ag-ops")


def api(method: str, path: str, payload=None, timeout=30):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(PLATFORM + path, data=data, method=method, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read().decode()
        return json.loads(b) if b else {}


def propose(action: str, params: dict, risk: str, reason: str) -> None:
    try:
        r = api("POST", "/v1/self/actions/propose",
                {"action": action, "params": params, "risk": risk, "reason": reason})
        log.info("đề xuất %s (%s) → #%s [%s]", action, risk, r.get("id"), r.get("status"))
    except Exception as exc:
        log.warning("không gửi được đề xuất %s: %s", action, exc)


def diagnose(snap: dict) -> list[tuple]:
    """Suy luận từ snapshot → danh sách (action, params, risk, reason)."""
    out = []
    jobs = snap.get("jobs") or {}
    dlq = int(jobs.get("dlq", 0))
    if dlq >= DLQ_TH:
        worst = (snap.get("dlq_by_agent") or [{}])[0]
        who = worst.get("agent_id") or "?"
        out.append(("alert", {"message": f"DLQ đang có {dlq} job (nhiều nhất: {who} — "
                                         f"{worst.get('n', 0)} job). Kiểm tra consumer của agent này."},
                    "low", f"DLQ {dlq} ≥ ngưỡng {DLQ_TH}"))
        # Agent chiếm phần lớn DLQ → đề xuất tạm dừng định tuyến (rủi ro cao, cần duyệt)
        if worst.get("n", 0) >= max(DLQ_TH, dlq * 0.8):
            out.append(("pause_routing", {"agent_id": who}, "high",
                        f"{who} chiếm {worst.get('n')}/{dlq} job DLQ — nghi consumer hỏng"))

    pool = {p["kind"]: p for p in (snap.get("credential_pool") or [])}
    sub = pool.get("subscription") or {}
    if sub and int(sub.get("usable", 0)) <= POOL_MIN:
        out.append(("alert", {"message": f"⚠️ Pool subscription chỉ còn "
                                         f"{sub.get('usable')}/{sub.get('total')} account khả dụng — "
                                         f"nạp thêm trước khi rơi xuống API."},
                    "low", "pool sắp cạn"))

    silent = snap.get("silent_agents") or []
    if silent:
        names = ", ".join(s["agent_id"] for s in silent[:5])
        out.append(("alert", {"message": f"Agent im lặng >24h: {names}"}, "low",
                    f"{len(silent)} agent không có telemetry"))

    errs = snap.get("connector_errors_24h") or []
    for e in errs:
        if int(e.get("n", 0)) >= ERR_TH:
            out.append(("alert", {"message": f"Connector {e['connector_id']} lỗi {e['n']} lần/24h"},
                        "low", "connector lỗi nhiều"))
    return out


def main() -> None:
    if not TOKEN:
        log.error("thiếu LSR_AGENT_TOKEN cho AG-OPS — không chạy được")
    log.info("AG-OPS khởi động (mỗi %ss) → %s", INTERVAL, PLATFORM)
    seen: dict = {}
    while True:
        try:
            snap = api("GET", "/v1/self/ops/snapshot")
            actions = diagnose(snap)
            for action, params, risk, reason in actions:
                key = f"{action}:{json.dumps(params, sort_keys=True)[:80]}"
                # Chống spam: cùng một vấn đề chỉ đề xuất lại sau 1 giờ.
                if time.time() - seen.get(key, 0) < 3600:
                    continue
                seen[key] = time.time()
                propose(action, params, risk, reason)
            if not actions:
                log.info("ổn định — jobs=%s, pending=%s", snap.get("jobs"),
                         snap.get("pending_actions"))
        except urllib.error.HTTPError as e:
            log.warning("snapshot lỗi %s: %s", e.code, e.read().decode()[:120])
        except Exception as exc:
            log.warning("vòng lặp lỗi: %s", exc)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
