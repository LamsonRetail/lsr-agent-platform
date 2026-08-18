"""Listener Lark — nhận @mention trong nhóm và trả lời câu hỏi về tồn kho.

Dùng long connection (WebSocket) nên KHÔNG cần domain public / webhook URL.
Yêu cầu trên Lark Developer Console:
  - Scope: im:message.group_at_msg (nhận tin @bot), im:message (gửi trả lời)
  - Events & Callbacks: Subscription mode = persistent connection,
    đăng ký sự kiện ``im.message.receive_v1``

Chạy:
    python bot.py --excel "<file excel>"            # DRY_RUN mặc định: chỉ log
    DRY_RUN=false python bot.py --excel "<file>"    # trả lời thật vào nhóm

Dữ liệu excel được nạp lại mỗi lần có câu hỏi để luôn phản ánh file mới nhất.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re

import lark_oapi as lark
import yaml
from dotenv import find_dotenv, load_dotenv

from inventory_days import load_excel_skus
from qa import answer

logger = logging.getLogger("inventory-bot")


def _load_source_cfg(config_path: str, excel_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    cfg = dict(next(c for c in config["sources"].values() if c.get("data_source") == "excel"))
    cfg["_excel_path"] = excel_path
    return cfg


def _strip_mentions(text: str) -> str:
    """Bỏ phần @_user_1 mà Lark chèn vào khi mention bot."""
    return re.sub(r"@_user_\d+", " ", text).strip()


def _extract_text(event) -> str:
    """Lấy nội dung text từ message event (bỏ qua ảnh/file...)."""
    msg = event.event.message
    if msg.message_type != "text":
        return ""
    try:
        return _strip_mentions(json.loads(msg.content).get("text", ""))
    except (json.JSONDecodeError, AttributeError):
        return ""


def build_handler(client: lark.Client, source_cfg: dict, *, dry_run: bool):
    def on_message(data) -> None:
        text = _extract_text(data)
        chat_id = data.event.message.chat_id
        if not text:
            return

        logger.info("Câu hỏi từ %s: %s", chat_id, text)
        try:
            reply = answer(text, load_excel_skus(source_cfg))
        except Exception:  # noqa: BLE001 — không để 1 câu hỏi lỗi làm chết listener
            logger.exception("Lỗi khi tra dữ liệu")
            reply = "Xin lỗi, mình gặp lỗi khi tra dữ liệu tồn kho. Bạn thử lại sau nhé."

        if dry_run:
            logger.info("[DRY_RUN] Sẽ trả lời:\n%s", reply)
            return

        from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

        resp = client.im.v1.message.create(
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("text")
                .content(json.dumps({"text": reply}, ensure_ascii=False))
                .build()
            )
            .build()
        )
        if not resp.success():
            logger.error("Gửi trả lời thất bại: %s %s", resp.code, resp.msg)

    return on_message


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="../config/thresholds.yaml")
    parser.add_argument("--excel", required=True)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv(find_dotenv(usecwd=True))

    app_id = os.environ.get("LARK_APP_ID_INVENTORY") or os.environ["LARK_APP_ID"]
    app_secret = os.environ.get("LARK_APP_SECRET_INVENTORY") or os.environ["LARK_APP_SECRET"]
    dry_run = os.environ.get("DRY_RUN", "true").lower() != "false"

    source_cfg = _load_source_cfg(args.config, args.excel)
    # Nạp thử một lần để lỗi cấu hình lộ ra ngay, không đợi tới câu hỏi đầu tiên.
    logger.info("Đã nạp %d SKU từ excel.", len(load_excel_skus(source_cfg)))

    # SDK mặc định trỏ Feishu (open.feishu.cn); app của LamsonRetail nằm trên
    # LarkSuite quốc tế nên phải chỉ định domain, nếu không WS báo "Incorrect domain name".
    domain = os.environ.get("LARK_DOMAIN", lark.LARK_DOMAIN)

    client = lark.Client.builder().app_id(app_id).app_secret(app_secret).domain(domain).build()
    handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(build_handler(client, source_cfg, dry_run=dry_run))
        .build()
    )

    ws = lark.ws.Client(app_id, app_secret, event_handler=handler,
                        domain=domain, log_level=lark.LogLevel.INFO)
    logger.info("Kết nối Lark (DRY_RUN=%s) — @mention bot trong nhóm để hỏi.", dry_run)
    ws.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
