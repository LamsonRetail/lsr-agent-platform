"""Cửa duy nhất để gửi tin Lark. Bọc libs/lsr_lark ở chế độ remote.

Vì sao phải đi qua đây: chế độ remote gọi broker của platform nên agent KHÔNG cầm
app_secret của Lark. Gọi Lark API trực tiếp bằng app_secret là vi phạm quy ước platform.

Ngoại lệ duy nhất là Lark Bitable — lsr_lark chưa hỗ trợ, code đó nằm ở
data_hub/sources/larkbase.py.

Env: LSR_PLATFORM_URL, LSR_AGENT_TOKEN (lsr_lark tự đọc).
"""

from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def client():
    """Trả client lsr_lark. Import muộn để test không cần cài lib của platform."""
    try:
        from lsr_lark import Lark
    except ImportError as exc:
        raise RuntimeError(
            "chưa cài lsr_lark — chạy: pip install -e libs/lsr_lark từ gốc repo"
        ) from exc
    return Lark()


def send(to: str, text: str, *, to_type: str = "email") -> None:
    client().send(to, text, to_type=to_type)


def send_markdown(to: str, markdown: str, *, to_type: str = "email") -> None:
    client().send_markdown(to, markdown, to_type=to_type)


def resolve_email(email: str) -> str:
    """email → open_id."""
    return client().resolve(email)
