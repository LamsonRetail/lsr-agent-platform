"""Lỗi chung của lsr_lark."""

from __future__ import annotations


class LarkError(RuntimeError):
    """Lỗi khi gọi Lark (qua broker hoặc trực tiếp)."""

    def __init__(self, message: str, *, status: int | None = None, detail: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.detail = detail
