"""Từ câu hỏi tiếng Việt → truy vấn → câu trả lời. Hương.

Tầng này chỉ diễn giải và diễn đạt, không tự tính toán số liệu (query.py làm việc đó) và
không kiểm quyền (consumer.py đã kiểm trước khi gọi vào đây).

Bốn luật diễn đạt, đều là để người đọc tự phát hiện được khi máy hiểu sai:
  • Không nhận ra câu hỏi hỏi số gì → nói không có trong phạm vi, liệt kê những gì có. Không
    đoán (C5).
  • Thiếu kỳ → hỏi lại, không mặc định là tháng này (C4).
  • Có tháng mà không có năm → vẫn trả lời nhưng NÊU RÕ đã hiểu là kỳ nào (C10).
  • Không có dữ liệu khác hoàn toàn với bằng 0, và số cũ luôn kèm mốc thời gian (C2, C3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from . import query
from .mapping import normalize_header
from .query import Figure
from .schema import format_money
from .store import Store

VN_TZ = timezone(timedelta(hours=7))

SCOPE_HINT = (
    "Trong phạm vi FIN-HUB hiện có: công nợ phải thu, công nợ phải trả, doanh thu, chi phí, "
    "lãi lỗ theo kỳ."
)


@dataclass(frozen=True)
class Answer:
    text: str
    figure: Figure | None = None
    needs_clarification: bool = False


def format_vnd(value: Decimal) -> str:
    return format_money(value) + " đ"


def format_ts(when: datetime | None) -> str:
    if when is None:
        return "chưa rõ"
    return when.astimezone(VN_TZ).strftime("%H:%M %d/%m/%Y")


# --- Diễn giải câu hỏi -------------------------------------------------------------------

_METRICS = (
    ("payable", ("phai tra", "no nha cung cap", "no ncc", "cong no phai tra")),
    ("receivable", ("phai thu", "cong no", "no khach hang", "no kh")),
    ("revenue", ("doanh thu",)),
    ("expense", ("chi phi", "chi tieu")),
    ("profit_loss", ("lai lo", "loi nhuan", "lai/lo")),
)


def detect_metric(question: str) -> str | None:
    folded = normalize_header(question)
    for metric, keywords in _METRICS:
        if any(k in folded for k in keywords):
            return metric
    return None


def detect_overdue_days(question: str) -> int | None:
    folded = normalize_header(question)
    if "qua han" not in folded and "tuoi no" not in folded:
        return None
    match = re.search(r"(\d+)\s*ngay", folded)
    return int(match.group(1)) if match else 0


@dataclass(frozen=True)
class Period:
    value: str
    year_assumed: bool = False


def detect_period(question: str, *, today: date | None = None) -> Period | None:
    """Nhận "2026-07", "tháng 7/2026", "07/2026", "tháng 7". Trả None nếu câu không nêu kỳ."""
    folded = normalize_header(question)

    match = re.search(r"(20\d{2})\s*-\s*(\d{1,2})", folded)
    if match:
        year, month = match.group(1), int(match.group(2))
        return Period(f"{year}-{month:02d}") if 1 <= month <= 12 else None

    match = re.search(r"(\d{1,2})\s*/\s*(20\d{2})", folded)
    if match:
        month, year = int(match.group(1)), match.group(2)
        return Period(f"{year}-{month:02d}") if 1 <= month <= 12 else None

    match = re.search(r"thang\s*(\d{1,2})", folded)
    if match:
        month = int(match.group(1))
        if 1 <= month <= 12:
            year = (today or datetime.now(VN_TZ).date()).year
            return Period(f"{year}-{month:02d}", year_assumed=True)
    return None


def detect_channel(question: str) -> str | None:
    folded = normalize_header(question)
    if "online" in folded:
        return "Online"
    if "offline" in folded or "cua hang" in folded:
        return "Offline"
    return None


# --- Trả lời -----------------------------------------------------------------------------


def answer_question(question: str, store: Store, *, today: date | None = None) -> Answer:
    metric = detect_metric(question)
    if metric is None:
        return Answer(
            text=f"Tôi không có số liệu cho câu hỏi này nên không trả lời. {SCOPE_HINT}",
            needs_clarification=True,
        )

    if metric in ("receivable", "payable"):
        overdue = detect_overdue_days(question)
        fn = query.outstanding_receivable if metric == "receivable" else query.outstanding_payable
        figure = fn(store, overdue_days=overdue, as_of=today)
        return Answer(text=render(figure), figure=figure)

    period = detect_period(question, today=today)
    if period is None:
        return Answer(
            text=(
                "Câu hỏi chưa nêu kỳ nào nên tôi chưa trả lời được — anh/chị cho tôi biết kỳ "
                "(ví dụ tháng 7/2026)"
                + (", và kênh nào nếu cần tách kênh." if metric == "revenue" else ".")
            ),
            needs_clarification=True,
        )

    if metric == "revenue":
        figure = query.revenue(store, period=period.value, channel=detect_channel(question))
    elif metric == "expense":
        figure = query.expense(store, period=period.value)
    else:
        figure = query.profit_loss(store, period=period.value)

    return Answer(text=render(figure, period=period), figure=figure)


def render(figure: Figure, *, period: Period | None = None) -> str:
    lines: list[str] = []

    if period is not None and period.year_assumed:
        # Người hỏi chỉ nói "tháng 7". Nêu rõ kỳ đã hiểu để họ tự phát hiện nếu sai (C10).
        lines.append(f"Tôi hiểu kỳ anh/chị hỏi là {period.value}.")

    if figure.value is None:
        if figure.synced_at is None:
            lines.append(
                f"FIN-HUB chưa đồng bộ lần nào nên tôi không có số cho {figure.label}. "
                "Chưa có dữ liệu, không phải bằng 0."
            )
        else:
            lines.append(
                f"Không có dữ liệu {figure.label} trong FIN-HUB "
                f"(mốc đồng bộ {format_ts(figure.synced_at)}). Chưa có dữ liệu, không phải bằng 0."
            )
        return "\n".join(lines)

    count = f" ({figure.count} bản ghi)" if figure.count else ""
    lines.append(f"Tổng {figure.label}: {format_vnd(figure.value)}{count}.")
    lines.append(
        f"Nguồn: {', '.join(figure.sources) or 'chưa rõ'}. "
        f"Số liệu tính đến mốc đồng bộ {format_ts(figure.synced_at)}."
    )
    if figure.is_stale:
        lines.append(
            f"Lưu ý: đây là số CŨ so với ngưỡng đang cấu hình — lần đồng bộ gần nhất là "
            f"{format_ts(figure.synced_at)}. Cần số mới thì chạy lại đồng bộ."
        )
    if figure.discrepancy:
        lines.append(figure.discrepancy + ". Tôi không tự chọn nguồn nào, cần kế toán đối chiếu.")
    return "\n".join(lines)
