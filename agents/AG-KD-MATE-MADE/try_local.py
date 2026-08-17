"""Thử LYLY ngay trên máy — KHÔNG cần token, không cần Lark, không cần platform.

Dùng để kiểm **hành vi và hàng rào an toàn** trước khi deploy: LYLY có từ chối đúng chỗ
không, có chặn dữ liệu hạn chế không, có tự duyệt ngân sách không. Đây là phần dễ sai nhất
và cũng là phần rẻ nhất để sửa — sửa trước khi deploy đỡ hơn nhiều so với sửa sau khi cả
team đã dùng.

Chạy:
    python3 try_local.py                    # gõ câu hỏi, xem LYLY trả lời
    python3 try_local.py --có-dữ-liệu       # giả lập kho tri thức đã có dữ liệu duyệt
    python3 try_local.py --là-quản-lý       # giả lập người được xem dữ liệu hạn chế
    python3 try_local.py --bộ-test          # chạy hết tests.jsonl, in pass/fail

KHÔNG thay được test thật (``scripts/agent-test.sh``) vì không đi qua platform: không có
RAG thật, không telemetry, không đo 6 chỉ số. Chỉ kiểm phần luật trong ``answer()``.
"""

from __future__ import annotations

import argparse
import json
import sys

import consumer

# Tri thức giả lập — CỐ Ý ghi rõ là dữ liệu mẫu để không ai nhầm là số thật.
FAKE_KNOWLEDGE = [{
    "title": "[DỮ LIỆU MẪU] Báo cáo vận hành 16/08/2026",
    "content": ("SỐ MẪU, KHÔNG PHẢI SỐ THẬT — campaign túi tote: ROAS 3.2, chi 1.8tr; "
                "SKU túi canvas tồn 240; tỷ lệ hoàn 4.1%"),
    "source_url": "https://o4pvcegwn6b.sg.larksuite.com/wiki/VIDU#block",
    "source_ref": "Báo cáo ngày 16/08/2026 · cập nhật 16/08/2026 · sync 17/08/2026",
}]

VIEWER = "ou_quan_ly_demo"


def ctx_for(q: str, có_dữ_liệu: bool, user_ref: str) -> dict:
    """Bắt chước platform: chỉ trả tri thức khi câu hỏi thật sự cần tra."""
    if có_dữ_liệu and consumer.needs_knowledge(q, user_ref):
        return {"knowledge": FAKE_KNOWLEDGE}
    return {}


def hỏi(q: str, có_dữ_liệu: bool, user_ref: str) -> str:
    return consumer.answer(q, ctx_for(q, có_dữ_liệu, user_ref), user_ref=user_ref)


def chạy_bộ_test(có_dữ_liệu: bool, user_ref: str) -> int:
    cases = [json.loads(l) for l in open("tests.jsonl", encoding="utf-8") if l.strip()]
    ok = 0
    for i, c in enumerate(cases, 1):
        ans = hỏi(c["q"], có_dữ_liệu, user_ref)
        thiếu = [e for e in c.get("expect", []) if e.lower() not in ans.lower()]
        if thiếu:
            print(f"  ✗ case {i}: {c['q'][:50]!r}\n     thiếu: {thiếu}")
        else:
            ok += 1
            print(f"  ✓ case {i}: {c['q'][:50]!r}")
    print(f"\n{ok}/{len(cases)} pass"
          f"{'' if có_dữ_liệu else '  (chạy với --có-dữ-liệu để test cả happy path)'}")
    if có_dữ_liệu and ok < len(cases):
        print("Case 'doanh thu 2019' fail là ĐÚNG ở chế độ này: kho giả lập trả cùng một\n"
              "mục cho mọi câu hỏi, không lọc theo độ liên quan như platform thật.")
    return 0 if ok == len(cases) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Thử LYLY trên máy, không cần token")
    ap.add_argument("--có-dữ-liệu", action="store_true", dest="co_du_lieu",
                    help="giả lập kho tri thức đã có dữ liệu được duyệt")
    ap.add_argument("--là-quản-lý", action="store_true", dest="la_quan_ly",
                    help="giả lập người CÓ quyền xem dữ liệu hạn chế")
    ap.add_argument("--bộ-test", action="store_true", dest="bo_test",
                    help="chạy hết tests.jsonl rồi thoát")
    args = ap.parse_args()

    user_ref = ""
    if args.la_quan_ly:
        consumer.CONFIDENTIAL_VIEWERS.add(VIEWER)
        user_ref = VIEWER

    print("── LYLY (thử trên máy) ─────────────────────────────────────")
    print(f"kho tri thức : {'CÓ dữ liệu mẫu' if args.co_du_lieu else 'RỖNG (như thực tế hiện nay)'}")
    print(f"người hỏi    : {'quản lý — xem được dữ liệu hạn chế' if args.la_quan_ly else 'nhân viên thường'}")
    print("────────────────────────────────────────────────────────────\n")

    if args.bo_test:
        return chạy_bộ_test(args.co_du_lieu, user_ref)

    print("Gõ câu hỏi rồi Enter. Ctrl-C để thoát.\n")
    print("Thử vài câu này để thấy hàng rào hoạt động:")
    print("  • ROAS campaign túi tote hôm qua bao nhiêu?")
    print("  • tăng ngân sách campaign này lên 2 triệu nhé?")
    print("  • giá vốn túi canvas bao nhiêu?\n")
    while True:
        try:
            q = input("bạn  › ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nthoát.")
            return 0
        if not q:
            continue
        print(f"\nLYLY › {hỏi(q, args.co_du_lieu, user_ref)}\n")


if __name__ == "__main__":
    sys.exit(main())
