#!/usr/bin/env python3
"""add_knowledge — nạp 1 mục tri thức vào brain riêng của AG-ASSISTANT-CHAN.

Dùng token của CHÍNH agent (không cần admin) — chỉ ghi vào brain của agent này,
scope='agent' (không lộ sang agent khác). Mục mới nạp status=pending, owner
duyệt trên Console (link /review) rồi agent mới tra được.

Dùng:
    python3 add_knowledge.py --title "Tên tài liệu" --content "Nội dung..." \\
        [--kind knowledge|process|definition|lesson|belief|faq] [--domain ten-domain] \\
        [--source-url https://...] [--tags "tag1,tag2"]

Hoặc nạp từ file:
    python3 add_knowledge.py --title "SOP abc" --content-file duong_dan_file.txt
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.request

PLATFORM = os.environ.get("LSR_PLATFORM_URL", "https://platform.34-126-154-135.sslip.io").rstrip("/")


def _load_env_local():
    path = os.path.join(os.path.dirname(__file__), ".env.local")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def main() -> int:
    _load_env_local()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--title", required=True)
    ap.add_argument("--content", default="")
    ap.add_argument("--content-file", default="")
    ap.add_argument("--kind", default="knowledge",
                     choices=["knowledge", "process", "definition", "lesson", "belief", "faq"])
    ap.add_argument("--domain", default="pmo")
    ap.add_argument("--source-url", default="")
    ap.add_argument("--tags", default="")
    args = ap.parse_args()

    content = args.content
    if args.content_file:
        content = open(args.content_file, encoding="utf-8").read()
    if not content.strip():
        print("✗ thiếu --content hoặc --content-file")
        return 1

    token = os.environ.get("LSR_AGENT_TOKEN", "")
    if not token:
        print("✗ thiếu LSR_AGENT_TOKEN (.env.local)")
        return 1

    payload = {
        "kind": args.kind,
        "title": args.title,
        "content": content,
        "domain": args.domain,
        "tags": args.tags,
        "source_url": args.source_url or None,
        "status": "pending",  # owner duyệt trên Console trước khi agent dùng
    }
    req = urllib.request.Request(
        PLATFORM + "/v1/self/brain/items",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        res = json.loads(r.read().decode())
    print(f"✓ Đã nộp: {res.get('item_id')} (status=pending) — duyệt tại Console → Duyệt tri thức")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
