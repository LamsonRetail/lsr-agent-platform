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

## Chat RIÊNG không nằm trong `list_chats` — phải tự mở trước

Đây là chi tiết quyết định, và `agent/jenny/lark_user_bot.py` nói thẳng trong docstring:
*"Chat riêng không nằm trong API list_chats"*. Đo lại đúng như vậy: account Ann tham gia
3 group, `list_chats` trả về **đúng 3 group, 0 chat riêng** — kể cả chat riêng đã có tin.

Nên không có cách nào "nghe" một chat riêng mà mình chưa biết `chat_id`. Cách duy nhất
(Jenny cũng làm y vậy): **agent chủ động nhắn trước** theo `open_id`. Lark tự mở chat riêng
và **trả về `chat_id`** ngay trong response — lưu lại rồi poll `chat_id` đó về sau.

Hệ quả phải nói rõ với người dùng: **agent chỉ trả lời chat riêng của người đã được mở
trước**. Muốn thêm ai thì thêm `open_id` vào `USERCHAT_P2P_OPEN_IDS`, hoặc thêm họ vào
group mà agent đang theo dõi (`USERCHAT_SEED_GROUPS`). Cố ý KHÔNG tự mở với toàn bộ công
ty: mở chat là **gửi một tin chào tới từng người**, không phải việc agent tự quyết.

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
# Chat MỚI thấy: nhìn lùi bao lâu. Không phải 0 (đọc cả lịch sử) cũng không phải "bây giờ".
#
# Vì sao cần: người ta add Ann vào group rồi hỏi ngay trong vài giây, nhưng agent chỉ quét
# lại danh sách chat mỗi CHAT_REFRESH_SECONDS — nên tới lúc phát hiện group thì câu hỏi đã
# nằm trong quá khứ và bị bỏ. Đã xảy ra thật 22/08: câu "chào mọi người đi nha Ann" lúc
# 01:50:04 rơi đúng khe đó.
#
# Cửa sổ phải ≥ CHAT_REFRESH_SECONDS, nếu không vẫn còn khe. Để 10 phút cho chắc.
FIRST_LOOKBACK_SECONDS = float(os.environ.get("USERCHAT_FIRST_LOOKBACK_SECONDS", "600"))


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


def chat_members(pf, chat_id):
    """Thành viên một chat, dưới danh tính account agent → `(list[(tên, open_id)], error)`.

    open_id trả về nằm trong **không gian id của app đã cấp token cho account** — đúng thứ
    `send_text_to_user()` cần. Lấy open_id từ app khác là Lark trả "user not found".
    """
    data, err = _get(pf, f"/chats/{chat_id}/members?member_id_type=open_id&page_size=100")
    if err:
        return [], err
    return [(m.get("name") or "", m.get("member_id") or "")
            for m in ((data or {}).get("items") or [])], None


def send_text_to_user(pf, open_id, text):
    """Nhắn riêng theo `open_id` — Lark **tự mở chat riêng** và trả `chat_id`.

    Đây là cách duy nhất để có `chat_id` của một chat riêng (API không liệt kê chúng).
    """
    body = {"receive_id": open_id, "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False)}
    data, err = pf.lark_user_call(subject(), "POST",
                                  IM + "/messages?receive_id_type=open_id", body)
    if err:
        return None, None, err
    return (data or {}).get("chat_id"), (data or {}).get("message_id"), None


P2P_GREETING = (
    "Xin chào, mình là **trợ lý pháp chế** của LSR (account máy `{subj}`, không phải người).\n"
    "Chat riêng đã mở — anh/chị nhắn mình bất cứ lúc nào: hỏi quy định nội bộ, nhờ soạn "
    "bản thảo hợp đồng từ mẫu, nhờ rà soát hợp đồng đối tác, hoặc tra văn bản pháp luật.\n"
    "_Nội dung trao đổi được ghi log và Pháp chế có thể xem để soát chất lượng._")


def p2p_partners(pf, store, log=print):
    """Những `open_id` được chat riêng: khai tay + thành viên các group hạt giống.

    Lấy thành viên group là để không phải khai tay từng người — nhưng **chỉ những group
    được khai tường minh** ở `USERCHAT_SEED_GROUPS` (mặc định: group Pháp chế/Admin).
    Không quét mọi group Ann tham gia: Ann ở trong "LAMSON RETAIL TEAM" nên làm vậy là gửi
    tin chào cho cả công ty.
    """
    ids, seen = [], set()
    for raw in os.environ.get("USERCHAT_P2P_OPEN_IDS", "").split(","):
        oid = raw.strip()
        if oid and oid not in seen:
            seen.add(oid)
            ids.append((oid, ""))
    groups = [g.strip() for g in os.environ.get(
        "USERCHAT_SEED_GROUPS", os.environ.get("LEGAL_GROUP_CHAT_ID", "")).split(",")
        if g.strip()]
    me = (store.get_meta("uc:me") or "").strip()
    for gid in groups:
        members, err = chat_members(pf, gid)
        if err:
            log(f"[userchat] không đọc được thành viên {gid[:14]}: {err}")
            continue
        for name, oid in members:
            if not oid or oid in seen or oid == me:
                continue
            seen.add(oid)
            ids.append((oid, name))
    return ids


def ensure_p2p(pf, store, log=print):
    """Mở chat riêng với người chưa có, trả về list `chat_id` để poll.

    Tin chào gửi **một lần cho mỗi người** — khoá bằng `meta`, nên restart không gửi lại.
    """
    out = []
    for oid, name in p2p_partners(pf, store, log=log):
        key = f"uc:p2p:{oid}"
        cid = store.get_meta(key)
        if cid:
            out.append(cid)
            continue
        cid, mid, err = send_text_to_user(pf, oid, P2P_GREETING.replace("{subj}", subject()))
        if err or not cid:
            log(f"[userchat] không mở được chat riêng với {name or oid}: {err}")
            continue
        store.set_meta(key, cid)
        # Ghi lại tin chào là "của mình". Thiếu dòng này thì vòng poll đọc tin chào như tin
        # mới và **agent trả lời chính tin chào của nó** — đã xảy ra thật 22/08 08:32→08:33.
        if mid:
            store.set_meta(f"uc:sent:{mid}", "1")
        out.append(cid)
        log(f"[userchat] đã mở chat riêng với {name or oid} → {cid}")
    return out


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
