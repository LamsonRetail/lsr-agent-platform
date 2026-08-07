"""Minh Anh — Lark long-connection listener (WebSocket outbound, không cần public URL).

Kết nối tới Lark bằng lark-oapi, nhận event (im.message.receive_v1...) và dispatch
sang workflow. Mặc định DRY_RUN=true: CHỈ LOG, không gửi tin nhắn nào (an toàn cho
tới khi được duyệt).
"""

from __future__ import annotations

import json
import logging
import os

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

APP_ID = os.environ["MINH_ANH_LARK_APP_ID"]
APP_SECRET = os.environ["MINH_ANH_LARK_APP_SECRET"]
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"
# LarkSuite quốc tế (open.larksuite.com). Đổi sang lark.FEISHU_DOMAIN nếu dùng Feishu.
DOMAIN = os.environ.get("LARK_DOMAIN_CONST", "LARK")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("minh-anh")


def on_message(data: P2ImMessageReceiveV1) -> None:
    """Nhận tin nhắn gửi cho Minh Anh."""

    try:
        msg = data.event.message
        content = msg.content or ""
        text = ""
        try:
            text = json.loads(content).get("text", "")
        except Exception:
            text = content
        mtype = getattr(msg, "message_type", "?")
        chat = getattr(msg, "chat_id", "?")
        log.info("📩 message | chat=%s | type=%s | text=%r", chat, mtype, text[:120])

        # Bot CHỈ nhận event từ chat/meeting nó được add vào (tenant permission) →
        # gate tự nhiên: ở đây chỉ định tuyến theo loại nội dung.
        RECORDING_TYPES = {"audio", "media", "file"}
        if mtype in RECORDING_TYPES:
            log.info("🎙️  Recording trong chat %s → cần TRANSCRIPT + PROCESS (Minh Anh phụ trách).", chat)
            if DRY_RUN:
                log.info("DRY_RUN: bỏ qua transcript. Bật thật: DRY_RUN=false.")
                return
            # TODO(runtime thật): download media (Lark im file) → TranscribeClient
            #   (Whisper) → draft_minutes → LLM trích key_points → ask_confirm.
        elif mtype == "text" and text.strip().lower() in {"confirm", "chốt", "duyệt"}:
            log.info("✅ Owner confirm biên bản ở chat %s → tạo task + lưu meeting-notes.", chat)
            if DRY_RUN:
                log.info("DRY_RUN: bỏ qua on_confirm.")
                return
            # TODO(runtime thật): MinhAnhBot.on_confirm(minutes) — tạo task + index.
        else:
            log.info("Bỏ qua (không phải recording/không phải lệnh confirm).")
    except Exception as exc:  # không để lỗi làm rớt listener
        log.exception("Lỗi xử lý message: %s", exc)


def on_bot_added(data) -> None:
    """Minh Anh được THÊM vào một chat/cuộc họp → sẽ phụ trách biên bản chat đó."""

    try:
        chat = getattr(getattr(data, "event", None), "chat_id", "?")
        log.info("➕ Minh Anh được thêm vào chat/meeting %s → sẽ phụ trách biên bản.", chat)
        if DRY_RUN:
            log.info("DRY_RUN: không gửi lời chào.")
            return
        # TODO(runtime thật): gửi lời chào + hướng dẫn share recording để viết biên bản.
    except Exception as exc:
        log.exception("Lỗi xử lý bot_added: %s", exc)


def on_bot_removed(data) -> None:
    try:
        chat = getattr(getattr(data, "event", None), "chat_id", "?")
        log.info("➖ Minh Anh bị gỡ khỏi chat %s → ngừng phụ trách.", chat)
    except Exception as exc:
        log.exception("Lỗi xử lý bot_removed: %s", exc)


def main() -> None:
    builder = lark.EventDispatcherHandler.builder("", "").register_p2_im_message_receive_v1(on_message)
    # Sự kiện bot được thêm/gỡ khỏi chat/meeting (nếu SDK hỗ trợ trong phiên bản này).
    for name, fn in (
        ("register_p2_im_chat_member_bot_added_v1", on_bot_added),
        ("register_p2_im_chat_member_bot_deleted_v1", on_bot_removed),
    ):
        reg = getattr(builder, name, None)
        if reg:
            builder = reg(fn)
        else:
            log.warning("SDK chưa có %s — bỏ qua (message vẫn nhận bình thường).", name)
    handler = builder.build()
    domain = lark.LARK_DOMAIN if DOMAIN.upper() == "LARK" else lark.FEISHU_DOMAIN
    client = lark.ws.Client(
        APP_ID, APP_SECRET,
        event_handler=handler,
        domain=domain,
        log_level=lark.LogLevel.INFO,
    )
    log.info("Minh Anh listener khởi động (DRY_RUN=%s, domain=%s)...", DRY_RUN, DOMAIN)
    client.start()  # blocking, tự reconnect


if __name__ == "__main__":
    main()
