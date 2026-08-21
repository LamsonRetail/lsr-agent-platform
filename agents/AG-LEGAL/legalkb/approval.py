"""Đọc Lark Approval dưới danh tính account của agent, qua broker C8 của platform.

## Vì sao phải qua broker

View "việc đang chờ tôi" của Approval **chỉ nhận user token** — hợp lý, vì "tôi" là ai thì
chỉ user token trả lời được. Nhưng chuẩn platform (§2.3) cấm agent cầm token của một
account thật. C8 giải quyết đúng chỗ đó: platform giữ token (mã hoá, tự refresh), agent gọi
`/v1/lark/user/call` và **không bao giờ thấy token**. Chi tiết: `docs/LARK_USER_BROKER.md`.

## Approval v4 TRỘN hai loại token — bảng dưới là ĐO THẬT, và nó SỬA một kết luận sai

Đo 20/08/2026, cùng một endpoint gọi bằng cả hai loại token:

| Endpoint | user token (C8) | tenant token |
|---|---|---|
| `GET /tasks?topic=1` (việc đang chờ tôi) | ✅ `code:0` | — |
| `GET /tasks?topic=2`, `17`, `18` | ✅ `code:0` | — |
| `GET /tasks` thiếu `topic` | ❌ `99992402`, options **[1,2,17,18]** | — |
| `GET /approvals/{code}` (định nghĩa) | ❌ `99991668` | **`99991672` thiếu scope** |
| `GET /instances/{code}` (form + file) | ❌ `99991668` | **`99991672` thiếu scope** |
| `GET /instances`, `POST /instances/search`, `/tasks/search` | ❌ `99991668` | — |

Đọc mã lỗi cho đúng — chỗ này quyết định thiết kế:

* `99991668 user access token not support` = endpoint **không nhận user token**.
* `99991672 Access denied. One of the following scopes is required: [approval:approval…]`
  = **token ĐÚNG LOẠI rồi**, chỉ thiếu scope trên app. Đây là lỗi cấu hình, không phải
  lỗi kiến trúc.

⚠️ **Kết luận cũ trong PLAN §11 là SAI**: ghi "API Approval là user-token-based, nên C5
phụ thuộc C8". Thực tế ngược lại — **phần lớn Approval dùng TENANT token**; user token chỉ
dùng được cho đúng một view: "việc đang chờ tôi". Lần 19/08 gọi bằng `--as bot` của CLI trả
"only supports: user" là app_access_token, **không phải** tenant_access_token; hai thứ khác
nhau và đó là chỗ đã đọc nhầm.

## Hệ quả: hôm nay làm được gì, còn thiếu gì

Làm được ngay (qua C8, đã đo chạy):
* Biết **có hồ sơ mới đang chờ** account của agent → `pending_tasks()`.

Còn thiếu, và thiếu **một** thứ duy nhất: platform chưa có đường gọi Lark bằng **tenant
token** kiểu passthrough (chỉ có `send`/`resolve`/`chats`/`resource`). Nên chưa đọc được
form + file đính kèm của hồ sơ, và chưa ghi comment vào instance. Đó là nội dung thật của
**C5** — xem `requests/C5-lark-tenant-passthrough.md`. Trong lúc chờ, báo cáo Bước 3/Bước 5
**gửi vào group Pháp chế qua bot** (chạy được ngay), không ghi vào instance.

"""
import os

# Định nghĩa workflow không đọc được bằng user token (99991668) nên số hiệu này ghim ở
# `signing.py` từ lần đọc bằng CLI 19/08. Không tự ý "đọc lại lúc chạy" — sẽ luôn lỗi.
SUBJECT_ENV = "AGENT_LARK_SUBJECT"
BASE = "/open-apis/approval/v4"

# topic của Lark: 1 = đang chờ tôi, 2 = tôi đã xử lý, 17/18 = tôi khởi tạo / CC cho tôi.
TOPIC_PENDING = "1"
TOPIC_DONE = "2"


def subject():
    return os.environ.get(SUBJECT_ENV, "").strip()


def status(pf):
    """Danh tính đã nối chưa + còn mấy ngày. Không cấu hình subject = coi như chưa nối."""
    subj = subject()
    if not subj:
        return {"connected": False,
                "reason": f"chưa đặt {SUBJECT_ENV} trong .env"}
    return pf.lark_user_status(subj)


def _get(pf, path):
    return pf.lark_user_call(subject(), "GET", BASE + path)


def pending_tasks(pf, page_size=20):
    """Việc đang chờ account của agent → `(list, error)`.

    Đây là **nguồn sự thật duy nhất** để agent biết có hồ sơ mới: `instances` liệt kê
    được thì tiện hơn nhiều, nhưng endpoint đó đòi tenant token (đo 20/08).
    """
    data, err = _get(pf, f"/tasks?topic={TOPIC_PENDING}&user_id_type=open_id"
                         f"&page_size={int(page_size)}")
    if err:
        return [], err
    return (data or {}).get("tasks") or [], None


def instance(pf, instance_code):
    """Chi tiết một instance (form + file đính kèm) → `(dict, error)`.

    ⛔ **Đường này ĐÃ ĐO LÀ KHÔNG DÙNG ĐƯỢC** bằng user token (`99991668`). Giữ hàm lại vì
    khi core mở passthrough tenant token (C5) thì chỉ đổi đúng một dòng ở đây. Cố tình
    KHÔNG xoá và cũng không im lặng trả rỗng: trả lỗi có nội dung để người đọc log biết
    đang thiếu cái gì.
    """
    if not instance_code:
        return None, "thiếu instance_code"
    data, err = _get(pf, f"/instances/{instance_code}?user_id_type=open_id&locale=vi-VN")
    if err and "99991668" in err:
        return None, ("đọc instance cần TENANT token — platform chưa có passthrough "
                      "(C5). Báo cáo sẽ gửi vào group thay vì ghi vào instance")
    return data, err


def comment(pf, instance_code, text, user_open_id=None):
    """Ghi comment vào instance → `(dict, error)`.

    Agent **chỉ comment**, không làm node duyệt: quy trình thật chỉ có 2 node Approval và
    cả hai đều là người. Nguyên tắc "hỗ trợ, không chặn" nằm ở đây.

    ⚠️ CHƯA đo được (tenant có 0 instance). Nhưng `instances/{code}` đã đo là đòi tenant
    token, nên rất có thể comment cũng vậy. Lỗi `99991668` ⇒ chuyển sang gửi báo cáo qua
    bot vào group, KHÔNG được im lặng bỏ qua.
    """
    if not (instance_code and text):
        return None, "thiếu instance_code hoặc nội dung"
    q = f"/instances/{instance_code}/comments?user_id_type=open_id"
    if user_open_id:
        q += f"&user_id={user_open_id}"
    return pf.lark_user_call(subject(), "POST", BASE + q, {"content": text})


def summarise_status(st):
    """Một dòng tiếng Việt về tình trạng danh tính — dùng cho log khởi động và `#ds`."""
    if not st.get("connected"):
        return f"❌ danh tính Lark chưa nối: {st.get('reason') or 'không rõ lý do'}"
    left = st.get("refresh_days_left")
    warn = "  ⚠️ sắp hết hạn, cần người authorize lại" if isinstance(left, int) and left <= 2 else ""
    return (f"✅ danh tính Lark: {st.get('subject')} · còn {left} ngày refresh"
            f" · quyền {', '.join(st.get('path_prefixes') or [])}{warn}")
