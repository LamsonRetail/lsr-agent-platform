"""Schema chuẩn của FIN-HUB — hợp đồng dữ liệu giữa các nguồn và tầng truy vấn.

Khớp với docs/DATA_MODEL.md. Đổi một bên thì đổi cả bên kia.

Tiền luôn là Decimal. Thiếu trường bắt buộc thì raise, không điền mặc định.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

VND = "VND"


class SchemaError(ValueError):
    """Dữ liệu nguồn không hợp lệ. Thông báo phải nêu rõ trường nào sai."""


def parse_money(raw: object) -> Decimal:
    """Đổi giá trị tiền từ nguồn thành Decimal.

    Nguồn Việt Nam viết tiền nhiều kiểu: "1.234.567", "1.234.567đ", "1,234,567",
    "(1.234.567)" cho số âm. Dấu chấm là phân cách nghìn, không phải thập phân.
    """
    if isinstance(raw, Decimal):
        return raw
    if isinstance(raw, int):
        return Decimal(raw)
    if isinstance(raw, float):
        raise SchemaError(f"tiền không được truyền dạng float (nhận {raw!r}) — dùng str hoặc Decimal")
    if raw is None:
        raise SchemaError("tiền bị rỗng")

    s = str(raw).strip()
    if not s:
        raise SchemaError("tiền bị rỗng")

    negative = s.startswith("(") and s.endswith(")")
    if negative:
        s = s[1:-1]
    s = re.sub(r"[đdĐD₫\s]", "", s)
    s = s.replace("_", "")

    # Phần thập phân chỉ được coi là thập phân khi có đúng 1 dấu và theo sau <= 2 chữ số.
    if "," in s and "." in s:
        s = s.replace(".", "") if s.rindex(",") > s.rindex(".") else s.replace(",", "")
        s = s.replace(",", ".")
    else:
        sep = "," if "," in s else "." if "." in s else ""
        if sep:
            tail = s.rsplit(sep, 1)[1]
            s = s.replace(sep, "") if (len(tail) == 3 or s.count(sep) > 1) else s.replace(sep, ".")

    if not re.fullmatch(r"-?\d+(\.\d+)?", s):
        raise SchemaError(f"không đọc được số tiền từ {raw!r}")

    try:
        value = Decimal(s)
    except InvalidOperation as exc:
        raise SchemaError(f"không đọc được số tiền từ {raw!r}") from exc
    return -value if negative else value


@dataclass(frozen=True)
class Provenance:
    """Số này từ đâu ra và cũ đến mức nào. Bắt buộc với mọi bản ghi."""

    source: str          # "gsheet" | "misa" | "larkbase"
    source_ref: str      # id dòng / số chứng từ ở nguồn, để đối chiếu ngược
    synced_at: datetime

    def __post_init__(self) -> None:
        if not self.source or not self.source_ref:
            raise SchemaError("thiếu source hoặc source_ref")
        if self.synced_at.tzinfo is None:
            raise SchemaError("synced_at phải có timezone")


@dataclass(frozen=True)
class Receivable:
    """Công nợ phải thu. Tuổi nợ KHÔNG lưu ở đây — tính lúc truy vấn."""

    partner_code: str
    partner_name: str
    invoice_no: str
    invoice_date: date
    due_date: date
    amount: Decimal
    paid_amount: Decimal
    outstanding: Decimal
    prov: Provenance
    currency: str = VND

    def __post_init__(self) -> None:
        _require(self, "partner_code", "partner_name", "invoice_no")
        if self.outstanding != self.amount - self.paid_amount:
            raise SchemaError(
                f"{self.partner_code}/{self.invoice_no}: outstanding={self.outstanding} "
                f"không bằng amount - paid_amount = {self.amount - self.paid_amount}"
            )

    @property
    def natural_key(self) -> tuple[str, str, str]:
        return (self.prov.source, self.partner_code, self.invoice_no)


@dataclass(frozen=True)
class Payable(Receivable):
    """Công nợ phải trả. Tách khỏi Receivable để không bao giờ cộng lẫn hai chiều nợ."""


@dataclass(frozen=True)
class Revenue:
    period: str          # YYYY-MM
    channel: str
    amount: Decimal
    prov: Provenance
    store_code: str = ""

    def __post_init__(self) -> None:
        _require_period(self.period)
        _require(self, "channel")

    @property
    def natural_key(self) -> tuple[str, str, str, str]:
        return (self.prov.source, self.period, self.channel, self.store_code)


@dataclass(frozen=True)
class Expense:
    period: str
    account_code: str
    account_name: str
    amount: Decimal
    prov: Provenance
    department: str = ""
    budget_amount: Decimal | None = None   # None = không có ngân sách, KHÁC ngân sách bằng 0

    def __post_init__(self) -> None:
        _require_period(self.period)
        _require(self, "account_code", "account_name")

    @property
    def natural_key(self) -> tuple[str, str, str, str]:
        return (self.prov.source, self.period, self.account_code, self.department)


@dataclass(frozen=True)
class Cashflow:
    txn_date: date
    account_code: str
    direction: str       # "in" | "out" — không dùng số âm để biểu thị chiều
    amount: Decimal
    prov: Provenance
    category: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        _require(self, "account_code")
        if self.direction not in ("in", "out"):
            raise SchemaError(f"direction phải là 'in' hoặc 'out', nhận {self.direction!r}")
        if self.amount < 0:
            raise SchemaError("amount của cashflow phải dương, chiều nằm ở direction")

    @property
    def natural_key(self) -> tuple[str, str]:
        return (self.prov.source, self.prov.source_ref)


@dataclass
class SyncLog:
    run_id: str
    source: str
    table: str
    started_at: datetime
    finished_at: datetime | None = None
    status: str = "ok"          # ok | partial | failed
    rows_read: int = 0
    rows_written: int = 0
    error: str = ""
    discrepancies: list[str] = field(default_factory=list)


def _require(obj: object, *names: str) -> None:
    missing = [n for n in names if not str(getattr(obj, n, "") or "").strip()]
    if missing:
        raise SchemaError(f"thiếu trường bắt buộc: {', '.join(missing)}")


def _require_period(period: str) -> None:
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period or ""):
        raise SchemaError(f"period phải dạng YYYY-MM, nhận {period!r}")
