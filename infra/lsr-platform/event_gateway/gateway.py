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
import time

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

# --- Báo đã nhận: thả emoji lên tin của người hỏi trước khi agent trả lời ----------
# Lark không có "typing indicator" cho bot, nên dấu hiệu duy nhất người dùng thấy được
# là một reaction. Làm ở GATEWAY (không phải trong từng agent) để MỌI agent có ngay,
# và để phản hồi tức thì thay vì chờ agent nghĩ xong.
# Chỉ thả khi platform trả status='queued' — tức tin đã định tuyến tới agent ĐANG BẬT và
# đã vào hàng đợi. Thả cả khi 'unrouted'/'rejected' là hứa suông: người dùng thấy ✅ rồi
# ngồi đợi một câu trả lời không bao giờ tới.
ACK_EMOJI = os.environ.get("LARK_ACK_EMOJI", "OK").strip()   # rỗng = tắt hẳn
API_BASE = os.environ.get("LARK_API_BASE", "https://open.larksuite.com").rstrip("/")
_TOKEN: dict = {"v": "", "exp": 0.0}
_ack_off = False          # tắt sau lỗi cấu hình để không spam log mỗi tin nhắn


def _tenant_token() -> str:
    """tenant_access_token của CHÍNH app này, cache trong process (~2h)."""
    now = time.time()
    if _TOKEN["v"] and now < _TOKEN["exp"]:
        return _TOKEN["v"]
    if not (APP_ID and APP_SECRET):
        return ""
    try:
        d = requests.post(f"{API_BASE}/open-apis/auth/v3/tenant_access_token/internal",
                          json={"app_id": APP_ID, "app_secret": APP_SECRET},
                          timeout=8).json()
    except Exception as exc:
        log.warning("lấy tenant token lỗi: %s", exc)
        return ""
    if d.get("code") != 0:
        log.warning("lấy tenant token bị từ chối: %s %s", d.get("code"), d.get("msg"))
        return ""
    _TOKEN["v"] = d.get("tenant_access_token", "")
    _TOKEN["exp"] = now + int(d.get("expire", 7200)) - 120
    return _TOKEN["v"]


def _ack_react(message_id: str) -> None:
    """Thả emoji báo đã nhận. Best-effort: lỗi thì bỏ qua, KHÔNG chặn luồng trả lời."""
    global _ack_off
    if _ack_off or not (ACK_EMOJI and message_id):
        return
    tok = _tenant_token()
    if not tok:
        return
    try:
        d = requests.post(f"{API_BASE}/open-apis/im/v1/messages/{message_id}/reactions",
                          headers={"Authorization": f"Bearer {tok}",
                                   "Content-Type": "application/json"},
                          json={"reaction_type": {"emoji_type": ACK_EMOJI}},
                          timeout=8).json()
    except Exception as exc:
        log.warning("thả emoji lỗi: %s", exc)
        return
    code = d.get("code")
    if code == 0:
        return
    # Lỗi CẤU HÌNH (thiếu scope im:message.reactions:write_only, emoji không tồn tại)
    # thì tin nào cũng lỗi y hệt → tắt luôn, log đúng một lần kèm cách sửa.
    _ack_off = True
    log.warning("TẮT báo-đã-nhận cho app %s: Lark trả code=%s (%s). "
                "Kiểm scope `im:message.reactions:write_only` (hoặc `im:message`) trong "
                "Developer Console, hoặc đổi LARK_ACK_EMOJI (hiện '%s').",
                APP_ID, code, d.get("msg"), ACK_EMOJI)


def _post_ingest(payload: dict) -> dict:
    """Đẩy 1 sự kiện đã verify vào platform. Best-effort + log rõ.

    Trả body của platform ({job_id, agent_id, status}) để caller biết tin có thật sự
    vào hàng đợi hay không — cần cho việc báo đã nhận.
    """
    try:
        r = requests.post(
            PLATFORM_URL + "/v1/ingest",
            json=payload,
            headers={"Authorization": f"Bearer {INGEST_TOKEN}"},
            timeout=5,
        )
        log.info("ingest %s ch=%s → %s %s", payload.get("event_id"), payload.get("channel"),
                 r.status_code, r.text[:160])
        return r.json() if r.content else {}
    except Exception as exc:
        log.exception("ingest lỗi: %s", exc)
        return {}


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
        res = _post_ingest(payload)
        if res.get("status") == "queued":
            _ack_react(getattr(msg, "message_id", None) or "")
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
    res = _post_ingest({
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
    if res.get("status") == "queued":
        _ack_react(msg.get("message_id") or "")
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
