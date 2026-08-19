#!/usr/bin/env python3
"""Kiểm tra đường số sống BigQuery (CẦN mạng + env/bq-service-account.json).

Không nằm trong bộ offline vì phụ thuộc mạng. Chạy trước khi go-live và mỗi khi
đổi configs/th_bq.json:  python3 tests/check_bq.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.pop("PLOY_OFFLINE", None)
import bq  # noqa: E402
import thailand_tools as tt  # noqa: E402

loi = []


def kiem(ten, dieu_kien, chi_tiet=""):
    print(("✅ " if dieu_kien else "❌ ") + ten + (f" — {chi_tiet}" if chi_tiet and not dieu_kien else ""))
    if not dieu_kien:
        loi.append(ten)


# 1. Khoá + quyền
try:
    r = bq.query("SELECT 1 AS ok")
    kiem("kết nối BigQuery bằng service account", r["dong"][0][0] == "1")
except Exception as e:
    kiem("kết nối BigQuery bằng service account", False, str(e))

# 2. Luật chỉ-đọc
for sql in ("DELETE FROM x", "DROP TABLE x", "SELECT 1; SELECT 2", "INSERT INTO t VALUES(1)"):
    try:
        bq.check_sql(sql)
        kiem(f"chặn câu ghi: {sql[:20]}", False, "KHÔNG bị chặn")
    except bq.BQError:
        kiem(f"chặn câu ghi: {sql[:20]}", True)

# 3. Mọi truy vấn trong config đều chạy được
cfg = tt.load_config("th_bq") or {}
for ten, q in (cfg.get("cac_truy_van") or {}).items():
    try:
        res = bq.query(q["sql"])
        kiem(f"truy vấn '{ten}'", True, f"{res['so_dong']} dòng")
    except Exception as e:
        kiem(f"truy vấn '{ten}'", False, str(e)[:120])

# 4. Ploy trả lời có số thật
for q in ("doanh số tháng này", "doanh số hôm qua", "kênh nào bán tốt nhất"):
    a = tt.th_bq_sales(q)
    kiem(f"Ploy trả lời '{q}'", bool(a) and "BigQuery" in a, (a or "rỗng")[:80])

print(f"\n{'ĐẠT ✅' if not loi else 'SAI: ' + ', '.join(loi)}")
sys.exit(1 if loi else 0)
