"""Phân quyền truy cập số liệu tài chính. Mặc định TỪ CHỐI.

Whitelist đọc từ biến môi trường, không hardcode vào repo (manifest và code đều public
trong repo nội bộ).

    FIN_SQUAD_EMAILS=a@lamsonretail.vn,b@lamsonretail.vn
    FIN_SQUAD_OPEN_IDS=ou_xxx,ou_yyy      # dùng khi chỉ biết open_id từ event Lark
    FIN_SQUAD_CHAT_IDS=oc_xxx             # nhóm Lark của squad: hỏi trong nhóm này là hợp lệ

Whitelist rỗng nghĩa là CHƯA CẤU HÌNH, không phải "cho tất cả" — mọi yêu cầu số liệu bị
từ chối (testcase A4).
"""

from __future__ import annotations

import os

DENY_MESSAGE = (
    "Số liệu tài chính chỉ dành cho squad Finance-Accounting nên tôi không trả lời câu này. "
    "Anh/chị liên hệ kế toán phụ trách để được cung cấp."
)


def _env_set(name: str) -> frozenset[str]:
    raw = os.environ.get(name, "")
    return frozenset(p.strip().lower() for p in raw.split(",") if p.strip())


def is_squad_member(
    *,
    email: str | None = None,
    open_id: str | None = None,
    chat_id: str | None = None,
) -> bool:
    """True nếu người/kênh này được phép xem số liệu tài chính.

    Nhận diện theo bất kỳ dấu hiệu nào khớp whitelist. Không có dấu hiệu nào khớp — kể cả
    khi không xác định được người hỏi là ai — thì trả False.
    """
    if email and email.strip().lower() in _env_set("FIN_SQUAD_EMAILS"):
        return True
    if open_id and open_id.strip().lower() in _env_set("FIN_SQUAD_OPEN_IDS"):
        return True
    if chat_id and chat_id.strip().lower() in _env_set("FIN_SQUAD_CHAT_IDS"):
        return True
    return False


def is_squad_member_from_payload(payload: dict) -> bool:
    """Bản tiện dụng cho payload job của platform."""
    return is_squad_member(
        email=payload.get("sender_email"),
        open_id=payload.get("sender_open_id"),
        chat_id=payload.get("chat_id"),
    )
