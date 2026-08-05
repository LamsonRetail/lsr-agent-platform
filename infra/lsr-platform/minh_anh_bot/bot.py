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
        log.info(
            "📩 message | chat=%s | type=%s | text=%r",
            getattr(msg, "chat_id", "?"), getattr(msg, "message_type", "?"), text[:120],
        )
        if DRY_RUN:
            log.info("DRY_RUN: bỏ qua (không gửi/không tạo task). Bật thật: DRY_RUN=false.")
            return
        # TODO(runtime thật): dispatch sang rating_agent.meeting.MinhAnhBot:
        #  - nếu là file ghi âm -> transcribe -> draft -> ask_confirm
        #  - nếu text == 'confirm' từ owner -> on_confirm (tạo task + lưu biên bản)
    except Exception as exc:  # không để lỗi làm rớt listener
        log.exception("Lỗi xử lý message: %s", exc)


def main() -> None:
    handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(on_message)
        .build()
    )
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
