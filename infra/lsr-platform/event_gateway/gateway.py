"""LSR Event Gateway — cổng sự kiện HỢP NHẤT (P1).

Mọi sự kiện từ touchpoint (hiện tại: Lark long-connection; sẵn khung webhook) đi qua đây:
  verify (SDK/secret) -> trích event_id/app_id/chat_id/text -> POST /v1/ingest (platform_api).
platform_api lo phần dedupe + route (routing_binding) + enqueue (jobs). Gateway chỉ ACK nhanh.

KHÔNG xử lý nghiệp vụ ở đây — việc đó do consumer (agent) làm khi lấy job.
"""

from __future__ import annotations

import json
import logging
import os
import threading

import requests
import uvicorn
from fastapi import FastAPI, Request

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

PLATFORM_URL = os.environ.get("PLATFORM_URL", "http://platform_api:8090").rstrip("/")
INGEST_TOKEN = os.environ.get("GATEWAY_INGEST_TOKEN") or os.environ.get("PLATFORM_ADMIN_TOKEN", "")
# 1 container = 1 app Lark (long-connection). Chạy thêm app (vd Sawadee HAPAS) = thêm
# 1 service compose với LARK_APP_ID/SECRET riêng. MINH_ANH_* giữ để tương thích cũ.
APP_ID = os.environ.get("LARK_APP_ID") or os.environ.get("MINH_ANH_LARK_APP_ID", "")
APP_SECRET = os.environ.get("LARK_APP_SECRET") or os.environ.get("MINH_ANH_LARK_APP_SECRET", "")
DOMAIN = os.environ.get("LARK_DOMAIN_CONST", "LARK")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("event-gateway")

app = FastAPI(title="LSR Event Gateway")


def _post_ingest(payload: dict) -> None:
    """Đẩy 1 sự kiện đã verify vào platform. Best-effort + log rõ."""
    try:
        r = requests.post(
            PLATFORM_URL + "/v1/ingest",
            json=payload,
            headers={"Authorization": f"Bearer {INGEST_TOKEN}"},
            timeout=5,
        )
        log.info("ingest %s ch=%s → %s %s", payload.get("event_id"), payload.get("channel"),
                 r.status_code, r.text[:160])
    except Exception as exc:
        log.exception("ingest lỗi: %s", exc)


def _content_of(msg) -> dict:
    """Parse content JSON của tin nhắn (text | file | media | audio | image...)."""
    try:
        d = json.loads(getattr(msg, "content", "") or "{}")
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _text_of(msg) -> str:
    content = getattr(msg, "content", "") or ""
    try:
        return json.loads(content).get("text", "") or content
    except Exception:
        return content


def _attachment_fields(content: dict) -> dict:
    """C1: đẩy đủ thông tin file đính kèm (recording, tài liệu) để agent tải được
    qua GET /v1/lark/resource/{message_id}/{file_key} — không cầm app_secret."""
    out = {}
    for k in ("file_key", "file_name", "image_key", "duration"):
        if content.get(k) is not None:
            out[k] = content[k]
    return out


def on_lark_message(data: P2ImMessageReceiveV1) -> None:
    """Nhận tin Lark qua long-connection → chuẩn hoá → ingest."""
    try:
        header = getattr(data, "header", None)
        event_id = getattr(header, "event_id", None)
        msg = data.event.message
        chat_id = getattr(msg, "chat_id", None)
        mtype = getattr(msg, "message_type", "text")
        sender = getattr(getattr(data.event, "sender", None), "sender_id", None)
        open_id = getattr(sender, "open_id", None) if sender else None
        content = _content_of(msg)
        payload = {
            "event_id": event_id or getattr(msg, "message_id", None),
            "channel": "lark",
            "app_id": APP_ID,
            "chat_id": chat_id,
            "reply_to": {"channel": "lark", "chat_id": chat_id, "open_id": open_id,
                         "app_id": APP_ID},
            "payload": {
                "text": _text_of(msg),
                "message_type": mtype,
                "message_id": getattr(msg, "message_id", None),
                "chat_id": chat_id,
                "sender_open_id": open_id,
                **_attachment_fields(content),
            },
        }
        _post_ingest(payload)
    except Exception as exc:
        log.exception("xử lý message Lark lỗi: %s", exc)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app_id": bool(APP_ID), "platform": PLATFORM_URL}


@app.post("/webhook/lark/{app}")
async def webhook_lark(app: str, req: Request) -> dict:
    """Khung webhook cho app dùng chế độ URL (verify challenge + đẩy ingest).

    Long-connection không cần endpoint này; giữ sẵn cho app cấu hình webhook sau.
    """
    body = await req.json()
    if body.get("type") == "url_verification":       # Lark verify URL
        return {"challenge": body.get("challenge")}
    header = body.get("header") or {}
    event = body.get("event") or {}
    msg = event.get("message") or {}
    src_app = header.get("app_id") or app
    open_id = ((event.get("sender") or {}).get("sender_id") or {}).get("open_id")
    try:
        content = json.loads(msg.get("content") or "{}")
        content = content if isinstance(content, dict) else {}
    except Exception:
        content = {}
    _post_ingest({
        "event_id": header.get("event_id"),
        "channel": "lark",
        "app_id": src_app,
        "chat_id": msg.get("chat_id"),
        "reply_to": {"channel": "lark", "chat_id": msg.get("chat_id"),
                     "open_id": open_id, "app_id": src_app},
        "payload": {"text": _text_of_dict(msg), "message_type": msg.get("message_type"),
                    "message_id": msg.get("message_id"), "chat_id": msg.get("chat_id"),
                    "sender_open_id": open_id, **_attachment_fields(content)},
    })
    return {"ok": True}


def _text_of_dict(msg: dict) -> str:
    try:
        return json.loads(msg.get("content") or "{}").get("text", "")
    except Exception:
        return msg.get("content") or ""


def _run_lark_ws() -> None:
    """Long-connection Lark (blocking, tự reconnect) — chạy ở thread nền."""
    if not (APP_ID and APP_SECRET):
        log.warning("Thiếu LARK_APP_ID/SECRET (hoặc MINH_ANH_*) — bỏ qua long-connection Lark.")
        return
    handler = (lark.EventDispatcherHandler.builder("", "")
               .register_p2_im_message_receive_v1(on_lark_message).build())
    domain = lark.LARK_DOMAIN if DOMAIN.upper() == "LARK" else lark.FEISHU_DOMAIN
    client = lark.ws.Client(APP_ID, APP_SECRET, event_handler=handler, domain=domain,
                            log_level=lark.LogLevel.INFO)
    log.info("Gateway long-connection Lark khởi động (app=%s, domain=%s)...", APP_ID[:8], DOMAIN)
    client.start()


@app.on_event("startup")
def _startup() -> None:
    threading.Thread(target=_run_lark_ws, daemon=True).start()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8095)
