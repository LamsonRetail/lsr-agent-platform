"""Minh Anh — CONSUMER (P1).

Trước đây bot tự nghe Lark long-connection. Từ P1, việc NHẬN sự kiện do event_gateway
lo (verify+dedupe+route+enqueue). Minh Anh giờ chỉ là CONSUMER: long-poll lấy job của
AG-MINH-ANH từ platform, xử lý, trả lời qua broker Lark dùng chung (lsr_lark), rồi
báo complete/fail. Nhờ đó Minh Anh tự có: retry/DLQ, quota, audit, kill-switch — giống
mọi agent khác.

DRY_RUN=true (mặc định): chỉ log, không gửi tin/tạo task.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
import urllib.error

PLATFORM = os.environ.get("LSR_PLATFORM_URL", "http://platform_api:8090").rstrip("/")
AGENT_ID = os.environ.get("LSR_AGENT_ID", "AG-MINH-ANH")
TOKEN = os.environ.get("LSR_AGENT_TOKEN", "")
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("minh-anh")

RECORDING_TYPES = {"audio", "media", "file"}
CONFIRM_WORDS = {"confirm", "chốt", "duyệt"}


def _api(method: str, path: str, payload: dict | None = None, timeout: int = 40):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(PLATFORM + path, data=data, method=method, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            b = r.read().decode()
            return json.loads(b) if b else {}
    except urllib.error.HTTPError as e:
        log.warning("API %s %s → %s %s", method, path, e.code, e.read().decode()[:160])
        raise
    except Exception as e:
        log.warning("API %s %s lỗi: %s", method, path, e)
        raise


def _reply(job: dict, text: str) -> None:
    """Trả lời về đúng nơi phát sinh job (reply_to) qua broker Lark dùng chung."""
    reply_to = job.get("reply_to") or {}
    chat_id = reply_to.get("chat_id")
    if DRY_RUN:
        log.info("DRY_RUN: (không gửi) reply → chat=%s: %s", chat_id, text[:120])
        return
    if reply_to.get("channel") == "lark" and chat_id:
        _api("POST", "/v1/lark/send", {"to": chat_id, "to_type": "chat_id", "text": text})


def handle(job: dict) -> None:
    """Xử lý 1 job. Ném exception nếu lỗi để consumer báo fail (→ retry/DLQ)."""
    payload = job.get("payload") or {}
    text = (payload.get("text") or "")
    mtype = payload.get("message_type", "text")
    chat = payload.get("chat_id", "?")
    log.info("▶ job#%s chat=%s type=%s text=%r", job.get("id"), chat, mtype, text[:120])

    if mtype in RECORDING_TYPES:
        log.info("🎙️ Recording → cần transcript + biên bản (Minh Anh phụ trách).")
        # TODO(runtime thật): download media → transcribe → draft minutes → ask confirm.
        _reply(job, "Đã nhận recording, sẽ lên biên bản và gửi lại để xác nhận.")
    elif mtype == "text" and text.strip().lower() in CONFIRM_WORDS:
        log.info("✅ Owner confirm → tạo task + lưu meeting-notes.")
        # TODO(runtime thật): on_confirm(minutes) — tạo task + index.
        _reply(job, "Đã chốt biên bản và tạo task.")
    else:
        log.info("Bỏ qua (không phải recording/không phải lệnh confirm).")


def loop() -> None:
    if not TOKEN:
        log.error("Thiếu LSR_AGENT_TOKEN cho %s — consumer không xác thực được.", AGENT_ID)
    log.info("Minh Anh consumer khởi động (agent=%s, DRY_RUN=%s) → %s", AGENT_ID, DRY_RUN, PLATFORM)
    while True:
        try:
            jobs = _api("GET", "/v1/self/jobs?wait=25&max=1")
        except urllib.error.HTTPError as e:
            if e.code == 403:                     # kill-switch: agent bị deactivate
                log.info("Agent deactivated — nghỉ 30s rồi thử lại.")
                time.sleep(30); continue
            time.sleep(5); continue
        except Exception:
            time.sleep(5); continue
        if not jobs:
            continue                              # long-poll hết hạn, vòng lại
        for job in jobs:
            jid = job.get("id")
            try:
                handle(job)
                _api("POST", f"/v1/self/jobs/{jid}/complete", {"result": {"ok": True}})
            except Exception as exc:
                log.exception("job#%s lỗi → báo fail", jid)
                try:
                    _api("POST", f"/v1/self/jobs/{jid}/fail", {"error": str(exc)[:400]})
                except Exception:
                    pass


if __name__ == "__main__":
    loop()
