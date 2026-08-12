"""Map một dòng thô từ nguồn thành bản ghi đúng schema.

Tầng này KHÔNG biết dữ liệu đến từ Google Sheet, MISA hay Lark Base — nó chỉ nhận dict
{tên cột: giá trị}. Nhờ vậy toàn bộ logic chuẩn hoá test được mà không cần credential
của nguồn nào.

Tên cột trên sheet của kế toán không cố định: "Mã KH", "Ma KH", "Mã khách hàng" đều là một
thứ. Vì vậy so khớp tên cột sau khi bỏ dấu và chuẩn hoá khoảng trắng.
"""

from __future__ import annotations

import unicodedata
from datetime import datetime

from .schema import (
    Expense,
    Payable,
    Receivable,
    Revenue,
    SchemaError,
    parse_date,
    parse_money,
)


def normalize_header(name: str) -> str:
    """"Mã Khách  Hàng" và "ma_kh" → "ma khach hang" / "ma kh".

    Bỏ dấu và coi gạch dưới như khoảng trắng: sheet của kế toán viết "Mã KH", API MISA trả
    "ma_kh". Bí danh trong ALIASES cũng đi qua hàm này nên khai kiểu nào cũng khớp được.
    """
    s = unicodedata.normalize("NFD", str(name or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("đ", "d").replace("Đ", "D").replace("_", " ")
    return " ".join(s.lower().split())


# Bí danh cột. Thêm bí danh mới vào đây, không sửa hàm map_row.
ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "receivable": {
        "partner_code": ("ma kh", "ma khach hang", "ma doi tac", "partner_code", "customer_code"),
        "partner_name": ("ten kh", "ten khach hang", "khach hang", "partner_name"),
        "invoice_no": ("so hoa don", "so hd", "so chung tu", "invoice_no", "invoice"),
        "invoice_date": ("ngay hoa don", "ngay hd", "ngay chung tu", "invoice_date"),
        "due_date": ("ngay den han", "den han", "han thanh toan", "due_date"),
        "amount": ("gia tri", "so tien", "tong tien", "amount", "thanh tien"),
        "paid_amount": ("da thu", "da thanh toan", "paid", "paid_amount"),
        "outstanding": ("con lai", "con no", "du no", "outstanding", "balance"),
    },
    "revenue": {
        "period": ("ky", "thang", "period", "ky bao cao"),
        "channel": ("kenh", "kenh ban", "channel"),
        "store_code": ("ma ch", "ma cua hang", "cua hang", "store", "store_code"),
        "amount": ("doanh thu", "doanh thu thuan", "amount", "revenue"),
    },
    "expense": {
        "period": ("ky", "thang", "period"),
        "account_code": ("ma khoan muc", "ma tk", "account_code"),
        "account_name": ("ten khoan muc", "khoan muc", "account_name"),
        "department": ("phong ban", "bo phan", "department"),
        "amount": ("thuc te", "chi phi", "so tien", "amount"),
        "budget_amount": ("ngan sach", "du toan", "budget", "budget_amount"),
    },
}
ALIASES["payable"] = {
    **ALIASES["receivable"],
    "partner_code": ("ma ncc", "ma nha cung cap", "ma doi tac", "partner_code", "vendor_code"),
    "partner_name": ("ten ncc", "ten nha cung cap", "nha cung cap", "partner_name"),
}

# Cột không có trong bảng bí danh thì phải khai ở đây, nếu không map_row sẽ báo thiếu.
OPTIONAL: dict[str, frozenset[str]] = {
    "receivable": frozenset({"outstanding"}),   # thiếu thì suy ra từ amount - paid_amount
    "payable": frozenset({"outstanding"}),
    "revenue": frozenset({"store_code"}),
    "expense": frozenset({"department", "budget_amount"}),
}

_RECORD_TYPES = {
    "receivable": Receivable,
    "payable": Payable,
    "revenue": Revenue,
    "expense": Expense,
}


def _pick(row: dict, aliases: tuple[str, ...]) -> object | None:
    normalized = {normalize_header(k): v for k, v in row.items()}
    for alias in aliases:
        key = normalize_header(alias)
        if key in normalized:
            value = normalized[key]
            if str(value or "").strip() != "":
                return value
    return None


def map_row(table: str, row: dict, *, prov) -> object:
    """Dựng một bản ghi từ dòng thô. Raise SchemaError nêu rõ cột nào thiếu hoặc sai.

    Không điền giá trị mặc định cho cột bắt buộc bị thiếu — xem docs/DATA_MODEL.md.
    Riêng `outstanding` được suy ra từ `amount - paid_amount` khi sheet không có cột đó:
    đây là giá trị phái sinh từ dữ liệu thật, không phải giá trị bịa.
    """
    if table not in ALIASES:
        raise SchemaError(f"chưa hỗ trợ bảng {table!r}")

    raw: dict[str, object] = {}
    missing: list[str] = []
    for field_name, aliases in ALIASES[table].items():
        value = _pick(row, aliases)
        if value is None:
            if field_name not in OPTIONAL.get(table, frozenset()):
                missing.append(field_name)
            continue
        raw[field_name] = value

    if missing:
        raise SchemaError(f"thiếu cột bắt buộc: {', '.join(sorted(missing))}")

    if table in ("receivable", "payable"):
        amount = parse_money(raw["amount"])
        paid = parse_money(raw["paid_amount"])
        outstanding = parse_money(raw["outstanding"]) if "outstanding" in raw else amount - paid
        return _RECORD_TYPES[table](
            partner_code=str(raw["partner_code"]).strip(),
            partner_name=str(raw["partner_name"]).strip(),
            invoice_no=str(raw["invoice_no"]).strip(),
            invoice_date=parse_date(raw["invoice_date"]),
            due_date=parse_date(raw["due_date"]),
            amount=amount,
            paid_amount=paid,
            outstanding=outstanding,
            prov=prov,
        )

    if table == "revenue":
        return Revenue(
            period=_as_period(raw["period"]),
            channel=str(raw["channel"]).strip(),
            store_code=str(raw.get("store_code", "")).strip(),
            amount=parse_money(raw["amount"]),
            prov=prov,
        )

    return Expense(
        period=_as_period(raw["period"]),
        account_code=str(raw["account_code"]).strip(),
        account_name=str(raw["account_name"]).strip(),
        department=str(raw.get("department", "")).strip(),
        amount=parse_money(raw["amount"]),
        budget_amount=parse_money(raw["budget_amount"]) if "budget_amount" in raw else None,
        prov=prov,
    )


def _as_period(raw: object) -> str:
    """Chấp nhận "2026-07", "07/2026", "7/2026" hoặc date. Trả về "YYYY-MM"."""
    if isinstance(raw, datetime):
        return f"{raw.year:04d}-{raw.month:02d}"
    s = str(raw or "").strip()
    if "/" in s:
        parts = s.split("/")
        if len(parts) == 2:
            month, year = parts
            return f"{int(year):04d}-{int(month):02d}"
    return s
