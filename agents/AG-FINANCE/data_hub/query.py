"""Trả lời câu hỏi số liệu từ FIN-HUB. Phase 1, Hương.

CHƯA IMPLEMENT.

Luật đã chốt, đừng đổi khi implement:
  • Kiểm quyền TRƯỚC khi truy vấn, không phải sau (shared/auth.py).
  • Mọi kết quả mang theo synced_at. Câu trả lời không có mốc thời gian là câu trả lời sai.
  • Không tìm thấy → trả None. KHÔNG trả Decimal(0) (C2).
  • Dữ liệu cũ hơn ngưỡng → vẫn trả nhưng đánh dấu stale kèm ngày (C3).
  • Câu hỏi thiếu kỳ hoặc phạm vi → trả về yêu cầu hỏi lại, không tự mặc định (C4).
  • Đang có lệch giữa các nguồn cho số này → nêu cả hai con số kèm nguồn.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class Figure:
    """Một con số trả về người dùng, kèm đủ ngữ cảnh để không bị hiểu sai."""

    value: Decimal | None          # None = không tìm thấy, khác hoàn toàn với Decimal(0)
    label: str
    synced_at: datetime | None
    is_stale: bool = False
    sources: tuple[str, ...] = ()
    discrepancy: str = ""          # rỗng nếu các nguồn khớp nhau


def outstanding_receivable(*, overdue_days: int | None = None) -> Figure:
    """Công nợ phải thu còn lại, lọc theo tuổi nợ nếu có (C1)."""
    raise NotImplementedError("Phase 1 — xem docstring module")


def revenue(*, period: str, channel: str | None = None, store_code: str | None = None) -> Figure:
    raise NotImplementedError("Phase 1 — xem docstring module")


def expense(*, period: str, account_code: str | None = None, department: str | None = None) -> Figure:
    raise NotImplementedError("Phase 2 — xem docstring module")


def profit_loss(*, period: str) -> Figure:
    """Lãi lỗ = revenue - expense, tính lúc truy vấn.

    KHÔNG lưu thành bảng riêng, để hệ thống không bao giờ có hai con số lãi lỗ lệch nhau.
    """
    raise NotImplementedError("Phase 2 — xem docstring module")


def cash_balance(*, account_code: str | None = None, as_of: datetime | None = None) -> Figure:
    raise NotImplementedError("Phase 2 — xem docstring module")
