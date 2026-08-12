"""Nạp tri thức Finance & Accounting từ agents/AG-HARRY/knowledge/*.md vào
brain riêng của AG-HARRY (POST /v1/self/brain/items — endpoint thật của
platform_api, xem infra/lsr-platform/platform_api/app.py).

Dùng:
    python3 seed_brain.py --dry-run          # xem trước, không gọi API
    LSR_AGENT_TOKEN=... python3 seed_brain.py

File .md bắt đầu bằng "_" (vd _TEMPLATE.md) bị bỏ qua.
"""
import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8")

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"
PLATFORM = os.environ.get("LSR_PLATFORM_URL", "https://platform.34-126-154-135.sslip.io").rstrip("/")
KIND_OK = {"knowledge", "process", "definition", "lesson", "belief", "faq"}


def parse_item(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        raise ValueError(f"{path.name}: thiếu front matter (---title/domain/...---)")
    _, front, content = raw.split("---", 2)
    meta = yaml.safe_load(front) or {}
    if not meta.get("title"):
        raise ValueError(f"{path.name}: thiếu 'title' trong front matter")
    kind = meta.get("kind", "knowledge")
    if kind not in KIND_OK:
        raise ValueError(f"{path.name}: kind={kind!r} không hợp lệ (phải thuộc {KIND_OK})")
    return {
        "item_id": f"ak_ag_harry_{path.stem}",
        "kind": kind,
        "title": meta["title"],
        "content": content.strip(),
        "domain": meta.get("domain", "finance-accounting"),
        "tags": meta.get("tags") or [],
        "source_url": meta.get("source_url"),
        "status": "approved",
    }


def post_item(token: str, item: dict) -> dict:
    req = urllib.request.Request(
        f"{PLATFORM}/v1/self/brain/items",
        data=json.dumps(item).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode() or "{}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="chỉ in ra, không gọi API")
    args = ap.parse_args()

    files = sorted(
        p for p in KNOWLEDGE_DIR.glob("*.md")
        if not p.name.startswith("_") and p.name.upper() != "README.MD"
    )
    if not files:
        print(f"Chưa có file tri thức nào trong {KNOWLEDGE_DIR} — copy từ _TEMPLATE.md rồi điền nội dung thật.")
        return

    token = os.environ.get("LSR_AGENT_TOKEN", "")
    if not args.dry_run and not token:
        raise SystemExit("thiếu LSR_AGENT_TOKEN (hoặc chạy với --dry-run để xem trước)")

    ok, failed = 0, []
    for path in files:
        try:
            item = parse_item(path)
        except ValueError as e:
            print(f"✗ {e}")
            failed.append(path.name)
            continue
        if args.dry_run:
            print(f"[dry-run] {path.name} -> item_id={item['item_id']} kind={item['kind']} title={item['title']!r}")
            ok += 1
            continue
        try:
            res = post_item(token, item)
            print(f"✓ {path.name} -> {res.get('item_id')}")
            ok += 1
        except Exception as exc:
            print(f"✗ {path.name}: lỗi gọi API: {exc}")
            failed.append(path.name)

    print(f"\nKẾT QUẢ: {ok}/{len(files)} nạp {'(dry-run)' if args.dry_run else 'thành công'}"
          + (f" — lỗi: {failed}" if failed else ""))


if __name__ == "__main__":
    main()
