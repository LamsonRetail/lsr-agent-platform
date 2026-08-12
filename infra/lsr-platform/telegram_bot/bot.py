"""LSR Admin Bot (Telegram) — kênh trao đổi giữa platform agent và admin.

Vì sao có: AG-OPS/AG-EVAL cần báo cáo & xin duyệt việc; Lark hiện chưa mở
available-range nên Telegram là kênh dùng được ngay (và giữ luôn làm kênh dự phòng).

Bot làm 3 việc:
  1. /start, /id  → trả chat_id + hướng dẫn nối tài khoản
  2. /dangky <email> <mã>  → nối chat Telegram với admin trong danh sách (mã ở .env)
  3. Nút ✅ Duyệt / ❌ Từ chối trên tin nhắn đề xuất → gọi API decide với đúng danh tính
     người bấm (KHÔNG cho tự duyệt việc do chính mình đề xuất — platform kiểm).

An toàn: Telegram không cho bot nhắn trước; admin phải chủ động mở chat với bot.
Token bot chỉ nằm ở .env trên VM.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
import urllib.request
import urllib.error

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
PLATFORM = os.environ.get("PLATFORM_URL", "http://platform_api:8090").rstrip("/")
INGEST = os.environ.get("GATEWAY_INGEST_TOKEN") or os.environ.get("PLATFORM_ADMIN_TOKEN", "")
LINK_CODE = os.environ.get("TELEGRAM_LINK_CODE", "")
API = f"https://api.telegram.org/bot{TOKEN}"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("tg-bot")

HELP = (
    "*LSR Admin Bot*\n"
    "Kênh nhận cảnh báo và duyệt việc từ AG-OPS / AG-EVAL.\n\n"
    "*Nối tài khoản của bạn:*\n"
    "`/dangky email@hapas.vn <mã>`\n"
    "(mã do quản trị platform cấp)\n\n"
    "Lệnh khác: /id — xem chat id của bạn"
)


def tg(method: str, payload: dict, timeout: int = 35):
    req = urllib.request.Request(f"{API}/{method}",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as exc:
        log.warning("telegram %s lỗi: %s", method, exc)
        return {}


def send(chat_id, text: str, buttons=None):
    p = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if buttons:
        p["reply_markup"] = {"inline_keyboard": buttons}
    return tg("sendMessage", p)


def papi(method: str, path: str, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(PLATFORM + path, data=data, method=method, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {INGEST}"})
    with urllib.request.urlopen(req, timeout=20) as r:
        b = r.read().decode()
        return json.loads(b) if b else {}


def who(chat_id) -> dict | None:
    try:
        return papi("GET", f"/v1/admins/by-telegram/{chat_id}")
    except Exception:
        return None


def handle_message(msg: dict) -> None:
    chat_id = msg.get("chat", {}).get("id")
    text = (msg.get("text") or "").strip()
    if not chat_id:
        return
    if text.startswith("/start") or text.startswith("/help"):
        send(chat_id, HELP + f"\n\n_chat id của bạn:_ `{chat_id}`")
        return
    if text.startswith("/id"):
        send(chat_id, f"chat id của bạn: `{chat_id}`")
        return
    if text.startswith("/dangky"):
        parts = text.split()
        if len(parts) < 3:
            send(chat_id, "Cú pháp: `/dangky email@hapas.vn <mã>`")
            return
        email, code = parts[1], parts[2]
        if LINK_CODE and code != LINK_CODE:
            send(chat_id, "❌ Mã không đúng. Hỏi quản trị platform để lấy mã.")
            log.warning("sai mã đăng ký từ chat %s (email %s)", chat_id, email)
            return
        try:
            papi("POST", "/v1/admins/link", {"email": email, "telegram_chat_id": str(chat_id)})
            send(chat_id, f"✅ Đã nối `{email}` với chat này.\n"
                          f"Từ giờ bạn sẽ nhận cảnh báo và đề xuất cần duyệt tại đây.")
            log.info("đã nối %s ↔ chat %s", email, chat_id)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                send(chat_id, f"❌ `{email}` không có trong danh sách admin của platform.")
            else:
                send(chat_id, f"❌ Lỗi nối tài khoản ({e.code}).")
        return
    a = who(chat_id)
    if a:
        send(chat_id, f"Chào {a['name']}. Dùng /help để xem lệnh.")
    else:
        send(chat_id, HELP + f"\n\n_chat id của bạn:_ `{chat_id}`")


def handle_callback(cb: dict) -> None:
    """Nút Duyệt/Từ chối — danh tính lấy từ chat_id đã nối, không tin dữ liệu client."""
    data = cb.get("data") or ""
    chat_id = (cb.get("message") or {}).get("chat", {}).get("id")
    cb_id = cb.get("id")
    a = who(chat_id)
    if not a:
        tg("answerCallbackQuery", {"callback_query_id": cb_id,
                                   "text": "Bạn chưa nối tài khoản admin (/dangky)",
                                   "show_alert": True})
        return
    try:
        act, aid = data.split(":", 1)
    except ValueError:
        return
    decision = "approve" if act == "approve" else "reject"
    try:
        r = papi("POST", f"/v1/actions/{aid}/decide",
                 {"decision": decision, "approver": a["email"]})
        msg = ("✅ Đã duyệt" if decision == "approve" else "❌ Đã từ chối") + f" #{aid}"
        detail = json.dumps(r.get("result") or {}, ensure_ascii=False)[:150]
        tg("answerCallbackQuery", {"callback_query_id": cb_id, "text": msg})
        send(chat_id, f"{msg} bởi *{a['name']}*\n`{detail}`")
        log.info("%s #%s bởi %s", decision, aid, a["email"])
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        # 403 = tự duyệt việc mình đề xuất; 409 = đã có người quyết trước
        tg("answerCallbackQuery", {"callback_query_id": cb_id,
                                   "text": f"Không thực hiện được ({e.code})", "show_alert": True})
        send(chat_id, f"⚠️ Không thực hiện được #{aid}: `{body}`")


def main() -> None:
    if not TOKEN:
        log.error("thiếu TELEGRAM_BOT_TOKEN — bot không chạy")
        while True:
            time.sleep(60)
    me = tg("getMe", {}, timeout=10).get("result", {})
    log.info("Admin bot khởi động: @%s (%s)", me.get("username", "?"), me.get("first_name", ""))
    offset = 0
    while True:
        try:
            r = tg("getUpdates", {"offset": offset, "timeout": 30}, timeout=40)
            for u in r.get("result", []) or []:
                offset = u["update_id"] + 1
                if "message" in u:
                    handle_message(u["message"])
                elif "callback_query" in u:
                    handle_callback(u["callback_query"])
        except Exception as exc:
            log.warning("vòng lặp lỗi: %s", exc)
            time.sleep(5)


if __name__ == "__main__":
    main()
