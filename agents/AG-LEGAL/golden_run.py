#!/usr/bin/env python3
"""Golden set AG-LEGAL — chống BỊA NGUỒN (PLAN Phase 7 mục 44).

Điểm khác các agent khác: phép kiểm quan trọng nhất ở đây không phải "câu trả lời có
đúng chữ nào", mà là **mọi link trong mục 📎 Nguồn phải tồn tại thật trong bảng
legal_sources**. Một agent pháp chế bịa ra tên nghị định hoặc link tài liệu thì nguy hiểm
hơn là trả lời "chưa có quy định".

    python3 golden_run.py --selfcheck            # kiểm tĩnh file case, không cần token/mạng
    LSR_AGENT_TOKEN=... python3 golden_run.py --ask     # hỏi agent đang chạy, chấm điểm

`--ask` gọi Chat API của platform (không tự gửi Lark, không ghi gì lên platform ngoài
hội thoại test) rồi đối chiếu citation với legal_sources của chính agent.
"""
import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from legalkb.platform import Platform
from legalkb.store import SourceStore

CASES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden-cases.json")
LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")


def load():
    with open(CASES, encoding="utf-8") as f:
        return json.load(f)


def selfcheck():
    """Kiểm tĩnh: file case có hợp lệ và có phủ đủ 4 nhóm hành vi bắt buộc không."""
    cases, bad = load(), []
    ids = set()
    for c in cases:
        if not c.get("id") or not c.get("q"):
            bad.append(f"case thiếu id/q: {c}")
        if c["id"] in ids:
            bad.append(f"id trùng: {c['id']}")
        ids.add(c.get("id"))
        if "must_cite" not in c:
            bad.append(f"{c['id']}: thiếu must_cite — không kiểm được việc bịa nguồn")
        if not c.get("why"):
            bad.append(f"{c['id']}: thiếu 'why' — case không nói được nó bảo vệ điều gì")
    if not any(c.get("must_cite") for c in cases):
        bad.append("không có case nào bắt buộc trích dẫn → mất phép kiểm chống bịa nguồn")
    if not any(c.get("must_cite") is False for c in cases):
        bad.append("không có case nào kiểm việc TỪ CHỐI khi KB không có căn cứ")
    for b in bad:
        print("✗", b)
    print(f"{'✓' if not bad else '✗'} {len(cases)} case, {len(bad)} vấn đề")
    return 1 if bad else 0


def known_urls(store):
    return {r["lark_url"] for r in store.all_active() if r.get("lark_url")}


def grade(answer, case, urls):
    """Trả (pass, [lỗi]). Bịa nguồn là lỗi NẶNG, tính riêng."""
    errs = []
    low = (answer or "").lower()
    for w in case.get("must_have") or []:
        if w.lower() not in low:
            errs.append(f"thiếu '{w}'")
    for w in case.get("must_not_have") or []:
        if w.lower() in low:
            errs.append(f"không được có '{w}'")
    cited = LINK_RE.findall(answer or "")
    if case.get("must_cite") and not cited:
        errs.append("không có trích dẫn nào")
    for _title, url in cited:
        if urls and url not in urls:
            errs.append(f"BỊA NGUỒN: {url} không có trong legal_sources")
    return (not errs), errs


def ask(agent_id="AG-LEGAL", timeout=180):
    pf = Platform()
    if not pf.token:
        sys.exit("cần LSR_AGENT_TOKEN")
    store = SourceStore(os.environ.get("LEGALKB_DB"))
    urls = known_urls(store)
    if not urls:
        print("⚠️  legal_sources trống — chưa sync KB, phép kiểm bịa nguồn sẽ bỏ qua.\n")
    cases, n_pass = load(), 0
    for c in cases:
        try:
            r = pf.call("POST", f"/v1/chat/{agent_id}/messages",
                        {"text": c["q"], "session_id": f"golden-{c['id']}"},
                        timeout=timeout)
            answer = r.get("text") or r.get("reply") or ""
        except Exception as exc:
            print(f"✗ {c['id']}: gọi chat lỗi: {exc}")
            continue
        ok, errs = grade(answer, c, urls)
        n_pass += ok
        print(f"{'✓' if ok else '✗'} {c['id']}: {c['q'][:60]}")
        for e in errs:
            print(f"    - {e}")
    print(f"\n{n_pass}/{len(cases)} pass")
    return 0 if n_pass == len(cases) else 1


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--selfcheck", action="store_true")
    g.add_argument("--ask", action="store_true")
    a = ap.parse_args()
    sys.exit(selfcheck() if a.selfcheck else ask())


if __name__ == "__main__":
    main()
