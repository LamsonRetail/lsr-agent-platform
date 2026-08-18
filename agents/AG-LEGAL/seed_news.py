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
        print("— Nguồn luật —")
        for s in news.sources(store, only_active=False):
            flag = "on " if s["active"] else "off"
            err = f"  lỗi: {s['last_error']}" if s.get("last_error") else ""
            print(f"[{flag}] {s['name']:44} {s['url']}{err}")
        print("\n— Checklist đầu mục hồ sơ —")
        for r in store.query("SELECT * FROM dossier_checklists ORDER BY contract_type"):
            print(f"{r['contract_type']}: {len(json.loads(r['items']))} mục")
        return 0

    n = news.seed_sources(store)
    print(f"✓ nguồn luật: {len(news.DEFAULT_SOURCES)} nguồn (ghi {n})")
    for ctype, items in CHECKLISTS.items():
        signing.set_checklist(store, ctype, items)
        print(f"✓ checklist '{ctype}': {len(items)} mục")
    print("\n⚠️ Checklist trên là bộ KHỞI TẠO — nhờ Pháp chế soát lại rồi chỉnh trong "
          "seed_news.py và chạy lại.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
