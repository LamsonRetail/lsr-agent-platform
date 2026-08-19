"""Bot trả lời câu hỏi tồn kho bằng cách POLL tin nhắn nhóm (không cần event).

Vì sao có bản này: long connection (``bot.py``) cần đăng ký sự kiện
``im.message.receive_v1`` trên Developer Console; nếu event chưa được đẩy,
bot vẫn hoạt động được nhờ quyền ĐỌC lịch sử nhóm (``im:message.group_msg``)
— poll định kỳ, thấy tin mới thì trả lời.

Chạy:
    python bot_poll.py --excel "<file>" --chat-id oc_xxx
    DRY_RUN=false python bot_poll.py ...   # trả lời thật

Chỉ xử lý tin nhắn tạo ra SAU khi bot khởi động (không trả lời lại lịch sử cũ).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time

import requests
import yaml
from dotenv import find_dotenv, load_dotenv

from inventory_days import load_excel_skus
from qa import answer

try:
    from coc import load_sections
except ImportError:  # thiếu file kiến thức nền -> bot vẫn chạy phần tồn kho
    load_sections = None  # type: ignore[assignment]

logger = logging.getLogger("inventory-bot-poll")

TOKEN_TTL_MARGIN = 120  # giây, làm mới token trước khi hết hạn


class LarkPoller:
    def __init__(self, app_id: str, app_secret: str, domain: str) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._domain = domain.rstrip("/")
        self._token: str | None = None
        self._token_expire_at = 0.0

    def _token_value(self) -> str:
        if self._token and time.monotonic() < self._token_expire_at:
            return self._token
        resp = requests.post(
            f"{self._domain}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": self._app_id, "app_secret": self._app_secret}, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"Lấy token thất bại: {payload}")
        self._token = payload["tenant_access_token"]
        self._token_expire_at = time.monotonic() + int(payload.get("expire", 7200)) - TOKEN_TTL_MARGIN
        return self._token

    def bot_info(self) -> dict:
        """open_id + tên của chính bot — để biết tin nào đang @ mình."""
        resp = requests.get(
            f"{self._domain}/open-apis/bot/v3/info",
            headers={"Authorization": f"Bearer {self._token_value()}"}, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"Lấy thông tin bot thất bại: {payload}")
        return payload.get("bot", {})

    def list_chats(self) -> list[dict]:
        """Mọi nhóm bot đang là thành viên — để phục vụ tất cả, không chỉ 1 nhóm."""
        resp = requests.get(
            f"{self._domain}/open-apis/im/v1/chats", params={"page_size": 100},
            headers={"Authorization": f"Bearer {self._token_value()}"}, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"Lấy danh sách nhóm thất bại: {payload}")
        return payload.get("data", {}).get("items", [])

    def fetch_recent(self, chat_id: str, page_size: int = 10) -> list[dict]:
        resp = requests.get(
            f"{self._domain}/open-apis/im/v1/messages",
            params={"container_id_type": "chat", "container_id": chat_id,
                    "sort_type": "ByCreateTimeDesc", "page_size": page_size},
            headers={"Authorization": f"Bearer {self._token_value()}"}, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"Đọc tin nhắn thất bại: {payload}")
        return payload.get("data", {}).get("items", [])

    def send(self, chat_id: str, text: str) -> None:
        resp = requests.post(
            f"{self._domain}/open-apis/im/v1/messages",
            params={"receive_id_type": "chat_id"},
            headers={"Authorization": f"Bearer {self._token_value()}"},
            json={"receive_id": chat_id, "msg_type": "text",
                  "content": json.dumps({"text": text}, ensure_ascii=False)}, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"Gửi tin thất bại: {payload}")


def _is_addressed(item: dict, bot_open_id: str, bot_name: str) -> bool:
    """Tin này có @mention đích danh bot không?"""
    for m in item.get("mentions") or []:
        if m.get("id") == bot_open_id:
            return True
        if bot_name and m.get("name") == bot_name:
            return True
    return False


# Dấu hiệu một tin là CÂU HỎI. Bot ngồi trong nhóm làm việc thật nên chỉ tự
# nhảy vào khi câu đó trông như câu hỏi VÀ nó tra ra được đáp án chắc chắn.
_QUESTION_MARKERS = (
    "?", " gì", " nào", " sao", " đâu", " mấy", " ai ", " bao nhiêu", " bao lâu",
    " thế nào", " ra sao", " khi nào", " bao giờ", " là gì", " có phải",
    " như thế nào", " bnhieu", " bn ",
)


def _looks_like_question(text: str) -> bool:
    t = " " + text.lower().strip() + " "
    if any(m in t for m in _QUESTION_MARKERS):
        return True
    # "... có ... không" — dạng hỏi rất phổ biến, không có từ để hỏi nào ở trên.
    return " có " in t and ("không " in t or " ko " in t)


def _message_text(item: dict) -> str:
    if item.get("msg_type") != "text":
        return ""
    try:
        text = json.loads(item.get("body", {}).get("content", "{}")).get("text", "")
    except json.JSONDecodeError:
        return ""
    # Lark thay mention bằng @_user_N — bỏ đi để còn lại nội dung câu hỏi.
    import re
    return re.sub(r"@_user_\d+", " ", text).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="../config/thresholds.yaml")
    parser.add_argument("--excel",
                        help="File dữ liệu tồn kho. BỎ TRỐNG được: khi đó bot chỉ trả lời "
                             "câu hỏi quy trình từ Code of Conduct, câu hỏi tồn kho sẽ "
                             "báo 'chưa có dữ liệu' thay vì bịa số.")
    parser.add_argument("--chat-id", action="append",
                        help="Giới hạn ở nhóm cụ thể (lặp lại được). Bỏ trống = phục vụ MỌI nhóm bot được add vào.")
    parser.add_argument("--answer-all", action="store_true",
                        help="Trả lời MỌI tin trong nhóm, không cần @mention. Chỉ nên "
                             "bật ở nhóm test — ở nhóm thật sẽ rất ồn.")
    parser.add_argument("--interval", type=float, default=3.0, help="Giây giữa 2 lần poll")
    parser.add_argument("--rescan-every", type=int, default=20,
                        help="Sau bao nhiêu vòng thì quét lại danh sách nhóm (bắt nhóm mới add bot)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv(find_dotenv(usecwd=True))

    app_id = os.environ.get("LARK_APP_ID_INVENTORY") or os.environ["LARK_APP_ID"]
    app_secret = os.environ.get("LARK_APP_SECRET_INVENTORY") or os.environ["LARK_APP_SECRET"]
    domain = os.environ.get("LARK_DOMAIN", "https://open.larksuite.com")
    dry_run = os.environ.get("DRY_RUN", "true").lower() != "false"

    source_cfg = None
    if args.excel:
        with open(args.config, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        source_cfg = dict(next(c for c in config["sources"].values()
                               if c.get("data_source") == "excel"))
        source_cfg["_excel_path"] = args.excel
        logger.info("Đã nạp %d SKU từ excel.", len(load_excel_skus(source_cfg)))
    else:
        logger.warning("Không có --excel: bot chỉ trả lời câu hỏi quy trình (Code of "
                       "Conduct). Câu hỏi tồn kho sẽ báo 'chưa có dữ liệu'.")

    def load_skus():
        return load_excel_skus(source_cfg) if source_cfg else []

    # Kiến thức nền: đọc 1 lần khi khởi động, không đọc lại mỗi tin nhắn.
    coc_sections = None
    if load_sections is not None:
        try:
            coc_sections = load_sections()
            logger.info("Đã nạp Code of Conduct KHHH: %d mục.", len(coc_sections))
        except OSError as exc:
            logger.warning("Không đọc được Code of Conduct (%s) — bot chỉ trả lời tồn kho.", exc)

    poller = LarkPoller(app_id, app_secret, domain)

    # Mất mạng lúc khởi động thì CHỜ, không được chết — nếu chết thì vòng lặp
    # bên ngoài restart ngay và quay vòng vô hạn (đã xảy ra đêm 19/08).
    bot = None
    for attempt in range(1, 61):
        try:
            bot = poller.bot_info()
            break
        except Exception as exc:  # noqa: BLE001
            logger.warning("Chưa gọi được Lark (lần %d): %s — thử lại sau 10s.", attempt, exc)
            time.sleep(10)
    if bot is None:
        logger.error("Không kết nối được Lark sau 10 phút. Dừng.")
        return 1
    bot_open_id, bot_name = bot.get("open_id", ""), bot.get("app_name", "")
    if args.answer_all:
        logger.warning("--answer-all: trả lời MỌI tin trong nhóm.")
    else:
        logger.info("Trả lời khi được @%s, hoặc khi có câu hỏi mà tra ra được "
                    "đáp án chắc chắn.", bot_name or "bot")
    # Mốc bắt đầu: chỉ trả lời tin tạo sau thời điểm này.
    start_ms = int(time.time() * 1000)
    seen: set[str] = set()

    def current_chats() -> dict[str, str]:
        """chat_id -> tên nhóm. Cố định nếu người dùng chỉ định --chat-id."""
        if args.chat_id:
            return {cid: cid for cid in args.chat_id}
        return {c["chat_id"]: c.get("name", "") for c in poller.list_chats()}

    try:
        chats = current_chats()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Chưa lấy được danh sách nhóm (%s) — sẽ thử lại trong vòng lặp.", exc)
        chats = {cid: cid for cid in (args.chat_id or [])}
    logger.info("Bắt đầu poll mỗi %.1fs (DRY_RUN=%s) — %d nhóm: %s",
                args.interval, dry_run, len(chats), ", ".join(chats.values()) or "(chưa có)")

    loop_count = 0
    while True:
        loop_count += 1
        try:
            # Định kỳ quét lại để bắt nhóm mới add bot vào giữa chừng.
            if not args.chat_id and loop_count % args.rescan_every == 0:
                refreshed = current_chats()
                for cid, name in refreshed.items():
                    if cid not in chats:
                        logger.info("Phát hiện nhóm mới: %s", name or cid)
                chats = refreshed

            for chat_id, chat_name in chats.items():
                for item in reversed(poller.fetch_recent(chat_id)):
                    mid = item.get("message_id")
                    if not mid or mid in seen:
                        continue
                    if int(item.get("create_time", 0)) < start_ms:
                        continue
                    if item.get("sender", {}).get("sender_type") != "user":
                        continue  # bỏ qua tin của chính bot
                    seen.add(mid)

                    question = _message_text(item)
                    if not question:
                        continue

                    # Được @ đích danh -> luôn trả lời, kể cả để nói "không biết".
                    # Không được gọi tên -> chỉ chen vào khi đúng là câu hỏi VÀ
                    # tra ra đáp án chắc chắn; còn lại im lặng.
                    addressed = args.answer_all or _is_addressed(item, bot_open_id, bot_name)
                    if not addressed and not _looks_like_question(question):
                        continue

                    try:
                        reply = answer(question, load_skus(), coc_sections,
                                       only_confident=not addressed)
                    except Exception:  # noqa: BLE001
                        logger.exception("Lỗi tra dữ liệu")
                        reply = "Xin lỗi, mình gặp lỗi khi tra dữ liệu tồn kho." if addressed else None

                    if reply is None:
                        logger.info("[%s] Bỏ qua (không tra được chắc chắn): %s",
                                    chat_name or chat_id, question)
                        continue
                    logger.info("[%s] Câu hỏi: %s", chat_name or chat_id, question)
                    if dry_run:
                        logger.info("[DRY_RUN] Sẽ trả lời:\n%s", reply)
                    else:
                        poller.send(chat_id, reply)
                        logger.info("[%s] Đã trả lời.", chat_name or chat_id)
        except requests.exceptions.RequestException as exc:
            # Mất mạng / Lark chớp tắt: 1 dòng gọn, không đổ traceback mỗi 3 giây.
            logger.warning("Lỗi mạng: %s — bỏ qua vòng này.", exc.__class__.__name__)
        except Exception:  # noqa: BLE001 — không lỗi nào được làm chết vòng lặp
            logger.exception("Lỗi khi poll")
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
