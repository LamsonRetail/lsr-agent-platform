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
# ⚠️ open_id của Lark thuộc TỪNG APP: cùng một người, mỗi app thấy một open_id khác. Nên
# account của agent phải chặn theo open_id của **mọi app** từng gặp, không chỉ một.
AGENT_OWN_OPEN_IDS = {
    "ou_d386c1e6ddbea6160569647db6491f37": "ann_legal@hapas.vn (theo app Admin platform)",
    "ou_6e62405ebd718453f6473554ea637e85": "ann_legal@hapas.vn (theo app AG-LEGAL "
                                           "cli_aa0f9ac50cf8dee9 — app nhận tin)",
}
# Chặn theo cả EMAIL, không chỉ open_id: đổi/ tạo lại account là open_id đổi, còn email
# thì thường giữ nguyên → chặn hai lớp cho chắc.
AGENT_OWN_EMAILS = {"ann_legal@hapas.vn"}


def _name_tokens(s):
    import re as _re
    drop = {"bod", "phap", "che", "chế", "pháp", "legal", "mr", "ms", "anh", "chi", "chị"}
    toks = {t for t in _re.split(r"[^\w]+", (s or "").lower()) if len(t) > 1}
    return toks - drop


def sync_open_ids_from_group(kb, store, chat_id, log=print):
    """Nạp open_id của người duyệt **theo đúng app đang nhận tin**, lấy từ thành viên group.

    Vì sao cần: quyền duyệt kiểm bằng `sender_open_id`, mà open_id của Lark **thuộc từng
    app**. `/v1/lark/resolve` của platform dùng app mặc định của platform, không phải app
    của AG-LEGAL ⇒ open_id lấy về không khớp ⇒ **đúng người vẫn bị từ chối lệnh duyệt**,
    và thông báo chỉ nói "chưa có quyền". Đã xảy ra thật: 21/08 cả hai người duyệt đều có
    open_id sai.

    Cách làm không cần thêm scope: đọc thành viên group bằng chính app đó rồi khớp theo
    TÊN. Khớp theo tập token và đòi **bao trùm hoàn toàn** — "Nguyễn Trần Thi" với
    "Nguyễn Thị Anh" trùng hai token nên khớp lỏng là gán sai người duyệt.
    """
    members = kb.chat_members(chat_id)
    n = 0
    for row in store.query("SELECT DISTINCT email, name FROM legal_roles"):
        if (row["email"] or "").lower() in AGENT_OWN_EMAILS:
            continue
        want = _name_tokens(row["name"] or row["email"])
        hit = [oid for nm, oid in members
               if want and (want <= _name_tokens(nm) or _name_tokens(nm) <= want)]
        if len(hit) != 1:
            log(f"  ⚠️  {row['name'] or row['email']}: khớp {len(hit)} thành viên — bỏ qua "
                f"(sửa tay bằng --map)")
            continue
        if hit[0] in AGENT_OWN_OPEN_IDS:
            log(f"  ✗ TỪ CHỐI {row['email']}: khớp vào account của chính agent")
            continue
        cur = store.one("SELECT open_id FROM legal_roles WHERE email=?", (row["email"],))
        if (cur or {}).get("open_id") == hit[0]:
            log(f"  = {row['name']}: open_id đã đúng")
            continue
        store.write("UPDATE legal_roles SET open_id=? WHERE email=?", (hit[0], row["email"]))
        log(f"  ✓ {row['name']}: open_id → {hit[0]}")
        n += 1
    return n


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
        rows = store.query("SELECT 1 FROM legal_roles WHERE open_id=? OR lower(email)=?",
                           (oid, who.split()[0].lower()))
        if rows:
            store.write("DELETE FROM legal_roles WHERE open_id=? OR lower(email)=?",
                        (oid, who.split()[0].lower()))
            print(f"⚠️  GỠ {len(rows)} dòng mang open_id của chính agent ({who}) — "
                  f"agent không được tự duyệt việc của mình")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--sync-from-group", action="store_true",
                    help="nạp open_id người duyệt từ thành viên group, theo ĐÚNG app đang "
                         "nhận tin (open_id của Lark thuộc từng app)")
    ap.add_argument("--map", nargs=2, metavar=("OPEN_ID", "EMAIL"),
                    help="gán open_id (theo app đang nhận tin) cho người đã có trong "
                         "legal_roles. Cần vì open_id của Lark thuộc TỪNG APP: đổi app "
                         "nhận tin là đúng người vẫn bị từ chối lệnh duyệt.")
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

    if args.sync_from_group:
        from legalkb.lark_kb import LarkKB
        chat = os.environ.get("LEGAL_GROUP_CHAT_ID")
        if not chat:
            print("✗ thiếu LEGAL_GROUP_CHAT_ID", file=sys.stderr)
            return 1
        kb = LarkKB(os.environ["LARK_APP_ID"], os.environ["LARK_APP_SECRET"])
        n = sync_open_ids_from_group(kb, store, chat)
        print(f"Xong: cập nhật {n} người.")
        return 0

    if args.map:
        open_id, email = args.map[0].strip(), args.map[1].strip().lower()
        if open_id in AGENT_OWN_OPEN_IDS or email in AGENT_OWN_EMAILS:
            print(f"✗ TỪ CHỐI: đây là user account của chính agent — agent không được tự "
                  f"duyệt việc của mình.", file=sys.stderr)
            return 1
        rows = store.query("SELECT role FROM legal_roles WHERE lower(email)=?", (email,))
        if not rows:
            print(f"✗ {email} chưa có trong legal_roles. Thêm vào ROSTER rồi chạy "
                  f"`seed_roles.py` trước.", file=sys.stderr)
            return 1
        store.write("UPDATE legal_roles SET open_id=? WHERE lower(email)=?",
                    (open_id, email))
        print(f"✓ {email}: open_id = {open_id} ({len(rows)} vai trò)")
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
        if email.lower() in AGENT_OWN_EMAILS:
            print(f"✗ TỪ CHỐI nạp {email}: đây là user account của chính agent — "
                  f"agent không được tự duyệt việc của mình.", file=sys.stderr)
            return 1
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
