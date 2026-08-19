"""Nạp tồn kho từ Lark Base — thay cho file Excel.

Vì sao có file này: bot đang đọc tồn kho từ file Excel trên máy cá nhân. Đưa
bot lên cloud thì không còn file đó, và số liệu cũng chỉ mới tới lúc ai đó
nhớ xuất file. Base "QL KẾ HOẠCH HÀNG HÓA HAPAS" là nguồn KHHH cập nhật hằng
ngày, nên đọc thẳng từ đó thì số luôn mới và không phụ thuộc máy nào cả.

Trả về đúng kiểu ``SkuResult`` mà ``qa.py`` đang dùng, nên phần trả lời câu
hỏi không phải sửa gì.

Dùng độc lập để kiểm tra:
    python lark_base.py                 # in 10 mã tồn cao nhất
    python lark_base.py --sku ORA26001  # tra 1 mã
"""

from __future__ import annotations

import argparse
import logging
import os

import requests
from dotenv import find_dotenv, load_dotenv

from inventory_days import SkuResult

logger = logging.getLogger("lark-base")

# Cùng Base/bảng mà khhh_report.py đang dùng — một nguồn sự thật, không tách hai.
BASE_TOKEN = "F7ZxbjBiuah1wtswfbVlmu9ygxh"      # QL KẾ HOẠCH HÀNG HÓA HAPAS
TABLE_ID = "tblDYIZcBY54VCQI"                   # BÁO CÁO KẾ HOẠCH HÀNG HOÁ

F_SP = "SP"
F_NHOM = "Phân loại 2"          # BST
F_TON = "Tồn kho"
F_TDB = "TĐB 7 ngày"            # ⚠️ trung bình MỖI NGÀY, không phải tổng 7 ngày
F_DUONG = "Số lượng đang trên đường"

FIELDS = [F_SP, F_NHOM, F_TON, F_TDB, F_DUONG]

TOKEN_TTL_MARGIN = 120


def _num(rec: dict, key: str) -> float:
    """Ô Base có thể là số, list, hoặc dict {text/value} tuỳ loại trường."""
    v = rec.get(key)
    if isinstance(v, list):
        v = v[0] if v else 0
    if isinstance(v, dict):
        v = v.get("value") or v.get("text") or 0
        if isinstance(v, list):
            v = v[0] if v else 0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _text(rec: dict, key: str) -> str:
    v = rec.get(key)
    if isinstance(v, list):
        v = v[0] if v else ""
    if isinstance(v, dict):
        v = v.get("text") or v.get("value") or ""
    return str(v or "").strip()


class BaseReader:
    def __init__(self, app_id: str, app_secret: str, domain: str) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._domain = domain.rstrip("/")
        self._token: str | None = None
        self._expire_at = 0.0

    def _token_value(self) -> str:
        import time
        if self._token and time.monotonic() < self._expire_at:
            return self._token
        r = requests.post(
            f"{self._domain}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": self._app_id, "app_secret": self._app_secret}, timeout=30)
        r.raise_for_status()
        p = r.json()
        if p.get("code") != 0:
            raise RuntimeError(f"Lấy token thất bại: {p}")
        self._token = p["tenant_access_token"]
        self._expire_at = time.monotonic() + int(p.get("expire", 7200)) - TOKEN_TTL_MARGIN
        return self._token

    def records(self) -> list[dict]:
        """Toàn bộ bản ghi, tự phân trang."""
        out: list[dict] = []
        page = None
        while True:
            r = requests.post(
                f"{self._domain}/open-apis/bitable/v1/apps/{BASE_TOKEN}"
                f"/tables/{TABLE_ID}/records/search",
                params={"page_size": 500, **({"page_token": page} if page else {})},
                headers={"Authorization": f"Bearer {self._token_value()}"},
                json={"field_names": FIELDS}, timeout=60)
            r.raise_for_status()
            p = r.json()
            if p.get("code") != 0:
                raise RuntimeError(
                    f"Đọc Base thất bại: {p}. Kiểm tra scope bitable:app:readonly "
                    f"và bot đã được thêm làm cộng tác viên của Base chưa.")
            d = p["data"]
            out += [it.get("fields", {}) for it in d.get("items", [])]
            if not d.get("has_more"):
                return out
            page = d.get("page_token")


def to_skus(records: list[dict]) -> list[SkuResult]:
    """Bản ghi Base -> SkuResult. Bỏ dòng không có tên mã."""
    skus: list[SkuResult] = []
    for rec in records:
        name = _text(rec, F_SP)
        if not name:
            continue
        ton = _num(rec, F_TON)
        duong = _num(rec, F_DUONG)
        tdb = _num(rec, F_TDB)
        total = ton + duong
        # TĐB = 0 -> không quy đổi ra ngày tồn được (vốn chết), để None chứ
        # không để 0 — 0 ngày nghĩa là sắp hết, ngược hẳn ý nghĩa.
        skus.append(SkuResult(
            sku=name,
            name=name,
            collection=_text(rec, F_NHOM) or None,
            current_qty=ton,
            total_qty=total,
            velocity_per_day=tdb,
            current_days=(ton / tdb) if tdb > 0 else None,
            total_days=(total / tdb) if tdb > 0 else None,
        ))
    return skus


def load_base_skus(app_id: str | None = None, app_secret: str | None = None,
                   domain: str | None = None) -> list[SkuResult]:
    """Nạp tồn kho từ Base. Thiếu credential -> đọc từ biến môi trường."""
    app_id = app_id or os.environ.get("LARK_APP_ID_INVENTORY") or os.environ["LARK_APP_ID"]
    app_secret = (app_secret or os.environ.get("LARK_APP_SECRET_INVENTORY")
                  or os.environ["LARK_APP_SECRET"])
    domain = domain or os.environ.get("LARK_DOMAIN", "https://open.larksuite.com")
    return to_skus(BaseReader(app_id, app_secret, domain).records())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sku", help="Tra đúng 1 mã")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv(find_dotenv(usecwd=True))

    skus = load_base_skus()
    print(f"Nạp được {len(skus)} mã từ Base.\n")

    if args.sku:
        found = [s for s in skus if args.sku.upper() in s.sku.upper()]
        if not found:
            print(f"Không thấy mã {args.sku}.")
            return 1
        for s in found[:10]:
            days = f"{s.current_days:,.1f} ngày" if s.current_days is not None else "TĐB=0 (vốn chết)"
            print(f"{s.sku} [{s.collection}]: tồn {s.current_qty:,.0f} · "
                  f"trên đường {s.total_qty - s.current_qty:,.0f} · "
                  f"bán {s.velocity_per_day:,.1f}/ngày · {days}")
        return 0

    rated = [s for s in skus if s.current_days is not None]
    print(f"--- {args.top} mã TỒN CAO nhất")
    for s in sorted(rated, key=lambda x: -x.current_days)[:args.top]:
        print(f"  {s.current_days:8,.0f} ngày  {s.sku[:48]}")
    print(f"\n--- {args.top} mã TỒN THẤP nhất (rủi ro hết hàng)")
    for s in sorted([x for x in rated if x.velocity_per_day > 0],
                    key=lambda x: x.current_days)[:args.top]:
        print(f"  {s.current_days:8,.1f} ngày  {s.sku[:48]}")
    dead = [s for s in skus if s.current_days is None and s.current_qty > 0]
    print(f"\n--- {len(dead)} mã còn tồn nhưng TĐB=0 (vốn chết)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
