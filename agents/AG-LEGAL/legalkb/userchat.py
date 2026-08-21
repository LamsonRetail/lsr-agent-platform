"""Chat dưới danh tính **account của agent** (`ann_legal@hapas.vn`) — poll, không event.

## Vì sao phải poll, và vì sao poll lại chạy được

Lark **không đẩy event cho account người** — đăng ký event là cơ chế của app/bot. Nhưng
với **user token** thì `GET /im/v1/chats` trả về **mọi chat account đó tham gia, kể cả chat
1-1**. Đó là chỗ mình từng kết luận sai: đo bằng *tenant* token thì API này chỉ trả group
(bot vừa mở chat 1-1 xong gọi lại vẫn không thấy), nên tưởng chat 1-1 không liệt kê được.
Sai vì đo bằng loại token khác.

Bằng chứng ngược lại là dự án **jenny-bod-assistant** (`agent/jenny/lark_user_bot.py`) —
đang chạy thật bằng đúng cách này: liệt kê chat của account → đọc tin mới → trả lời với tư
cách account.

## Khác Jenny một chỗ quan trọng: KHÔNG cầm token

Jenny tự giữ user token (lưu DB của nó, tự refresh). Ở đây token do **platform giữ** (C8,
mã hoá + tự refresh + audit từng lời gọi); agent chỉ gọi `POST /v1/lark/user/call` và
**không bao giờ thấy token**. Đúng chuẩn §2.3, và thu hồi được tức thì bằng
`/v1/lark/user/identities/<subject>/revoke`.

## Bốn cái bẫy của vòng poll (lấy từ code đang chạy của Jenny)

1. **Chat mới thấy thì bỏ qua lịch sử** — cursor khởi tạo bằng `now`, không phải 0. Nếu
   không, lần chạy đầu agent trả lời lại toàn bộ tin nhắn cũ của cả công ty.
2. **Bỏ tin của chính mình** — không thì agent trả lời chính câu trả lời của nó, lặp vô hạn.
   Ở đây nhận diện bằng `message_id` của tin mình vừa gửi (không cần thêm scope để biết
   open_id của chính mình).
3. **Cursor luôn tiến** (`max(latest, now)`) — tin lỗi xử lý cũng không đọc lại mãi.
4. **Dedupe theo `message_id`** — poll gối đầu nhau vẫn không xử lý hai lần.
"""
import json
import os
import time

IM = "/open-apis/im/v1"
NEED_PREFIX = "/open-apis/im/v1/"
NEED_SCOPES = ("im:chat:readonly", "im:message")   # tên scope lấy từ Jenny (đang chạy thật)

POLL_SECONDS = float(os.environ.get("USERCHAT_POLL_SECONDS", "10"))
CHAT_REFRESH_SECONDS = float(os.environ.get("USERCHAT_CHAT_REFRESH_SECONDS", "120"))


def subject():
    return os.environ.get("AGENT_LARK_SUBJECT", "").strip()


def available(pf):
    """Đủ điều kiện chạy chưa → `(bool, lý do)`.

    Kiểm cả hai tầng, vì chúng chặn ở hai chỗ khác nhau và báo lỗi khác nhau:
    **grant của platform** (403 "ngoài phạm vi được cấp") và **scope của token Lark**.
    """
    subj = subject()
    if not subj:
        return False, "chưa đặt AGENT_LARK_SUBJECT"
    st = pf.lark_user_status(subj) or {}
    if not st.get("connected"):
        return False, f"danh tính chưa nối: {st.get('reason') or 'không rõ'}"
    scopes = (st.get("scope") or "").split()
    missing = [s for s in NEED_SCOPES if s not in scopes]
    if missing:
        return False, ("token của account thiếu scope " + ", ".join(missing)
                       + " → cần core thêm domain `im` (C14) rồi admin authorize lại")
    prefixes = st.get("path_prefixes") or []
    if not any(NEED_PREFIX.startswith(p) or p.startswith(NEED_PREFIX) for p in prefixes):
        return False, (f"grant chưa mở {NEED_PREFIX} (đang có {prefixes}) → admin gọi "
                       f"POST /v1/lark/user/grants thêm prefix này")
    return True, f"chat dưới danh tính {subj} (poll {int(POLL_SECONDS)}s)"


def _get(pf, path):
    return pf.lark_user_call(subject(), "GET", IM + path)


def list_chats(pf):
    """Chat account đang tham gia, **kể cả chat 1-1**. Trả `(list, error)`."""
    out, token, guard = [], "", 0
    while guard < 20:
        guard += 1
        q = f"/chats?page_size=100" + (f"&page_token={token}" if token else "")
        data, err = _get(pf, q)
        if err:
            return out, err
        out += (data or {}).get("items") or []
        token = (data or {}).get("page_token") or ""
        if not (data or {}).get("has_more"):
            break
    return out, None


def list_messages(pf, chat_id, since_sec):
    """Tin trong một chat từ mốc thời gian. Trả `(list, error)`."""
    data, err = _get(pf, f"/messages?container_id_type=chat&container_id={chat_id}"
                         f"&start_time={int(since_sec)}&sort_type=ByCreateTimeAsc"
                         f"&page_size=50")
    if err:
        return [], err
    return (data or {}).get("items") or [], None


def send_text(pf, chat_id, text):
    """Gửi tin **với tư cách account**. Trả `(message_id, error)`."""
    body = {"receive_id": chat_id, "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False)}
    data, err = pf.lark_user_call(subject(), "POST",
                                  IM + "/messages?receive_id_type=chat_id", body)
    if err:
        return None, err
    return (data or {}).get("message_id"), None


def text_of(msg):
    """Nội dung tin dạng text. Tin khác loại trả "" — người gọi tự quyết cách xử lý."""
    if (msg or {}).get("msg_type") != "text":
        return ""
    try:
        raw = json.loads(((msg.get("body") or {}).get("content")) or "{}")
    except (json.JSONDecodeError, TypeError):
        return ""
    text = raw.get("text") or ""
    # Lark thay chỗ @mention bằng khoá (`@_user_1`); giữ nguyên placeholder để
    # `addressing.called_by_name()` nhận ra là có người gọi tên.
    return text.strip()


def is_group_chat(chat):
    """Group hay 1-1. Lark cho biết qua `chat_mode`/`chat_type` ở chính bản ghi chat."""
    return ((chat or {}).get("chat_mode") or "group") == "group" \
        and (chat or {}).get("chat_type") != "p2p"
