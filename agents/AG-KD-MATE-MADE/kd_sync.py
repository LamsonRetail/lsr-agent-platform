"""kd_sync — đồng bộ dữ liệu team Kinh Doanh → hàng chờ tri thức của AG-KD-MATE-MADE.

Chạy ĐỊNH KỲ HÀNG NGÀY (mặc định 6h sáng giờ VN): pipeline và báo cáo đổi mỗi ngày, agent
trả lời bằng số cũ là trả lời sai.

Mỗi lần chạy:
  1. **Lark Base** (pipeline / đơn hàng / khách hàng) → domain ``kd-confidential``,
     ``scope=agent`` — chỉ AG-KD-MATE-MADE tra được, agent khác trong công ty không.
  2. **Drive/Sheets báo cáo** → domain ``kd-report``, ``scope=shared``.
  3. (tuỳ chọn, mặc định TẮT) **Wiki KD** → domain ``business-context`` — xem ghi chú dưới.
  4. Nộp ``POST /v1/brain/items`` (status=pending) → người team KD duyệt trên console.

KHÔNG tự đưa tri thức vào diện đã duyệt — mọi thứ phải qua người.

Vì sao ``/v1/brain/items`` chứ không phải ``/v1/knowledge/items``: chỉ endpoint này nhận
``scope``/``agent_id`` — điều kiện để giá vốn/danh sách khách chỉ AG-KD-MATE-MADE đọc được.

**Chỉ nộp phần THAY ĐỔI.** Endpoint upsert đặt lại ``status=pending`` mỗi lần ghi; nộp mù
cả kho thì mỗi ngày team KD phải duyệt lại toàn bộ. Trước khi nộp, job đọc tri thức hiện
có và bỏ qua mục có nội dung y hệt.

---
**Về wiki space KD (``KD_SYNC_WIKI``) — đọc trước khi bật.**

Space ``7496094770155061279`` (TEAM KINH DOANH MATE MADE) cũng nằm trong danh sách sync
của agent Pháp chế (``agents/AG-LEGAL/legal_sync.py``, domain ``business-context``).
AG-LEGAL **chưa merge vào main** tại thời điểm viết file này.

  • AG-LEGAL chưa merge → bật ``KD_SYNC_WIKI=true`` để có tri thức wiki dùng ngay.
  • AG-LEGAL đã merge   → **tắt** (``false``), nếu không mỗi mục wiki sẽ có 2 bản trong
    hàng chờ: team KD phải duyệt 2 lần và RAG trả kết quả trùng.

Mặc định TẮT — trạng thái an toàn hơn là trạng thái tiện hơn.
---

Chạy thử không ghi gì:  python3 kd_sync.py --dry-run
Chạy 1 lần rồi thoát:   python3 kd_sync.py --once
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

from lark_docs import LarkDocs, LarkDocsError

PLATFORM = os.environ.get("LSR_PLATFORM_URL", "http://platform_api:8090").rstrip("/")
ADMIN = os.environ.get("PLATFORM_ADMIN_TOKEN", "")
AGENT_ID = os.environ.get("LSR_AGENT_ID", "AG-KD-MATE-MADE")
RUN_HOUR = int(os.environ.get("KD_SYNC_HOUR", "6"))
RUN_ON_START = os.environ.get("KD_SYNC_ON_START", "false").lower() == "true"
MAX_CHARS = int(os.environ.get("KD_CHUNK_CHARS", "1800"))
ROWS_PER_ITEM = int(os.environ.get("KD_ROWS_PER_ITEM", "20"))
SYNC_WIKI = os.environ.get("KD_SYNC_WIKI", "false").lower() == "true"
TZ = timezone(timedelta(hours=7))  # Asia/Ho_Chi_Minh

# Wiki space KD — chỉ dùng khi SYNC_WIKI=true (xem ghi chú đầu file).
KD_WIKI_SPACE = os.environ.get("KD_WIKI_SPACE", "7496094770155061279")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("kd-sync")

_H = {"Authorization": f"Bearer {ADMIN}", "Content-Type": "application/json"}


def today() -> str:
    return datetime.now(TZ).strftime("%d/%m/%Y")


def bases() -> list[dict]:
    """Lark Base cần đồng bộ. Khai bằng env ``KD_BASES`` (JSON).

    Ví dụ::

        KD_BASES='[{"app_token":"bascn...","label":"Pipeline bán hàng"}]'

    Bỏ trống ``tables`` = đồng bộ mọi bảng trong Base.
    """
    raw = os.environ.get("KD_BASES", "").strip()
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.warning("KD_BASES không phải JSON hợp lệ — bỏ qua nguồn Lark Base")
        return []


def folders() -> list[dict]:
    """Folder Drive báo cáo. Khai bằng env ``KD_FOLDERS`` (JSON).

    Ví dụ::

        KD_FOLDERS='[{"folder_token":"fldcn...","label":"Báo cáo doanh số"}]'
    """
    raw = os.environ.get("KD_FOLDERS", "").strip()
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.warning("KD_FOLDERS không phải JSON hợp lệ — bỏ qua nguồn Drive")
        return []


def seconds_until_next_run(now: datetime | None = None) -> float:
    """Số giây tới lần chạy kế (RUN_HOUR giờ VN, mỗi ngày)."""
    now = now or datetime.now(TZ)
    target = now.replace(hour=RUN_HOUR, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def render_rows(rows: list[dict]) -> str:
    """Đổi record Lark Base thành text tra cứu được.

    Giữ nguyên tên field để người đọc đối chiếu được với bảng gốc.
    """
    out = []
    for r in rows:
        fields = r.get("fields") or {}
        pairs = [f"{k}: {v}" for k, v in fields.items()
                 if v not in (None, "", [], {})]
        if pairs:
            out.append(" | ".join(pairs))
    return "\n".join(out)


# ----------------------------- thu thập từng nguồn -----------------------------

def collect_bases(docs: LarkDocs) -> list[dict]:
    """Lark Base → tri thức NHẠY CẢM (scope=agent).

    Gom ``ROWS_PER_ITEM`` dòng thành một mục thay vì mỗi dòng một mục: một Base pipeline
    vài nghìn dòng sẽ đẻ ra vài nghìn mục cần người duyệt — không ai duyệt nổi, và hàng
    chờ trở thành nút thắt thay vì hàng rào.

    Đánh đổi: record sắp theo ``record_id`` rồi mới chia khối, nên thêm dòng mới thường
    chỉ làm khối CUỐI đổi nội dung. Sửa một dòng ở giữa sẽ khiến khối chứa nó phải duyệt
    lại — chấp nhận được, đổi lại số mục nhỏ.
    """
    items: list[dict] = []
    stamp = today()
    for b in bases():
        app_token, label = b.get("app_token"), b.get("label") or b.get("app_token")
        if not app_token:
            continue
        try:
            tables = docs.bitable_tables(app_token)
        except LarkDocsError as exc:
            log.warning("bỏ qua Base %s: %s", label, exc)
            continue
        wanted = set(b.get("tables") or [])
        log.info("Base %s: %d bảng", label, len(tables))
        for t in tables:
            tid, tname = t.get("table_id"), t.get("name") or t.get("table_id")
            if not tid or (wanted and tid not in wanted and tname not in wanted):
                continue
            try:
                records = docs.bitable_records(app_token, tid)
            except LarkDocsError as exc:
                log.warning("đọc lỗi bảng '%s': %s", tname, exc)
                continue
            records.sort(key=lambda r: str(r.get("record_id") or ""))
            for idx in range(0, len(records), ROWS_PER_ITEM):
                chunk = records[idx:idx + ROWS_PER_ITEM]
                body = render_rows(chunk)
                if not body:
                    continue
                part = idx // ROWS_PER_ITEM + 1
                items.append({
                    "item_id": f"kd_bt_{app_token[:10]}_{tid[:10]}_{part:04d}",
                    "kind": "knowledge",
                    "title": f"{label} › {tname} (phần {part})",
                    "content": body[:MAX_CHARS],
                    "domain": "kd-confidential",
                    "tags": ["lark-base", label, tname],
                    # NHẠY CẢM: giá vốn / chiết khấu / khách hàng. Đổi thành "shared" là
                    # mở dữ liệu này cho mọi agent trong công ty — đừng đổi.
                    "scope": "agent",
                    "agent_id": AGENT_ID,
                    "source_agent": AGENT_ID,
                    "source_team": "Kinh doanh Mate Made",
                    "source_ref": f"{tname} · sync {stamp}",
                    "source_url": docs.bitable_url(app_token, tid),
                })
    return items


def collect_folders(docs: LarkDocs) -> list[dict]:
    """Drive/Sheets báo cáo → tri thức dùng chung (scope=shared)."""
    items: list[dict] = []
    stamp = today()
    skipped: dict[str, int] = {}
    for f in folders():
        ftoken, label = f.get("folder_token"), f.get("label") or f.get("folder_token")
        if not ftoken:
            continue
        try:
            files = docs.drive_files(ftoken)
        except LarkDocsError as exc:
            log.warning("bỏ qua folder %s: %s", label, exc)
            continue
        log.info("folder %s: %d file", label, len(files))
        for fi in files:
            ftype, token, name = fi.get("type"), fi.get("token"), fi.get("name") or ""
            # v1 chỉ đọc docx. sheet/bitable/pdf cần parser riêng — báo rõ thay vì im lặng.
            if ftype != "docx" or not token:
                skipped[ftype or "?"] = skipped.get(ftype or "?", 0) + 1
                continue
            try:
                sections = docs.docx_sections(token, doc_title=name, max_chars=MAX_CHARS)
            except LarkDocsError as exc:
                log.warning("đọc lỗi '%s': %s", name, exc)
                continue
            for s in sections:
                items.append({
                    "item_id": f"kd_dv_{token[:12]}_{(s['block_id'] or 'x')[:12]}",
                    "kind": "knowledge",
                    "title": f"{name} › {s['title']}" if s["title"] != name else name,
                    "content": s["content"],
                    "domain": "kd-report",
                    "tags": ["lark-drive", label],
                    "scope": "shared",
                    "agent_id": None,
                    "source_agent": AGENT_ID,
                    "source_team": "Kinh doanh Mate Made",
                    "source_ref": f"{s['heading_path']} · sync {stamp}",
                    "source_url": s["source_url"],
                })
    if skipped:
        log.warning("bỏ qua file không đọc được (v1 chỉ đọc docx): %s", skipped)
    return items


def collect_wiki(docs: LarkDocs) -> list[dict]:
    """Wiki KD → business-context. CHỈ chạy khi ``KD_SYNC_WIKI=true`` (xem đầu file)."""
    items: list[dict] = []
    stamp = today()
    try:
        nodes = docs.wiki_nodes(KD_WIKI_SPACE)
    except LarkDocsError as exc:
        log.warning("bỏ qua wiki space %s: %s", KD_WIKI_SPACE, exc)
        return items
    log.info("wiki space %s: %d node", KD_WIKI_SPACE, len(nodes))
    for n in nodes:
        if n.get("obj_type") != "docx" or not n.get("obj_token"):
            continue
        title = n.get("title") or ""
        try:
            sections = docs.docx_sections(n["obj_token"], doc_title=title,
                                          max_chars=MAX_CHARS)
        except LarkDocsError as exc:
            log.warning("đọc lỗi '%s': %s", title, exc)
            continue
        for s in sections:
            items.append({
                "item_id": f"kd_wk_{n['obj_token'][:12]}_{(s['block_id'] or 'x')[:12]}",
                "kind": "knowledge",
                "title": f"{title} › {s['title']}" if s["title"] != title else title,
                "content": s["content"],
                "domain": "business-context",
                "tags": ["lark-wiki", "TEAM KINH DOANH MATE MADE"],
                "scope": "shared",
                "agent_id": None,
                "source_agent": AGENT_ID,
                "source_team": "Kinh doanh Mate Made",
                "source_ref": f"{s['heading_path']} · sync {stamp}",
                "source_url": s["source_url"],
            })
    return items


def collect(docs: LarkDocs) -> list[dict]:
    items = collect_bases(docs) + collect_folders(docs)
    if SYNC_WIKI:
        items += collect_wiki(docs)
    else:
        log.info("KD_SYNC_WIKI=false — bỏ qua wiki space %s (tránh trùng với AG-LEGAL)",
                 KD_WIKI_SPACE)
    return items


# ----------------------------- nộp lên platform -----------------------------

def existing_content() -> dict[str, str]:
    """Nội dung tri thức đã có: ``{item_id: content}``.

    Dùng để bỏ qua mục không đổi — tránh upsert làm mất trạng thái 'approved'.
    """
    out: dict[str, str] = {}
    for params in ({"scope": "shared", "limit": 500},
                   {"scope": "agent", "agent_id": AGENT_ID, "limit": 500}):
        try:
            r = requests.get(PLATFORM + "/v1/brain/items", headers=_H, params=params,
                             timeout=60)
            rows = r.json() if r.ok else []
        except Exception as exc:
            log.warning("không đọc được tri thức hiện có (%s): %s", params["scope"], exc)
            continue
        if len(rows) >= 500:
            log.warning("chạm trần 500 khi đọc scope=%s — mục ngoài trần có thể bị nộp "
                        "lại và phải duyệt lại", params["scope"])
        for row in rows:
            if str(row.get("item_id", "")).startswith("kd_"):
                out[row["item_id"]] = row.get("content") or ""
    return out


def submit(items: list[dict]) -> dict:
    """Nộp từng mục (endpoint nhận 1 item/lần). Bỏ qua mục nội dung không đổi."""
    have = existing_content()
    stats = {"submitted": 0, "unchanged": 0, "failed": 0}
    for it in items:
        if have.get(it["item_id"]) == it["content"]:
            stats["unchanged"] += 1
            continue
        r = requests.post(PLATFORM + "/v1/brain/items", headers=_H, timeout=30, json=it)
        if r.ok:
            stats["submitted"] += 1
        else:
            stats["failed"] += 1
            log.warning("nộp lỗi %s (%s): %s", r.status_code, it["item_id"], r.text[:200])
    return stats


def run_once(dry_run: bool = False) -> dict:
    try:
        docs = LarkDocs()
    except LarkDocsError as exc:
        # Thiếu credential là lỗi cấu hình, không phải lỗi lập trình — báo cho người chạy
        # biết phải điền gì, đừng đổ traceback.
        log.error("%s — điền LARK_APP_ID/LARK_APP_SECRET trong .env "
                  "(xem .env.example)", exc)
        return {"candidates": 0, "submitted": 0, "failed": 0}
    items = collect(docs)
    stats = {
        "candidates": len(items),
        "confidential": sum(1 for i in items if i["scope"] == "agent"),
        "shared": sum(1 for i in items if i["scope"] == "shared"),
    }
    if dry_run:
        json.dump(items, sys.stdout, ensure_ascii=False, indent=2)
        print()
        stats["submitted"] = 0
    else:
        stats.update(submit(items))
    log.info("kd_sync xong: %s", stats)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Đồng bộ dữ liệu Kinh Doanh → hàng chờ tri thức AG-KD-MATE-MADE")
    ap.add_argument("--dry-run", action="store_true",
                    help="in ứng viên ra stdout, KHÔNG nộp lên platform")
    ap.add_argument("--once", action="store_true", help="chạy 1 lần rồi thoát")
    args = ap.parse_args()

    if not (bases() or folders() or SYNC_WIKI):
        log.warning("chưa khai nguồn nào (KD_BASES / KD_FOLDERS / KD_SYNC_WIKI) — "
                    "sẽ không có tri thức nào được nộp")

    if args.dry_run or args.once:
        run_once(dry_run=args.dry_run)
        return

    log.info("kd_sync: chạy hàng ngày lúc %sh giờ VN, platform=%s", RUN_HOUR, PLATFORM)
    if RUN_ON_START:
        try:
            run_once()
        except Exception as exc:
            log.exception("run_once lỗi: %s", exc)
    while True:
        wait = seconds_until_next_run()
        log.info("Lần chạy kế sau %.1f giờ", wait / 3600)
        time.sleep(wait)
        try:
            run_once()
        except Exception as exc:
            log.exception("run_once lỗi: %s", exc)
        time.sleep(60)  # tránh chạy lặp trong cùng giờ


if __name__ == "__main__":
    main()
