#!/usr/bin/env python3
"""Nạp danh sách người duyệt của AG-LEGAL vào bảng `legal_roles`.

Chốt 17/08/2026 — 2 người: Nguyễn Trần Thi (BOD) và Nguyễn Thị Anh (Legal).
Cả hai đều có quyền duyệt mọi loại việc; platform chặn tự duyệt việc của chính mình nên
2 người là mức tối thiểu hợp lệ.

Dùng:
    python3 seed_roles.py            # nạp + resolve open_id qua broker platform
    python3 seed_roles.py --list     # xem đang có ai

Thêm/bớt người: sửa ROSTER rồi chạy lại. KHÔNG hard-code danh sách này vào consumer.py.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from legalkb.platform import Platform
from legalkb.store import SourceStore

# ⚠️ EMAIL CẦN XÁC NHẬN: chưa tra được email của chị Nguyễn Thị Anh (user token Lark CLI
# hết hạn). Placeholder dưới đây sẽ làm script BÁO LỖI thay vì âm thầm gửi sai người.
NEEDS_CONFIRM = "TODO_CONFIRM"

ROSTER = [
    # (email, tên, các vai trò, loại hợp đồng: None = mọi loại)
    ("thint@hapas.vn", "Nguyễn Trần Thi (BOD)",
     ["approver", "legal_reviewer", "digest_owner"], None),
    (f"{NEEDS_CONFIRM}@hapas.vn", "Nguyễn Thị Anh (Legal)",
     ["approver", "legal_reviewer", "digest_owner"], None),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    store = SourceStore(os.environ.get("LEGALKB_DB"))
    if args.list:
        rows = store.query("SELECT * FROM legal_roles ORDER BY email, role")
        if not rows:
            print("(trống)")
        for r in rows:
            print(f"{r['email']:32} {r['role']:16} open_id={r['open_id'] or '-'} "
                  f"active={r['active']} {r['name'] or ''}")
        return 0

    bad = [e for e, *_ in ROSTER if NEEDS_CONFIRM in e]
    if bad:
        print(f"✗ Chưa xác nhận email: {', '.join(bad)}\n"
              f"  Sửa ROSTER trong {__file__} rồi chạy lại. Không nạp gì cả để tránh "
              f"gửi thông báo/phê duyệt cho sai người.", file=sys.stderr)
        return 1

    for email, name, roles, ctype in ROSTER:
        for role in roles:
            store.write(
                "INSERT INTO legal_roles (email, role, contract_type, name, active) "
                "VALUES (?,?,?,?,1) ON CONFLICT(email, role, contract_type) DO UPDATE SET "
                "name=excluded.name, active=1", (email, role, ctype, name))
        print(f"✓ {email} — {', '.join(roles)}")

    pf = Platform()
    if not pf.token:
        print("⚠️  thiếu LSR_AGENT_TOKEN — chưa resolve được open_id. "
              "Chạy lại sau khi enroll; consumer cũng tự resolve lúc khởi động.")
        return 0
    n = 0
    for r in store.query("SELECT DISTINCT email FROM legal_roles WHERE active=1"):
        oid = pf.lark_resolve(r["email"])
        if oid:
            store.write("UPDATE legal_roles SET open_id=? WHERE email=?", (oid, r["email"]))
            print(f"  open_id {r['email']} → {oid}")
            n += 1
        else:
            print(f"  ⚠️ không resolve được open_id cho {r['email']} — kiểm email hoặc "
                  f"available range của app Lark", file=sys.stderr)
    print(f"Xong: {n} người có open_id (cần open_id mới gõ lệnh duyệt trong group được).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
