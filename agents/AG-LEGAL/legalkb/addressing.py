"""Ann chỉ lên tiếng khi được gọi tên, và nhớ ngữ cảnh theo từng chat/nhóm.

Hai việc nhỏ nhưng quyết định việc agent có dùng được trong nhóm hay không.

## 1. Khi nào trả lời

| Nơi | Quy tắc |
|---|---|
| Chat riêng 1-1 | luôn trả lời — người ta mở chat với agent là để hỏi nó |
| Group admin/phê duyệt | CHỈ xử lý lệnh (`#12 duyệt`…), tin thường thì im |
| Group thường | CHỈ trả lời khi **được gọi tên** hoặc **@mention** |

Vì sao phải chặn ở nhóm thường: agent nhảy vào mọi câu trong nhóm là cách nhanh nhất để
bị đá ra khỏi nhóm. Trong nhóm người ta bàn việc với nhau, không phải hỏi agent.

⚠️ Ràng buộc thật: gateway **không chuyển danh sách `mentions`** của Lark
(`event_gateway/gateway.py` chỉ lấy text + file_key/file_name/image_key/duration). Lark
lại thay chỗ mention trong text bằng placeholder `@_user_1`, nên **không biết mention ai**.
Cách xử lý: coi là được gọi khi có placeholder mention BẤT KỲ, hoặc khi text chứa tên/bí
danh của agent. Muốn chính xác tuyệt đối thì cần core chuyển thêm `mentions` — nhưng
thực tế Lark mặc định chỉ đẩy cho bot những tin có @mention nó, nên mức này đã đủ dùng.

## 2. Bộ nhớ theo chat/nhóm

Gateway **không set `session_id`** khi đẩy ingest, nên platform lưu job với session NULL.
Trước đây consumer rơi về `f"job-{id}"` ⇒ **mỗi tin là một phiên mới, không có bộ nhớ nào**.
Nay khoá phiên theo `chat_id`: cả nhóm dùng chung một mạch hội thoại, chat riêng thì mỗi
người một mạch — và nhớ được qua restart vì phiên nằm ở platform.
"""
import os

from legalkb.gates import plain

# Placeholder Lark chèn vào text khi có @mention (không kèm tên thật).
MENTION_MARK = "@_user_"

DEFAULT_ALIASES = "ann,ann nguyen,ann legal,legal agent,ag-legal,trợ lý pháp chế"


def aliases():
    """Tên/bí danh để nhận ra mình bị gọi. Đổi qua env, không sửa code."""
    raw = os.environ.get("AGENT_NAME_ALIASES", DEFAULT_ALIASES)
    return [plain(a) for a in raw.split(",") if plain(a)]


def called_by_name(text):
    """Có ai gọi tên/mention agent trong câu này không (không phân biệt dấu, hoa thường)."""
    if not text:
        return False
    if MENTION_MARK in text:
        return True
    t = plain(text)
    return any(a in t for a in aliases())


def session_for(job, payload):
    """Khoá phiên hội thoại — đây là chỗ bộ nhớ theo chat/nhóm dựa vào.

    Ưu tiên `session_id` do platform cấp. Không có (trường hợp Lark hiện tại) thì khoá
    theo `chat_id` để cả nhóm/cả chat riêng dùng chung một mạch. Cùng đường cuối mới rơi
    về job id — lúc đó coi như không có bộ nhớ, và đó là điều cần tránh.
    """
    if job.get("session_id"):
        return job["session_id"]
    chat_id = payload.get("chat_id") or (job.get("reply_to") or {}).get("chat_id")
    if chat_id:
        return f"{job.get('channel') or 'lark'}:{chat_id}"
    return f"job-{job['id']}"


def group_ids():
    """Danh sách chat_id được coi là NHÓM (nơi phải gọi tên mới trả lời)."""
    raw = os.environ.get("AGENT_GROUP_CHAT_IDS", "")
    return {c.strip() for c in raw.split(",") if c.strip()}


def is_group(payload, job=None):
    """Chat nhóm hay chat riêng.

    ⚠️ KHÔNG đoán theo tiền tố chat_id: Lark dùng `oc_` cho **cả** chat riêng lẫn nhóm,
    nên đoán kiểu đó sai. Tín hiệu đáng tin là `chat_type` ("p2p" | "group") — mà
    `event_gateway/gateway.py` hiện **không truyền** (chỉ có text, message_type,
    message_id, chat_id, sender_open_id + field đính kèm). Đã ghi thành yêu cầu **C12**.

    Nên thứ tự xét:
      1. có `chat_type` → tin nó (khi core truyền thì tự động đúng cho mọi nhóm);
      2. không có → tra danh sách cấu hình `AGENT_GROUP_CHAT_IDS`;
      3. không thuộc danh sách → coi là chat riêng, trả lời bình thường.

    Mặc định thiên về "chat riêng" là có chủ ý: nhầm thành nhóm sẽ khiến agent im lặng
    với người đang hỏi trực tiếp — hỏng nặng hơn là lỡ trả lời một câu trong nhóm.
    """
    ctype = (payload.get("chat_type") or payload.get("chat_mode") or "").lower()
    if ctype:
        return ctype == "group"
    chat_id = payload.get("chat_id") or ((job or {}).get("reply_to") or {}).get("chat_id")
    return bool(chat_id) and chat_id in group_ids()


def should_answer(payload, job=None, admin_group=None):
    """Có nên trả lời tin này không. Trả (bool, lý do) — lý do để ghi log cho dễ soi."""
    chat_id = payload.get("chat_id") or ((job or {}).get("reply_to") or {}).get("chat_id")
    if admin_group and chat_id == admin_group:
        return False, "group phê duyệt — chỉ xử lý lệnh"
    if not is_group(payload, job):
        return True, "chat riêng"
    if called_by_name(payload.get("text") or ""):
        return True, "được gọi tên trong nhóm"
    return False, "nhóm nhưng không gọi tên"
