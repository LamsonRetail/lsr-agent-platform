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
     ["approver", "legal_reviewer", "digest_owner"], "*",
     "ou_c4a4e1e07b0dce1c484a1e7d3046b66c"),
    # Chị Nguyễn Thị Anh — Pháp chế, admin thứ hai (cung cấp 19/08/2026).
    # user_id Lark là `51fga65b`; KHÔNG dùng được để kiểm quyền vì payload tin nhắn mang
    # `sender_open_id` (tiền tố ou_), khác hệ id. Nên open_id để trống và script tự
    # resolve từ email qua broker /v1/lark/resolve.
    ("anhnt1@hapas.vn", "Nguyễn Thị Anh (Pháp chế)",
     ["approver", "legal_reviewer", "digest_owner"], "*",
     "ou_41b21c59e5bb6c435ed86c6bef149091"),   # resolve từ email 19/08, ghim lại
]

# ❌ KHÔNG BAO GIỜ đưa open_id của CHÍNH AGENT vào legal_roles.
# "Ann Nguyen" (ou_d386c1e6ddbea6160569647db6491f37) là **user account của agent** trên
# Lark, không phải người duyệt. Nếu để nó trong legal_roles thì agent tự duyệt gate của
# chính mình — phá đúng cái tách vai mà toàn bộ khung "Pháp chế in the loop" dựa vào.
# Danh sách này để consumer NHẬN RA và từ chối, chứ không phải để cấp quyền.
AGENT_OWN_OPEN_IDS = {
    "ou_d386c1e6ddbea6160569647db6491f37": "Ann Nguyen (user account của AG-LEGAL)",
}


def _housekeep(store):
    """Dọn dữ liệu cũ trước khi nạp. Ba việc, đều đã xảy ra thật ngày 19/08:

    1. `contract_type` NULL → '*': NULL trong SQLite không tự bằng nhau nên PK không
       dedupe, chạy seed 2 lần là có 2 dòng y hệt.
    2. Gỡ dòng trùng còn lại (giữ dòng cũ nhất).
    3. Gỡ open_id của CHÍNH AGENT nếu đã bị nạp nhầm làm người duyệt.
    """
    # THỨ TỰ QUAN TRỌNG: dedupe TRƯỚC rồi mới đổi NULL → '*'. Làm ngược lại thì UPDATE
    # vỡ UNIQUE constraint, vì GROUP BY coi các NULL là bằng nhau nhưng UNIQUE thì không.
    before = len(store.query("SELECT 1 FROM legal_roles"))
    store.write("DELETE FROM legal_roles WHERE rowid NOT IN "
                "(SELECT min(rowid) FROM legal_roles GROUP BY email, role, contract_type)")
    after = len(store.query("SELECT 1 FROM legal_roles"))
    if before != after:
        print(f"• dọn {before - after} dòng trùng (còn {after})")
    n = len(store.query("SELECT 1 FROM legal_roles WHERE contract_type IS NULL"))
    if n:
        store.write("UPDATE legal_roles SET contract_type='*' WHERE contract_type IS NULL")
        print(f"• chuẩn hoá {n} dòng contract_type NULL → '*'")
    for oid, who in AGENT_OWN_OPEN_IDS.items():
        rows = store.query("SELECT 1 FROM legal_roles WHERE open_id=?", (oid,))
        if rows:
            store.write("DELETE FROM legal_roles WHERE open_id=?", (oid,))
            print(f"⚠️  GỠ {len(rows)} dòng mang open_id của chính agent ({who}) — "
                  f"agent không được tự duyệt việc của mình")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    store = SourceStore(os.environ.get("LEGALKB_DB"))
    _housekeep(store)
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
        if open_id in AGENT_OWN_OPEN_IDS:
            print(f"✗ TỪ CHỐI nạp {name}: open_id này là user account của chính agent "
                  f"({AGENT_OWN_OPEN_IDS[open_id]}) — agent không được tự duyệt.",
                  file=sys.stderr)
            return 1
        for role in roles:
            # DELETE rồi INSERT: idempotent bất kể ngữ nghĩa PK, không phụ thuộc
            # ON CONFLICT (đã bị NULL làm vô hiệu một lần).
            store.write("DELETE FROM legal_roles WHERE email=? AND role=? AND contract_type=?",
                        (email, role, ctype or "*"))
            store.write(
                "INSERT INTO legal_roles (email, role, contract_type, name, open_id, active) "
                "VALUES (?,?,?,?,?,1)", (email, role, ctype or "*", name, open_id))
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
