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
import re
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
SHEET_ROWS = int(os.environ.get("KD_SHEET_ROWS", "200"))
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


def configured_docs() -> list[dict]:
    """Tài liệu cần đồng bộ. Khai bằng env ``KD_DOCS`` (JSON) — nguồn CHÍNH giai đoạn 1.

    Ví dụ::

        KD_DOCS='[
          {"token":"Hh7Fwh2VpiNUctkhnTylsoCygGf","label":"MATE MADE - BC DAILY","domain":"kd-ops"},
          {"token":"JKZUw0CK4iDXbCkhi5ilTNoXgnd","label":"01_SOP","domain":"kd-report"},
          {"token":"GNSHwzC3aiurVmkXHryli0acgth","label":"JBP DT/CP 2026","domain":"kd-ops",
           "scope":"agent"}
        ]'

    ``token`` lấy từ URL (đoạn sau ``/wiki/``, ``/docx/`` hoặc ``/sheets/``).
    ``scope: "agent"`` cho tài liệu nhạy cảm (P&L, giá vốn, chi phí booking) — mặc định
    là ``shared`` để cả team tra được.
    """
    raw = os.environ.get("KD_DOCS", "").strip()
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.warning("KD_DOCS không phải JSON hợp lệ — bỏ qua nguồn tài liệu")
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


def collect_docs(docs: LarkDocs) -> list[dict]:
    """Tài liệu chỉ đích danh (docx / sheet / bitable) → tri thức.

    **Đây là nguồn CHÍNH ở giai đoạn 1.** Số vận hành của team hiện nằm trong báo cáo
    docx và sheet viết tay (BC DAILY, B2S-SHOPEE, báo cáo AFF, SOP, JBP), không nằm
    trong Lark Base. Khai từng tài liệu bằng ``KD_DOCS`` thay vì quét cả folder: quét
    folder sẽ kéo về cả file nháp, file cũ, file của người khác — rác vào kho tri thức
    thì người duyệt phải lọc tay.

    ``token`` nhận cả **wiki node token** (đoạn sau ``/wiki/`` trên URL) lẫn token tài
    liệu; ``resolve()`` tự phân biệt.
    """
    items: list[dict] = []
    stamp = today()
    for d in configured_docs():
        token, label = d.get("token"), d.get("label") or d.get("token")
        if not token:
            continue
        domain = d.get("domain") or "kd-ops"
        confidential = d.get("scope") == "agent"
        try:
            node = docs.resolve(token)
        except LarkDocsError as exc:
            log.warning("bỏ qua '%s': %s", label, exc)
            continue
        obj, otype = node["obj_token"], (node["obj_type"] or d.get("type") or "").lower()
        title = node["title"] or label

        try:
            if otype in ("sheet", "sheets", "spreadsheet"):
                items += _sheet_items(docs, obj, title, label, domain, confidential, stamp)
            elif otype in ("bitable", "base"):
                items += _bitable_items(docs, obj, title, label, domain, confidential, stamp)
            else:  # docx là mặc định — đa số báo cáo của team ở dạng này
                items += _docx_items(docs, obj, title, label, domain, confidential, stamp)
        except LarkDocsError as exc:
            log.warning("đọc lỗi '%s' (%s): %s", label, otype or "docx", exc)
    return items


# Mật khẩu / khoá viết thẳng trong tài liệu nội bộ. Có thật: wiki công ty đang để tài
# khoản Brandcamp dùng chung kèm mật khẩu. Nếu để lọt vào kho tri thức thì agent sẽ đọc
# lại mật khẩu đó cho bất kỳ ai hỏi — che ở đây, trước khi nộp.
_SECRET_LINE = re.compile(
    r"^(.*(?:pass(?:word)?|pwd|mật\s*khẩu|mat\s*khau|secret|api[_\s-]?key|token|"
    r"app[_\s-]?secret)\s*[:=]\s*)(\S.*)$",
    re.IGNORECASE | re.MULTILINE)
_SECRET_INLINE = re.compile(r"\b(sk-ant-[\w-]+|lsr_tel_[\w-]+|cli_[a-f0-9]{16,})\b",
                            re.IGNORECASE)

_redacted = 0


def redact(text: str) -> str:
    """Che giá trị mật khẩu/khoá trước khi nộp lên kho tri thức.

    Che **giá trị**, giữ lại phần mô tả — để câu hướng dẫn ("mật khẩu do IT cấp") vẫn tra
    được, chỉ mất đúng chuỗi bí mật.
    """
    global _redacted
    out, n = _SECRET_LINE.subn(r"\1[ĐÃ CHE]", text or "")
    out, n2 = _SECRET_INLINE.subn("[ĐÃ CHE]", out)
    _redacted += n + n2
    return out


def _item(**kw) -> dict:
    """Khung một mục tri thức — gom vào đây để mọi nguồn dùng chung đúng schema.

    Mọi nguồn đều đi qua đây nên ``redact()`` đặt ở đây là chặn được toàn bộ, không phải
    nhớ gọi ở từng hàm collect.
    """
    conf = kw.pop("confidential", False)
    if "content" in kw:
        kw["content"] = redact(kw["content"])
    return {
        "kind": "knowledge",
        "scope": "agent" if conf else "shared",
        "agent_id": AGENT_ID if conf else None,
        "source_agent": AGENT_ID,
        "source_team": "MATE MADE",
        **kw,
    }


def _docx_items(docs, obj, title, label, domain, conf, stamp) -> list[dict]:
    out = []
    for s in docs.docx_sections(obj, doc_title=title, max_chars=MAX_CHARS):
        out.append(_item(
            item_id=f"kd_dx_{obj[:12]}_{(s['block_id'] or 'x')[:12]}",
            title=f"{title} › {s['title']}" if s["title"] != title else title,
            content=s["content"], domain=domain, tags=["lark-docx", label],
            confidential=conf,
            source_ref=f"{s['heading_path']} · sync {stamp}",
            source_url=s["source_url"]))
    return out


def _sheet_items(docs, obj, title, label, domain, conf, stamp) -> list[dict]:
    """Sheet → mỗi khối ROWS_PER_ITEM dòng là một mục, giữ dòng đầu làm tiêu đề cột.

    Không có dòng tiêu đề thì số trong mục mất nghĩa ("7.1" là ROAS hay là giá?), nên
    dòng đầu được lặp lại ở mọi khối.
    """
    out = []
    for sh in docs.sheet_list(obj):
        rows = docs.sheet_rows(obj, sh["sheet_id"], max_rows=SHEET_ROWS)
        if not rows:
            continue
        header = " | ".join(str(c) for c in rows[0] if c not in (None, ""))
        body = rows[1:]
        for idx in range(0, len(body), ROWS_PER_ITEM):
            chunk = body[idx:idx + ROWS_PER_ITEM]
            text = "\n".join(" | ".join(str(c) for c in r if c not in (None, ""))
                             for r in chunk)
            if not text.strip():
                continue
            part = idx // ROWS_PER_ITEM + 1
            out.append(_item(
                item_id=f"kd_sh_{obj[:10]}_{str(sh['sheet_id'])[:10]}_{part:04d}",
                title=f"{title} › {sh['title']} (phần {part})",
                content=(f"Cột: {header}\n{text}")[:MAX_CHARS],
                domain=domain, tags=["lark-sheet", label, sh["title"]],
                confidential=conf,
                source_ref=f"{sh['title']} · sync {stamp}",
                source_url=docs.sheet_url(obj, sh["sheet_id"])))
    return out


def _bitable_items(docs, obj, title, label, domain, conf, stamp) -> list[dict]:
    out = []
    for t in docs.bitable_tables(obj):
        tid, tname = t.get("table_id"), t.get("name") or t.get("table_id")
        if not tid:
            continue
        records = docs.bitable_records(obj, tid)
        records.sort(key=lambda r: str(r.get("record_id") or ""))
        for idx in range(0, len(records), ROWS_PER_ITEM):
            body = render_rows(records[idx:idx + ROWS_PER_ITEM])
            if not body:
                continue
            part = idx // ROWS_PER_ITEM + 1
            out.append(_item(
                item_id=f"kd_bt_{obj[:10]}_{tid[:10]}_{part:04d}",
                title=f"{title} › {tname} (phần {part})",
                content=body[:MAX_CHARS], domain=domain,
                tags=["lark-base", label, tname], confidential=conf,
                source_ref=f"{tname} · sync {stamp}",
                source_url=docs.bitable_url(obj, tid)))
    return out


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
    # Giai đoạn 1: KD_DOCS là nguồn chính (báo cáo docx/sheet team đang dùng hằng ngày).
    # Giai đoạn 2: khi team dựng được Base "số vận hành hằng ngày" thì khai thêm KD_BASES
    # và chuyển dần các mục số sang đó — Base có cột ngày nên chặn được lỗi kỳ dữ liệu.
    items = collect_docs(docs) + collect_bases(docs) + collect_folders(docs)
    if SYNC_WIKI:
        items += collect_wiki(docs)
    else:
        log.info("KD_SYNC_WIKI=false — bỏ qua quét cả wiki space %s (khai từng tài liệu "
                 "bằng KD_DOCS thay vì quét cả space)", KD_WIKI_SPACE)
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
    stats["redacted"] = _redacted
    if _redacted:
        log.warning("đã che %d chuỗi giống mật khẩu/khoá trong tài liệu nguồn — báo chủ "
                    "tài liệu chuyển secret ra khỏi wiki, đừng chỉ dựa vào lớp che này",
                    _redacted)
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

    if not (configured_docs() or bases() or folders() or SYNC_WIKI):
        log.warning("chưa khai nguồn nào (KD_DOCS / KD_BASES / KD_FOLDERS / KD_SYNC_WIKI) "
                    "— sẽ không có tri thức nào được nộp. Giai đoạn 1 dùng KD_DOCS.")

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
