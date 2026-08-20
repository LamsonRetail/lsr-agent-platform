#!/usr/bin/env python3
"""Nạp nguồn luật (S4) + checklist đầu mục hồ sơ trình ký (S5) vào DB của agent.

Legal team thêm/bớt bằng cách sửa file này rồi chạy lại — không sửa code nghiệp vụ.

    python3 seed_news.py            # nạp nguồn luật + checklist mẫu
    python3 seed_news.py --list     # xem đang có gì
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from legalkb import news, signing
from legalkb.store import SourceStore

# Checklist đầu mục hồ sơ trình ký. `*` = áp cho loại hợp đồng chưa khai riêng.
# ⚠️ Đây là bộ KHỞI TẠO do dev đặt để luồng chạy được — Pháp chế cần soát lại và chốt
# bộ thật (PLAN §10 câu hỏi 7). Chưa chốt thì báo cáo Bước 3 vẫn ghi rõ là tham khảo.
CHECKLISTS = {
    "*": [
        "Tờ trình/phiếu đề nghị trình ký có phê duyệt của quản lý trực tiếp",
        "Bản hợp đồng đầy đủ các trang, đã đánh số",
        "Giấy đăng ký kinh doanh của đối tác (bản sao)",
        "Thông tin pháp nhân & người đại diện hợp pháp của hai bên",
    ],
    "hợp đồng dịch vụ": [
        "Tờ trình/phiếu đề nghị trình ký có phê duyệt của quản lý trực tiếp",
        "Bản hợp đồng đầy đủ các trang, đã đánh số",
        "Giấy đăng ký kinh doanh của đối tác (bản sao)",
        "Báo giá / bảng giá dịch vụ kèm theo",
        "Phụ lục phạm vi công việc (SOW) nếu có",
        "Xác nhận ngân sách của bộ phận Tài chính",
    ],
    "hợp đồng mua bán": [
        "Tờ trình/phiếu đề nghị trình ký có phê duyệt của quản lý trực tiếp",
        "Bản hợp đồng đầy đủ các trang, đã đánh số",
        "Giấy đăng ký kinh doanh của đối tác (bản sao)",
        "Giấy phép/điều kiện kinh doanh ngành hàng (nếu hàng thuộc diện quản lý)",
        "Báo giá và điều kiện thanh toán",
        "Hồ sơ chất lượng/công bố sản phẩm nếu có",
    ],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    store = SourceStore(os.environ.get("LEGALKB_DB"))

    if args.list:
        print("— Nguồn luật (hằng tuần, thứ 2 07:00) —")
        for s in news.sources(store, only_active=False):
            flag = "ON " if s["active"] else "off"
            print(f"[{flag}] {s['country']:2} {s['kind']:4} {s['name'][:38]:38} {s['url']}")
            if s.get("last_error"):
                print(f"          ↳ lỗi lần chạy gần nhất: {s['last_error'][:90]}")
            if not s["active"] and s.get("note"):
                print(f"          ↳ cần gì để bật: {s['note'][:90]}")
        print("\n— Checklist đầu mục hồ sơ —")
        for r in store.query("SELECT * FROM dossier_checklists ORDER BY contract_type"):
            print(f"{r['contract_type']}: {len(json.loads(r['items']))} mục")
        return 0

    news.seed_sources(store)
    rows = news.sources(store, only_active=False)
    on = [r for r in rows if r["active"]]
    print(f"✓ nguồn luật: {len(rows)} nguồn ({len(on)} đang BẬT)")
    for r in rows:
        print(f"   [{'ON ' if r['active'] else 'off'}] {r['country']} · {r['name']}")
    print("\n⚠️ Chỉ nguồn đã KIỂM THẬT mới để bật. Nguồn tắt kèm ghi chú cần gì để bật "
          "(chạy `--list` để xem). Thêm/bật nguồn sẽ làm trên console agent sau.")
    for ctype, items in CHECKLISTS.items():
        signing.set_checklist(store, ctype, items)
        print(f"✓ checklist '{ctype}': {len(items)} mục")
    print("\n⚠️ Checklist trên là bộ KHỞI TẠO — nhờ Pháp chế soát lại rồi chỉnh trong "
          "seed_news.py và chạy lại.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
