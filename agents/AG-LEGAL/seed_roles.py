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

# Quyền được kiểm bằng `sender_open_id` của tin nhắn, nên OPEN_ID mới là thứ bắt buộc;
# email chỉ dùng để resolve ra open_id. Ai đã biết open_id thì khai thẳng — khỏi phụ thuộc
# vào việc app Lark có scope contact hay không.
#
# open_id lấy từ device-flow authorize ngày 19/08/2026 (`lark-cli auth status`).
NEEDS_CONFIRM = "TODO_CONFIRM"

ROSTER = [
    # (email, tên, vai trò, loại hợp đồng: None = mọi loại, open_id)
    ("thint@hapas.vn", "Nguyễn Trần Thi (BOD)",
     ["approver", "legal_reviewer", "digest_owner"], None,
     "ou_c4a4e1e07b0dce1c484a1e7d3046b66c"),
    # ⚠️ Email chưa xác nhận, nhưng ĐÃ CÓ open_id → vẫn duyệt được bằng lệnh trong group.
    # Tên trên Lark là "Ann Nguyen" — cần bạn xác nhận đúng là chị Nguyễn Thị Anh (Pháp chế).
    (f"{NEEDS_CONFIRM}-ann@hapas.vn", "Nguyễn Thị Anh (Legal)",
     ["approver", "legal_reviewer", "digest_owner"], None,
     "ou_d386c1e6ddbea6160569647db6491f37"),
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

    # Chỉ CHẶN khi vừa thiếu email vừa thiếu open_id — lúc đó thật sự không xác định được
    # người. Có open_id là đủ để duyệt, nên không chặn oan.
    blocked = [e for e, _n, _r, _c, oid in ROSTER if NEEDS_CONFIRM in e and not oid]
    if blocked:
        print(f"✗ Không xác định được người: {', '.join(blocked)} (thiếu cả email lẫn "
              f"open_id). Sửa ROSTER trong {__file__} rồi chạy lại — không nạp gì cả để "
              f"tránh gửi phê duyệt cho sai người.", file=sys.stderr)
        return 1

    for email, name, roles, ctype, open_id in ROSTER:
        for role in roles:
            store.write(
                "INSERT INTO legal_roles (email, role, contract_type, name, open_id, active) "
                "VALUES (?,?,?,?,?,1) ON CONFLICT(email, role, contract_type) DO UPDATE SET "
                "name=excluded.name, open_id=coalesce(excluded.open_id, legal_roles.open_id), "
                "active=1", (email, role, ctype, name, open_id))
        flag = "" if NEEDS_CONFIRM not in email else "  ⚠️ email chưa xác nhận (dùng open_id)"
        print(f"✓ {name} — {', '.join(roles)}{flag}")

    pf = Platform()
    if not pf.token:
        print("⚠️  thiếu LSR_AGENT_TOKEN — chưa resolve được open_id. "
              "Chạy lại sau khi enroll; consumer cũng tự resolve lúc khởi động.")
        return 0
    n = 0
    for r in store.query("SELECT DISTINCT email FROM legal_roles WHERE active=1 AND "
                         "(open_id IS NULL OR open_id='')"):
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
