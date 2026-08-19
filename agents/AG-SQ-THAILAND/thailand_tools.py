"""Ploy — bộ tool thị trường Thái Lan (6 nhóm) cho AG-SQ-THAILAND.

Nguyên tắc (PLAN Ploy mục 5): **skill = năng lực chung (.md), chi tiết hay thay đổi =
config** — mọi số liệu/lịch/danh sách nằm ở ``configs/*.json``, sửa file là đổi câu trả
lời, KHÔNG hard-code. Sau khi agent register, config chuyển vào schema riêng của agent
trên Supabase chung (``agent_ag_sq_thailand``) để sửa không cần commit.

Tình trạng tool:
  • ``ready`` — chạy ngay từ config, không cần mạng (mùa vụ, mốc BST, base target, kb index).
  • ``stub``  — khai đủ chữ ký để agent nạp được tool list; ruột chờ Phase 1–3
    (đọc Lark doc qua connector platform, assignments, research, họp).

Chủ file: **Data/Tech** (xem skills/README.md). Chỉ stdlib. Cách thêm tool mới:
viết hàm + gắn ``@tool(group, status)`` — tự vào registry, tự hiện ở ``--list``.

Chạy tay:  python3 thailand_tools.py --list
           python3 thailand_tools.py --call th_milestone_check
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sys
import time

CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "configs")

# ----------------------------- config: sửa là đổi hành vi -----------------------------


def load_config(key: str):
    """Đọc 1 config key từ configs/<key>.json. Không có file → None (tool tự nói rõ)."""
    path = os.path.join(CONFIG_DIR, f"{key}.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def show_source() -> bool:
    """Vinh 19/08: không cần in nguồn ra câu trả lời. Bật lại: reply_rules.show_source=true."""
    cfg = load_config("reply_rules") or {}
    return bool(cfg.get("show_source", False))


# consumer gắn hàm gọi platform vào đây lúc chạy: thailand_tools.API = consumer.api
API = None

NO_CONFIG = ("Chưa có config `{key}` (configs/{key}.json). Người phụ trách key này bổ sung "
             "là em trả lời được ngay — không cần deploy.")

# ----------------------------- registry 6 nhóm tool -----------------------------

TOOLS: dict[str, dict] = {}


def tool(group: str, status: str = "ready"):
    def deco(fn):
        TOOLS[fn.__name__] = {
            "fn": fn, "group": group, "status": status,
            "doc": (fn.__doc__ or "").strip().splitlines()[0],
        }
        return fn
    return deco


def _stub(name: str, phase: str, detail: str = "") -> str:
    msg = (f"Tool `{name}` chưa được nối — theo lộ trình **{phase}** (xem PLOY.md). "
           "Em chưa làm được việc này, không đoán kết quả thay.")
    return msg + (f"\n{detail}" if detail else "")


def _dmy(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{d}/{m}/{y}"


def _countdown(iso: str, today: datetime.date | None = None) -> str:
    today = today or datetime.date.today()
    delta = (datetime.date.fromisoformat(iso) - today).days
    if delta > 0:
        return f"còn {delta} ngày (D-{delta})"
    if delta == 0:
        return "HÔM NAY"
    return f"⚠️ QUÁ HẠN {-delta} ngày"


# ----------------------------- nhóm 1 · tri thức nội bộ -----------------------------


@tool("tri-thức")
def th_kb_index() -> str:
    """Mục lục kho tri thức TH: 3 master file + thư mục nghiên cứu (tra 2 bước: index → đọc)."""
    kb = load_config("th_kb_files")
    if not kb:
        return NO_CONFIG.format(key="th_kb_files")
    lines = ["**Kho tri thức thị trường Thái Lan** (tra 2 bước: chọn nguồn ở index này rồi mới đọc):"]
    lines.append("\n*Master file:*")
    for f in kb.get("master_files", []):
        lines.append(f"- `{f['path']}` ({f.get('size', '?')}) — {f.get('content', '')}")
    src = kb.get("lark_sources", [])
    if src:
        lines.append(f"\n*Nguồn Lark ({len(src)} link — wiki/docx/base/sheets):*")
        for s in src:
            lines.append(f"- [{s.get('kind', '?')}] {s.get('title', '?')}\n  {s.get('url', '')}")
    rf = kb.get("research_folder")
    if rf:
        lines.append(f"\n*Nghiên cứu:* `{rf['path']}` — {rf.get('count', '')}: {rf.get('content', '')}")
    lines.append(f"\nVị trí: {kb.get('location', 'Lark')}")
    if kb.get("corrections_priority"):
        lines.append(f"Lưu ý: {kb['corrections_priority']}")
    return "\n".join(lines)


@tool("tri-thức", status="stub")
def th_kb_read(file: str = "", section: str = "") -> str:
    """Đọc 1 mục trong master file theo anchor — cần connector Lark của platform."""
    return _stub("th_kb_read", "Phase 0 — chờ nối connector Lark (/v1/lark/*)",
                 "Tạm thời: tra mục lục bằng `th_kb_index`, mở file trực tiếp trên Lark Drive.")


@tool("tri-thức", status="stub")
def th_review_report(doc_token: str = "") -> str:
    """Soi báo cáo tuần của manager theo 6 trục (reach vs revenue, Done giả, ngày lệch…)."""
    return _stub("th_review_report", "Phase 1")


# ----------------------------- nhóm 2 · báo cáo tuần/tháng -----------------------------


def _vn(x) -> str:
    """Số kiểu Việt: 2.4 → '2,4'."""
    return str(x).replace(".", ",")


@tool("báo-cáo")
def th_base_targets() -> str:
    """Base target đang dùng + lịch sử rebase + các chỗ số liệu lệch giữa nguồn."""
    t = load_config("th_base_targets")
    if not t:
        return NO_CONFIG.format(key="th_base_targets")
    cur = t.get("current") or {}
    lines = [f"**Base target đang dùng — kỳ {cur.get('period', '?')}** "
             f"(áp từ {cur.get('applied_from', '?')}):",
             f"- DT **{_vn(cur.get('dt'))} {cur.get('unit', '')}** · "
             f"LNĐG **{_vn(cur.get('lndg'))} {cur.get('unit', '')}**",
             f"- Phạm vi: {cur.get('scope', '')}"]
    if cur.get("note"):
        lines.append(f"- {cur['note']}")

    hist = t.get("history") or []
    if hist:
        lines.append("\n**Lịch sử base (để không trích số cũ):**")
        for h in hist:
            lines.append(f"- {h.get('period')} · {h.get('label')}: DT {_vn(h.get('dt'))} · "
                         f"LNĐG {_vn(h.get('lndg'))} {h.get('unit', '')} — dùng bởi {h.get('used_by', '?')}")

    lines += ["\n**Luật khi trích số:**"] + [f"- {r}" for r in t.get("rules", [])]
    kc = t.get("known_conflicts") or []
    if kc:
        lines.append("\n⚠️ **Các chỗ số liệu đang lệch giữa nguồn** (em không tự chọn hộ):")
        lines += [f"- {c}" for c in kc]
    if show_source():
        lines.append(f"\n(nguồn: {t.get('source', '?')})")
    return "\n".join(lines)


@tool("báo-cáo")
def th_numbers_snapshot() -> str:
    """Số KQKD chốt tới 19/08: DT/LNĐG/%MTD + vấn đề đang thấy + tồn kho + dòng tiền."""
    s = load_config("th_numbers_snapshot")
    if not s:
        return NO_CONFIG.format(key="th_numbers_snapshot")
    m8 = s.get("thang_8_2026", {})
    tg, th = m8.get("target", {}), m8.get("thuc_hien_19_08", {})
    lines = [f"**Số tới {s.get('as_of')}** ({s.get('scope', '')}):",
             f"- DT **{th.get('dt')}** / target {tg.get('dt')} — MTD **{th.get('dt_mtd')}**",
             f"- LNĐG **{th.get('lndg')}** / target {tg.get('lndg')} — MTD **{th.get('lndg_mtd')}**",
             f"- Dự kiến cuối tháng: LNĐG {m8.get('du_kien_cuoi_thang', {}).get('lndg', '?')}"]
    probs = s.get("🔴_van_de_dang_thay") or []
    if probs:
        lines.append("\n🔴 **Đang lệch:**")
        lines += [f"- {p}" for p in probs[:3]]
    tk = s.get("ton_kho", {})
    if tk:
        lines.append(f"\n**Tồn kho:** TH {tk.get('thai_lan')} · tại NCC {tk.get('tai_ncc')} · "
                     f"{tk.get('ngay_ton')}")
    lines.append(f"\n_{s.get('canh_bao', '')}_")
    return "\n".join(lines)


def th_numbers(q_low: str = "") -> str:
    """Số KQKD: ưu tiên số sống BigQuery, ghép thêm LNĐG/target từ snapshot (DB không có)."""
    live = th_bq_sales(q_low)
    snap = th_numbers_snapshot()
    if not live:
        return snap
    if any(k in q_low for k in ("lnđg", "lndg", "lãi", "lai gop", "lợi nhuận", "loi nhuan",
                               "target", "kế hoạch", "ke hoach")):
        return live + "\n\n" + snap
    return live


# ----------------------------- số sống từ BigQuery -----------------------------

_BQ_CACHE_DIR = "/tmp"


def _bq_run(ten_truy_van: str):
    """Chạy một truy vấn ĐÃ RÀ SOÁT trong configs/th_bq.json, có cache theo phút.

    Ploy không bao giờ dựng SQL từ câu chat: chỉ chọn theo tên trong config. Lý do:
    câu chat có thể bị cài chỉ thị, và một câu SELECT sai có thể quét cả kho (tốn tiền).
    Trả None nếu tắt/lỗi/không mạng — nơi gọi phải tự lùi về số snapshot.
    """
    # PLOY_OFFLINE=1: bộ test offline không được gọi mạng (kết quả phải tất định)
    if os.environ.get("PLOY_OFFLINE") == "1":
        return None
    cfg = load_config("th_bq") or {}
    if not cfg.get("bat"):
        return None
    q = (cfg.get("cac_truy_van") or {}).get(ten_truy_van)
    if not q:
        return None
    ttl = int((cfg.get("gioi_han") or {}).get("cache_giay", 900))
    cache = os.path.join(_BQ_CACHE_DIR, f"ploy-bq-{ten_truy_van}.json")
    try:
        if os.path.exists(cache) and time.time() - os.path.getmtime(cache) < ttl:
            with open(cache, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    try:
        import bq
        res = bq.query(q["sql"], max_rows=(cfg.get("gioi_han") or {}).get("so_dong", 200))
    except Exception:
        return None
    try:
        with open(cache, "w", encoding="utf-8") as f:
            json.dump(res, f)
    except Exception:
        pass
    return res


def _bq_rows(res):
    """[[v,...]] + tên cột -> [{cot: v}] cho dễ đọc."""
    return [dict(zip(res["cot"], r)) for r in res["dong"]]


@tool("báo-cáo")
def th_bq_sales(q_low: str = "") -> str:
    """Doanh số Thái Lan LIVE từ BigQuery (01_hptl_report.hptl_pnl_dashboard, brand HPTH).

    DB quy hết về VND. Chưa khai tỷ giá THB thì KHÔNG quy đổi — nói rõ đơn vị.
    """
    ten = "mtd"
    if any(k in q_low for k in ("hôm qua", "hom qua")):
        ten = "hom_qua"
    elif any(k in q_low for k in ("hôm nay", "hom nay", "sáng nay", "sang nay")):
        ten = "hom_nay"
    elif any(k in q_low for k in ("kênh", "kenh", "tiktok", "shopee", "lazada", "sàn nào", "san nao")):
        ten = "theo_kenh"
    elif any(k in q_low for k in ("theo ngày", "theo ngay", "từng ngày", "tung ngay",
                                 "14 ngày", "mấy ngày qua", "may ngay qua")):
        ten = "theo_ngay"
    res = _bq_run(ten)
    if not res or not res["dong"]:
        return ""
    rows = _bq_rows(res)
    cfg = load_config("th_bq") or {}
    tg = cfg.get("ty_gia_thb_vnd")

    def ty(v):
        """triệu VND -> '7,29 tỷ VND' (+ THB nếu Vinh đã khai tỷ giá)."""
        if v in (None, ""):
            return "chưa có"
        x = float(v)
        out = f"{x / 1000:,.2f} tỷ VND".replace(",", " ") if x >= 1000 else f"{x:,.0f} tr VND".replace(",", " ")
        if tg:
            out += f" (~{x * 1e6 / float(tg) / 1e6:,.1f}M THB)".replace(",", " ")
        return out

    if ten == "mtd":
        nay = next((r for r in rows if r.get("ky") == "thang_nay"), None)
        truoc = next((r for r in rows if r.get("ky") == "thang_truoc_cung_ky"), None)
        if not nay:
            return ""
        out = [f"**Doanh số TH tới {nay.get('den_ngay')}** (số sống, BigQuery):",
               f"- GMV **{ty(nay.get('gmv_trieu_vnd'))}** · DT thuần {ty(nay.get('dt_thuan_trieu_vnd'))} "
               f"· {int(float(nay.get('don') or 0)):,} đơn".replace(",", " ")]
        if truoc and truoc.get("gmv_trieu_vnd"):
            d = (float(nay["gmv_trieu_vnd"]) / float(truoc["gmv_trieu_vnd"]) - 1) * 100
            out.append(f"- Cùng kỳ tháng trước: {ty(truoc.get('gmv_trieu_vnd'))} → **{d:+.0f}%**")
        if not tg:
            out.append("- _DB ghi theo VND; chưa khai tỷ giá THB nên em không quy đổi._")
        return "\n".join(out)

    if ten in ("hom_qua", "hom_nay"):
        r = rows[0]
        nhan = "Hôm nay" if ten == "hom_nay" else "Hôm qua"
        return (f"**{nhan} {r.get('ngay')}** (BigQuery): GMV {ty(r.get('gmv_trieu_vnd'))} · "
                f"DT thuần {ty(r.get('dt_thuan_trieu_vnd'))} · {int(float(r.get('don') or 0))} đơn "
                f"· {int(float(r.get('don_hoan') or 0))} đơn hoàn")

    if ten == "theo_kenh":
        có = [r for r in rows if r.get("gmv_trieu_vnd")]
        lines = [f"**Doanh số MTD theo kênh** (BigQuery, tới hôm nay):"]
        lines += [f"- {r['kenh']}: GMV {ty(r.get('gmv_trieu_vnd'))} · "
                  f"{int(float(r.get('don') or 0)):,} đơn".replace(",", " ") for r in có[:5]]
        trong = [r["kenh"] for r in rows if not r.get("gmv_trieu_vnd")]
        if trong:
            lines.append(f"- Chưa phát sinh: {', '.join(trong[:5])}")
        return "\n".join(lines)

    lines = ["**Doanh số theo ngày** (BigQuery, 7 ngày gần nhất):"]
    lines += [f"- {r['ngay']}: GMV {ty(r.get('gmv_trieu_vnd'))} · {int(float(r.get('don') or 0))} đơn"
              for r in rows[:7]]
    return "\n".join(lines)


def _with_agent_hint(text: str, q_low: str) -> str:
    h = agent_hint(q_low)
    return f"{text}\n\n{h}" if h else text


@tool("báo-cáo", status="stub")
def th_numbers_read(period: str = "", brand: str = "") -> str:
    """Đọc DT/LNĐG/%MTD LIVE từ 3 doc KQKD — cần connector Lark (bản chốt: th_numbers_snapshot)."""
    return _stub("th_numbers_read", "Phase 1",
                 "Số chốt tới 19/08 có sẵn: gọi `th_numbers_snapshot`.")


@tool("báo-cáo", status="stub")
def th_base_snapshot(view: str = "") -> str:
    """Screenshot Base Overview Dashboard (text extract vô dụng) — cần headless Chrome."""
    return _stub("th_base_snapshot", "Phase 1")


@tool("báo-cáo", status="stub")
def th_report_draft(type: str = "weekly", period: str = "") -> str:
    """Gom 8 nguồn → draft .md theo template 8 mục bọc khung 5 tầng BOD."""
    src = load_config("th_report_sources")
    n = len(src.get("sources", [])) if src else 0
    return _stub("th_report_draft", "Phase 1",
                 f"8 nguồn cố định đã khai đủ trong config `th_report_sources` ({n}/8).")


@tool("báo-cáo", status="stub")
def th_report_charts(spec: str = "") -> str:
    """4 chart chuẩn COO dạng whiteboard SVG (luỹ kế vs target · waterfall · MKT · phễu tuyển)."""
    return _stub("th_report_charts", "Phase 1")


@tool("báo-cáo", status="stub")
def th_report_publish(draft_id: str = "", target: str = "") -> str:
    """Tạo Lark Doc + gửi chat — CHỈ sau khi Vinh duyệt draft."""
    return _stub("th_report_publish", "Phase 1", "Luật: draft luôn chờ Vinh duyệt mới phát hành.")


# ----------------------------- nhóm 3 · mùa vụ & mốc BST -----------------------------


@tool("mùa-vụ-mốc")
def th_season_calendar(filter_q: str = "") -> str:
    """Lịch mùa vụ Thái — dịp lễ kèm KẾT LUẬN làm/không làm, không phải danh sách ngày suông."""
    cal = load_config("th_season_calendar")
    if not cal:
        return NO_CONFIG.format(key="th_season_calendar")
    occasions = cal.get("occasions", [])
    if filter_q:
        low = filter_q.lower()
        hit = [o for o in occasions if any(k in low for k in o.get("keywords", []))]
        occasions = hit or occasions
    blocks = []
    for o in occasions:
        b = [f"**{o['name']}** — {o['verdict']}"]
        b += [f"  • {n}" for n in o.get("notes", [])]
        blocks.append("\n".join(b))
    return "\n".join(blocks)


@tool("mùa-vụ-mốc")
def th_milestone_list() -> str:
    """Toàn bộ mốc BST đang theo dõi, kèm nguồn của từng mốc."""
    cfg = load_config("th_bst_milestones")
    if not cfg:
        return NO_CONFIG.format(key="th_bst_milestones")
    lines = ["**Mốc BST đang theo dõi** (ngày tuyệt đối · nguồn):"]
    for m in cfg.get("milestones", []):
        s = f"- {m['bst']} · {m['milestone']}: {_dmy(m['date'])} (nguồn: {m['source']})"
        if m.get("status"):
            s += f" — {m['status']}"
        lines.append(s)
    return "\n".join(lines)


# Nhận diện BST và loại mốc từ câu hỏi → trả lời TRỌNG TÂM (feedback Hương 19/08: đừng
# "học tủ" đọc cả bảng; hỏi BST nào thì chỉ nói BST đó, hỏi launching thì 1 dòng 1 mốc).
_BST_ALIAS = {
    "BST T10 (Color Trend)": ("t10", "tháng 10", "thang 10", "color trend", "aura", "ruby lock"),
    "BST T9 (Special Booming - Bloomly/Stella/Chloe)": ("t9", "tháng 9", "thang 9", "booming", "bloomly", "stella", "chloe"),
    "BST T11 (Thu Đông)": ("t11", "tháng 11", "thang 11", "thu đông", "thu dong"),
    "BST Tote bag - VN (Roam/Kerry/Sienna)": ("tote", "roam", "kerry", "sienna"),
    "BST Travel bag (Sora/Kaia/Lyra)": ("travel", "sora", "kaia", "lyra"),
    "BST Tổng hợp (SP win)": ("tổng hợp", "tong hop", "sp win"),
    "BST Giáng Sinh / Năm mới": ("giáng sinh", "giang sinh", "noel", "xmas", "christmas", "năm mới"),
    "BST Ví (mới)": ("bst ví", "bst vi", "ví nhỏ", "wallet"),
    "BST Tết VN (bán màu đỏ / cho Xmas)": ("tết vn", "tet vn"),
    "BST Balo": ("balo", "backpack"),
}
_MS_ALIAS = {
    "Launching Day": ("launching", "launch", "ra mắt", "ra mat", "lên sóng", "len song"),
    "Xuống đơn hàng PO": ("xuống đơn", "xuong don", " po", "đặt hàng", "dat hang", "xuống đh"),
    "Hàng về cho KOC": ("hàng về cho koc", "hang ve cho koc", "gửi hàng koc", "koc"),
    "Mở bán chính thức": ("mở bán", "mo ban"),
    "Chốt sản phẩm BST": ("chốt sản phẩm", "chot san pham", "chốt mẫu", "chot mau"),
    "Bán test": ("bán test", "ban test", "tỷ trọng", "ty trong"),
    "Hàng về số lượng lớn": ("số lượng lớn", "so luong lon", "sll", "hàng về kho"),
}


def _match_bst(q: str) -> str | None:
    for name, keys in _BST_ALIAS.items():
        if any(k in q for k in keys):
            return name
    return None


def _match_milestone(q: str) -> str | None:
    for name, keys in _MS_ALIAS.items():
        if any(k in q for k in keys):
            return name
    return None


def th_milestone_answer(q: str, today: str = "") -> str | None:
    """Trả lời NGẮN đúng thứ được hỏi. None nếu câu hỏi không chỉ rõ BST nào."""
    cfg = load_config("th_bst_milestones")
    if not cfg:
        return None
    bst = _match_bst(q)
    if not bst:
        return None
    ref = datetime.date.fromisoformat(today) if today else datetime.date.today()
    rows = [m for m in cfg.get("milestones", []) if m["bst"] == bst and m.get("date")]
    if not rows:
        return None

    want = _match_milestone(q)
    if want:
        hit = [m for m in rows if want in m["milestone"] and not m.get("superseded")]
        # Mốc đã được chốt chính thức (vd Vinh chốt trong nhóm) → chỉ nói mốc đó, hết.
        official = [m for m in hit if m.get("official")]
        if official:
            hit = official[:1]
        if hit:
            dates = sorted({m["date"] for m in hit})
            if len(dates) == 1:
                m = hit[0]
                out = (f"**{bst} · {m['milestone']}: {_dmy(m['date'])}** "
                       f"({_countdown(m['date'], ref)})")
                if m.get("status") and ("🔴" in m["status"] or "QUÁ HẠN" in m["status"].upper()):
                    out += f"\n{m['status']}"
                return out
            # nhiều nguồn ghi khác ngày → nói thẳng là đang lệch, không chọn hộ
            lines = [f"⚠️ **{bst} · {want}** đang có {len(dates)} ngày khác nhau, chưa ai chốt:"]
            lines += [f"- {_dmy(d)}" for d in dates]
            lines.append("→ Anh/chị chốt giúp em ngày nào là chuẩn.")
            return "\n".join(lines)

    # Có BST nhưng không rõ mốc nào → tóm tắt gọn đúng BST đó
    launch = next((m.get("launch") for m in rows if m.get("launch")), None)
    head = f"**{bst}**" + (f" — launching {_dmy(launch)} ({_countdown(launch, ref)})" if launch else "")
    late = sorted([m for m in rows
                   if datetime.date.fromisoformat(m["date"]) < ref and not m.get("done")],
                  key=lambda x: x["date"])
    nxt = sorted([m for m in rows
                  if datetime.date.fromisoformat(m["date"]) >= ref and not m.get("done")],
                 key=lambda x: x["date"])
    lines = [head]
    if late:
        lines.append("🔴 Quá hạn: " + " · ".join(
            f"{m['milestone']} {_dmy(m['date'])} ({-(datetime.date.fromisoformat(m['date']) - ref).days}n)"
            for m in late[:3]))
    if nxt:
        lines.append("⏰ Mốc tới: " + " · ".join(
            f"{m['milestone']} {_dmy(m['date'])}" for m in nxt[:3]))
    return "\n".join(lines)


@tool("mùa-vụ-mốc")
def th_milestone_check(today: str = "", horizon: int = 21) -> str:
    """Mốc QUÁ HẠN + mốc tới trong `horizon` ngày; mốc lệch nguồn đẩy sang phần conflict."""
    cfg = load_config("th_bst_milestones")
    if not cfg:
        return NO_CONFIG.format(key="th_bst_milestones")
    ref = datetime.date.fromisoformat(today) if today else datetime.date.today()

    groups: dict[tuple, list] = {}
    for m in cfg.get("milestones", []):
        if m.get("done") or not m.get("date"):
            continue                      # mốc đã xong thì không đếm ngược
        groups.setdefault((m["bst"], m["milestone"]), []).append(m)

    overdue, soon, later, conflicted = [], [], 0, False
    for (bst, ms), items in groups.items():
        if len({i["date"] for i in items}) > 1:
            conflicted = True             # lệch nguồn — xem phần conflict, không tự chọn
            continue
        m = items[0]
        delta = (datetime.date.fromisoformat(m["date"]) - ref).days
        row = f"- **{bst} · {ms}** — {_dmy(m['date'])} · {_countdown(m['date'], ref)}"
        if m.get("status"):
            row += f"\n    {m['status']}"
        if delta < 0:
            overdue.append((delta, row))
        elif delta <= horizon:
            soon.append((delta, row))
        else:
            later += 1

    lines = [f"**Mốc BST — tính tới {_dmy(ref.isoformat())}:**"]
    if overdue:
        lines.append(f"\n🔴 **QUÁ HẠN ({len(overdue)} mốc)** — cũ nhất trước:")
        lines += [r for _, r in sorted(overdue)]
    if soon:
        lines.append(f"\n⏰ **Tới trong {horizon} ngày ({len(soon)} mốc):**")
        lines += [r for _, r in sorted(soon)]
    if later:
        lines.append(f"\n📅 Còn {later} mốc xa hơn {horizon} ngày (hỏi 'toàn bộ mốc BST' để xem đủ).")
    if cfg.get("luat_uu_tien_nguon"):
        lines.append(f"\n_Lưu ý: {cfg['luat_uu_tien_nguon']}_")
    if conflicted:
        lines.append("")
        lines.append(th_milestone_conflict())
    return "\n".join(lines)


@tool("mùa-vụ-mốc")
def th_milestone_conflict() -> str:
    """⭐ Soi 1 mốc có nhiều phiên bản ngày giữa các nguồn → liệt kê, bắt chốt 1 nguồn chuẩn."""
    cfg = load_config("th_bst_milestones")
    if not cfg:
        return NO_CONFIG.format(key="th_bst_milestones")
    groups: dict[tuple, list] = {}
    for m in cfg.get("milestones", []):
        groups.setdefault((m["bst"], m["milestone"]), []).append(m)

    blocks = []
    for (bst, ms), items in groups.items():
        dates = sorted({i["date"] for i in items})
        if len(dates) <= 1:
            continue
        b = [f"⚠️ **{bst} · {ms}** đang có {len(dates)} phiên bản ngày giữa các nguồn:"]
        for i in sorted(items, key=lambda x: x["date"]):
            b.append(f"  - {_dmy(i['date'])} — nguồn: {i['source']}")
        extra = next((i.get("status") for i in items if i.get("status")), None)
        if extra:
            b.append(f"  Bối cảnh: {extra}")
        b.append("→ Cần chốt 1 **nguồn chuẩn** rồi cập nhật `configs/th_bst_milestones.json`; "
                 "em không tự chọn hộ.")
        blocks.append("\n".join(b))
    return "\n\n".join(blocks) if blocks else "Không phát hiện mốc nào lệch giữa các nguồn. ✅"


# ----------------------------- nhóm 4 · giao việc & đôn đốc -----------------------------


@tool("giao-việc", status="stub")
def th_assignment_create(what: str = "", context: str = "", output: str = "", pic: str = "") -> str:
    """Tạo assignment — bắt buộc đủ 4 yếu tố: việc gì · bối cảnh · đầu ra chấm được · PIC."""
    sq = load_config("th_squads") or {}
    who = " / ".join(sq.get("can_assign", [])) or "[CẦN XÁC NHẬN]"
    return _stub("th_assignment_create", "Phase 2 (20–31/08)",
                 f"Luật đã chốt sẵn: thiếu 1 trong 4 yếu tố thì từ chối tạo; chỉ {who} giao được việc; "
                 "tạo task đi qua đề xuất /v1/self/actions/propose + duyệt trên console (HITL).")


@tool("giao-việc", status="stub")
def th_assignment_list(filter_by: str = "") -> str:
    """Danh sách assignment theo squad / PIC / trạng thái."""
    return _stub("th_assignment_list", "Phase 2")


@tool("giao-việc", status="stub")
def th_assignment_update(assignment_id: str = "", status: str = "") -> str:
    """Cập nhật assignment — khi done bắt buộc kèm bản tổng hợp cho CM."""
    return _stub("th_assignment_update", "Phase 2")


@tool("giao-việc", status="stub")
def th_assignment_remind(assignment_id: str = "") -> str:
    """Nhắc PIC trước hạn."""
    return _stub("th_assignment_remind", "Phase 2")


@tool("giao-việc", status="stub")
def th_assignment_escalate(assignment_id: str = "") -> str:
    """Luật 24h: squad lead MM im 24h → escalate cho Trang + Vinh quyết theo khung."""
    return _stub("th_assignment_escalate", "Phase 2")


# ----------------------------- nhóm 5 · nghiên cứu thị trường -----------------------------


@tool("nghiên-cứu", status="stub")
def th_research_index() -> str:
    """Index ~27 file nghiên cứu cũ — luật: tra TRƯỚC khi làm bài mới."""
    kb = load_config("th_kb_files") or {}
    rf = kb.get("research_folder", {})
    return _stub("th_research_index", "Phase 2 (20–31/08)",
                 f"Nguồn: `{rf.get('path', '02-Nghien-cuu-TuiNu-TH/')}` — {rf.get('count', '~27 file')}.")


@tool("nghiên-cứu", status="stub")
def th_research_search(keyword: str = "") -> str:
    """Tìm trong nghiên cứu cũ theo từ khoá."""
    return _stub("th_research_search", "Phase 2")


@tool("nghiên-cứu", status="stub")
def th_research_sop(topic: str = "") -> str:
    """SOP nghiên cứu — tái dùng skill th-market-research đã đóng 05/08, KHÔNG viết bản mới."""
    return _stub("th_research_sop", "Phase 2",
                 "⚠️ 3 file .skill 05/08 (lsr-doc-style · lsr-report-formats · th-market-research) "
                 "chưa có trong repo — Vinh gửi lại để commit vào skills/, tránh 2 bản recipe lệch nhau.")


@tool("nghiên-cứu", status="stub")
def th_research_report_build(data: str = "", format: str = "") -> str:
    """Dựng HTML báo cáo theo format đã chốt (card ảnh thật → '→ HAPAS làm được gì' → nguồn A/B/C)."""
    return _stub("th_research_report_build", "Phase 2")


# ----------------------------- nhóm 6 · họp & bối cảnh -----------------------------


@tool("họp", status="stub")
def th_meeting_to_assignment(meeting_id: str = "") -> str:
    """Biến action item của biên bản đã chốt thành assignment 4 yếu tố theo squad."""
    return _stub("th_meeting_to_assignment", "Phase 3 (T9)",
                 "Luồng biên bản (recording → nháp → chủ trì chốt) đã chạy sẵn ở minutes.py.")


@tool("bối-cảnh")
def th_context(brand: str = "") -> str:
    """Bối cảnh thị trường Thái (2 brand, 2 squad, target) — riêng MATE MADE không gộp HAPAS."""
    ctx = load_config("th_context")
    if not ctx:
        return NO_CONFIG.format(key="th_context")
    t = ctx.get("targets_2026") or {}
    lines = ["**Thị trường Thái Lan** — CM: " + ctx.get("cm", "?"),
             "- Brand: " + " · ".join(ctx.get("brands", [])),
             "- Squad: " + " · ".join(ctx.get("squads", [])),
             "- Mục tiêu: " + ctx.get("market_goal", "")]
    if t:
        unit = t.get("unit", "")
        for brand_key, label in (("HAPAS", "HAPAS"), ("MATE_MADE", "MATE MADE")):
            b = t.get(brand_key) or {}
            months = " · ".join(f"{m[-2:]}/{m[:4]}: {_vn(v)}" for m, v in b.items() if m != "ca_nam")
            lines.append(f"- Target {label} ({unit}): {months} · cả năm {_vn(b.get('ca_nam'))}")
        if t.get("note"):
            lines.append(f"  ⚠️ {t['note']}")
    for w in ctx.get("canh_bao_du_lieu", []):
        lines.append(f"- ⚠️ {w}")
    if show_source():
        lines.append(f"(nguồn: {ctx.get('source', '?')})")
    return "\n".join(lines)


# ----------------------------- route: consumer gọi 1 hàm này -----------------------------

_CONFLICT_Q = ("travel bag", "packed_with_love", "packed with love", "mốc lệch", "moc lech",
               "lệch nguồn", "lech nguon", "nhiều phiên bản")
_MILESTONE_Q = ("mốc", "moc bst", "tote", "koc", "launching", "launch", "đếm ngược",
                "dem nguoc", "xuống đơn", "chốt mẫu", "bst")
_SEASON_Q = ("mùa vụ", "mua vu", "dịp lễ", "dip le", "noel", "năm mới", "nam moi",
             "songkran", "valentine", "tết", "nguyên đán", "ngày của mẹ", "ngay cua me",
             "tháng 12", "thang 12", "giáng sinh")
_TARGET_Q = ("base target", "base nào", "base nao", "target nào", "target nao",
             "target tháng", "target ngày", "rebase")
_NUMBERS_Q = ("doanh thu", "doanh so", "doanh số", "lợi nhuận", "loi nhuan", "lnđg", "lndg",
              "mtd", "tình hình", "tinh hinh", "kqkd", "dòng tiền",
              "dong tien", "bán được bao nhiêu", "số tháng 8", "thang 8 the nao", "kênh nào", "kenh nao", "sàn nào", "san nao", "bán tốt", "ban tot",
               "tiktok", "shopee", "lazada", "theo kênh", "theo kenh", "theo ngày")
_KB_Q = ("kho tri thức", "kho tri thuc", "master file", "mục lục", "muc luc",
         "file nào", "file nao", "có những file", "tài liệu nào", "tai lieu nao")
_MM_Q = ("mate made", "matemade", "mate-made", "mm th")


def mate_made_answer(q_low: str) -> str:
    """MATE MADE Thái Lan đã đóng 19/08. MM Việt Nam ngoài phạm vi Ploy."""
    cfg = load_config("th_agent_routing") or {}
    row = next((r for r in cfg.get("routing", []) if r["agent"] == "AG-JENNY-BOD"), {})
    vn = any(k in q_low for k in ("việt nam", "viet nam", " vn", "vn "))
    head = "**MATE MADE Thái Lan đã đóng** (19/08/2026) — em không còn giữ số mảng này."
    if not vn:
        return head + "\nNếu anh/chị hỏi MATE MADE **Việt Nam** thì nói rõ giúp em — đó là thị trường VN, ngoài phạm vi em."
    who = f"**{row.get('ten', 'Jenny')}** ({row.get('agent', 'AG-JENNY-BOD')})"
    can = row.get("can_call")
    tail = (f"Số MATE MADE **Việt Nam** do {who} giữ (BigQuery). "
            + ("Em hỏi được — nói em hỏi là em gọi." if can else
               "Em CHƯA được cấp quyền gọi; nhờ admin cấp A2A grant."))
    ds = cfg.get("🔴_data_support_khong_chay")
    if ds and not can:
        tail += "\n_AG-DATA-SUPPORT đã có quyền nhưng gọi 2 lần không phản hồi — agent đó chưa chạy._"
    return head + "\n" + tail
_CULTURE_Q = ("văn hoá", "van hoa", "văn hóa", "giá trị cốt lõi", "gia tri cot loi", "giá trị của lsr",
              "keeper test", "nguyên tắc làm việc", "check-in", "chuẩn mực", "tuyên ngôn")
_LOGISTICS_Q = ("logistic", "kho vận", "kho van", "vận chuyển", "van chuyen", "hàng về",
                "hang ve", "ffm", "flash", "cung ứng", "cung ung", "nhập hàng", "nhap hang",
                "hải quan", "hai quan", "3pl", "giao hàng", "giao hang", "lô hàng", "lo hang",
                "tồn kho", "ton kho", "giá vốn", "gia von", "nvl", "nguyên vật liệu", "hộp",
                "ruy băng", "packaging", "đóng gói", "dong goi", "scg", "anchanto", "ntk")
_PEOPLE_Q = ("nhân sự", "nhan su", "có những ai", "co nhung ai", "ai phụ trách", "team gồm",
             "danh sách người", "bao nhiêu người", "ai làm", "nhân viên", "có ai", "co ai", "gồm những ai", "gom nhung ai", "team nào",
              "danh sách nhân", "danh sach nhan", "đội ngũ", "doi ngu")
_AGENTS_Q = ("agent nào", "danh bạ agent", "bot nào", "agent khác", "gọi agent", "a2a")
_MEETING_Q = ("biên bản họp", "bien ban hop", "nội dung cuộc họp", "họp hôm", "mino", "gỡ băng",
              "meeting note", "biên bản cuộc họp")
_HOWWORK_Q = ("cơ chế", "co che", "kiến trúc", "kien truc", "em hoạt động", "hoạt động thế nào",
              "tự học", "tu hoc", "học thế nào", "hoc the nao", "system prompt", "cấu hình của em",
              "em được setup", "làm sao em biết", "sao em biết")
_DIGEST_Q = ("hôm nay có gì", "hom nay co gi", "bản tin", "ban tin", "digest", "tin mới",
             "tin moi", "cập nhật hôm nay", "có gì mới")
_COMPANY_Q = ("lịch sử", "lich su", "tầm nhìn", "tam nhin", "sứ mệnh", "su menh", "bod là ai",
              "lamson", "lam sơn", "hà túi", "ha tui", "văn phòng công ty", "trụ sở")


def route(q_low: str) -> str | None:
    """Định tuyến câu hỏi bối cảnh TH → tool. Câu chạm NHIỀU nhóm thì ghép đủ các phần
    (vd "ưu tiên gì theo mốc BST và lịch mùa vụ" → mốc + mùa vụ). Không khớp → None.

    Gọi SAU các gate của consumer (confirm biên bản, task, save, nhạy cảm) — thứ tự
    trong consumer.answer(). Lưu ý: câu chứa 'chốt'/'duyệt' bị gate confirm bắt trước.
    """
    parts = []
    # Hỏi đích danh một người → 1 dòng vị trí.
    who = person_lookup(q_low)
    if who:
        return who
    # Tin NÊU ngày/mốc (không phải câu hỏi) → đối chiếu với dữ liệu của em, góp ý nếu lệch.
    # Quyền Vinh cấp 19/08: được feedback về VIỆC và SỐ, không nhận xét con người.
    if len(q_low) < 220 and not any(k in q_low for k in ("?", "khi nào", "ngày nào", "bao giờ")):
        cc = th_crosscheck(q_low)
        if cc:
            return cc
    # Hỏi rõ BST nào → trả lời TRỌNG TÂM 1-3 dòng, không đọc cả bảng.
    focused = th_milestone_answer(q_low)
    if focused:
        return focused
    if any(k in q_low for k in _CONFLICT_Q):
        parts.append(th_milestone_conflict())
    elif any(k in q_low for k in _MILESTONE_Q):   # check đã kèm conflict ở cuối
        parts.append(th_milestone_check())
    if any(k in q_low for k in _SEASON_Q):
        parts.append(th_season_calendar(filter_q=q_low))
    if any(k in q_low for k in _PEOPLE_Q):
        return th_people(q_low)
    if any(k in q_low for k in _AGENTS_Q):
        return th_agents()
    if any(k in q_low for k in _MEETING_Q):
        return th_meeting_notes(q_low)
    if any(k in q_low for k in _HOWWORK_Q):
        return ploy_how_i_work()
    if any(k in q_low for k in _LOGISTICS_Q):
        parts.append(_with_agent_hint(th_logistics(q_low), q_low))
    if any(k in q_low for k in _DIGEST_Q):
        parts.append(th_daily_digest())
    if any(k in q_low for k in _NUMBERS_Q):
        n = th_numbers(q_low)
        # có số sống từ BigQuery thì không gợi ý đi hỏi agent khác nữa
        parts.append(n if "BigQuery" in n else _with_agent_hint(n, q_low))
    if any(k in q_low for k in _TARGET_Q):
        parts.append(th_base_targets())
    if any(k in q_low for k in _KB_Q):
        parts.append(th_kb_index())
    if any(k in q_low for k in _MM_Q):
        return mate_made_answer(q_low)
    if any(k in q_low for k in _CULTURE_Q):
        parts.append(lsr_culture())
    if any(k in q_low for k in _COMPANY_Q):
        parts.append(lsr_company())
    if not parts:
        h = agent_hint(q_low)
        if h:
            return ("Mảng này em không giữ số.\n" + h.strip("_"))
    # Ghép tối đa 2 mục — hỏi 1 câu không nên nhận về cả 4 bảng.
    return "\n\n".join(parts[:2]) if parts else None


# ----------------------------- nhóm 7 · LSR chung (văn hoá & công ty) -----------------------------


@tool("lsr-chung")
def lsr_culture() -> str:
    """Văn hoá LSR: 6 giá trị cốt lõi + 9 hành vi + 8 khía cạnh + Keeper Test + 5 thói quen."""
    c = load_config("lsr_culture")
    if not c:
        return NO_CONFIG.format(key="lsr_culture")
    lines = ["**Văn hoá LSR** — em nắm từ 2 tài liệu chính thức:"]
    for s in c.get("sources", []):
        lines.append(f"- {s.get('name')}" + (f" — {s.get('note')}" if s.get("note") else ""))
    if c.get("⚠️_hai_bo_gia_tri"):
        lines.append(f"\n⚠️ {c['⚠️_hai_bo_gia_tri']}")
    lines.append("\n**6 giá trị cốt lõi** (wiki LAMSON RETAIL INFORMATION_2026):")
    for g in c.get("6_gia_tri_cot_loi", []):
        lines.append(f"- **{g['ten']}** — {g['cot']}")
    lines.append("\n**9 hành vi & năng lực được trân trọng** (Tuyên ngôn văn hoá LSR):")
    lines.append("  " + " · ".join(h["ten"] for h in c.get("9_hanh_vi_nang_luc", [])))
    lines.append("\n**8 khía cạnh văn hoá:**")
    lines += [f"  {k}" for k in c.get("8_khia_canh_van_hoa", [])]
    lines.append("\n**5 thói quen vận hành mỗi ngày:**")
    lines += [f"- {t}" for t in c.get("5_thoi_quen_van_hanh", [])]
    if c.get("keeper_test"):
        lines.append(f"\n**Keeper Test:** {c['keeper_test']}")
    lines.append("\nHỏi sâu hơn được: '9 hành vi là gì', '5 cấp check-in', "
                 "'5 câu hỏi khi không chắc nên làm gì', 'nguyên tắc trao quyền'.")
    return "\n".join(lines)


@tool("lsr-chung")
def lsr_company() -> str:
    """Thông tin công ty LSR: lịch sử, tầm nhìn/sứ mệnh, brand, BOD, cơ sở, nội quy chung."""
    c = load_config("lsr_company")
    if not c:
        return NO_CONFIG.format(key="lsr_company")
    lines = [f"**Lamson Retail (LSR)** — {c.get('gioi_thieu', '')}",
             f"\n**Tầm nhìn 2030:** {c.get('tam_nhin_2030', '')}",
             f"**Sứ mệnh:** \"{c.get('su_menh', '')}\"",
             "\n**Lịch sử:**"]
    lines += [f"- {x}" for x in c.get("lich_su", [])]
    if c.get("⚠️_lech_moc_tai_dinh_vi"):
        lines.append(f"⚠️ {c['⚠️_lech_moc_tai_dinh_vi']}")
    lines.append(f"\n**Tăng trưởng:** {c.get('tang_truong', '')}")
    lines.append("\n**Thương hiệu:**")
    for b in c.get("brands", []):
        lines.append(f"- **{b['ten']}** — {b.get('dinh_vi', '')} ({b.get('vi_the', '')})")
    lines.append("\n**BOD:** " + " · ".join(c.get("bod", [])))
    cs = c.get("co_so", {})
    lines.append(f"\n**Cơ sở:** VP Hà Nội: {cs.get('van_phong_ha_noi', '')} · VP HCM: "
                 f"{cs.get('van_phong_hcm', '')} · VP Thái Lan: {cs.get('van_phong_thai_lan', '')}")
    lines.append(f"**Kho:** {cs.get('kho', '')}")
    g = c.get("gio_lam_viec", {})
    lines.append(f"\n**Giờ làm việc:** {g.get('khoi_van_phong', '')}. {g.get('hop_dinh_ky', '')}")
    if show_source():
        lines.append(f"\n(nguồn: {c.get('source', '?')})")
    return "\n".join(lines)


@tool("tri-thức")
def th_daily_digest() -> str:
    """Bản tin quét Lark hằng ngày: điểm chính, số mới, mốc bị đổi, rủi ro, việc chờ quyết."""
    d = load_config("th_daily_digest")
    if not d:
        return NO_CONFIG.format(key="th_daily_digest")
    if not d.get("as_of"):
        return ("Chưa có bản tin nào — job quét Lark hằng ngày (08:07) chưa chạy lần đầu ạ.")
    lines = [f"**Bản tin thị trường Thái Lan — {d['as_of']}**"]
    for k, title in (("diem_chinh", "Điểm chính"), ("cho_vinh_quyet", "Chờ anh/chị quyết")):
        if d.get(k):
            lines.append(f"\n**{title}:**")
            lines += [f"- {x}" for x in d[k][:5]]
    if d.get("so_moi"):
        lines.append("\n**Số mới:**")
        lines += [f"- {s.get('chi_so')}: {s.get('gia_tri')} ({s.get('ngay')})" for s in d["so_moi"][:5]]
    if d.get("moc_thay_doi"):
        lines.append("\n**Mốc bị đổi:**")
        lines += [f"- {m.get('bst')} · {m.get('milestone')} → {m.get('ngay_moi')}" for m in d["moc_thay_doi"][:5]]
    if d.get("rui_ro"):
        lines.append("\n🔴 **Rủi ro:**")
        lines += [f"- {r.get('noi_dung')}" for r in d["rui_ro"][:4]]
    return "\n".join(lines)


@tool("báo-cáo")
def th_logistics(topic: str = "") -> str:
    """Logistics/kho vận TH. Hỏi chung → rủi ro + tin mới nhất; hỏi cụ thể → chỉ mục đó."""
    d = load_config("th_logistics")
    if not d:
        return NO_CONFIG.format(key="th_logistics")
    if not d.get("as_of"):
        return ("Em chưa có dữ liệu logistics — job quét 6 nhóm kho vận (08:07 hằng ngày) "
                "chưa chạy lần đầu ạ.")

    def rows(key, n=3):
        out = []
        for r in (d.get(key) or [])[:n]:
            txt = r.get("noi_dung") or r.get("muc") or r.get("chi_so") or ""
            if r.get("gia_tri"):
                txt = f"{txt}: {r['gia_tri']}" if txt else r["gia_tri"]
            meta = " · ".join(x for x in (r.get("doi_tac"), r.get("ngay"), r.get("ai_xu_ly")) if x)
            out.append(f"- {txt}" + (f" _({meta})_" if meta else ""))
        return out

    t = topic.lower()
    # Hỏi cụ thể → chỉ trả đúng mục đó, gọn.
    for keys, key, title in (
        (("chi phí", "chi phi", "giá vốn", "gia von", "hoá đơn", "hoa don", "billing", "thuế", "cbm"),
         "chi_phi", "Chi phí logistics"),
        (("tồn kho", "ton kho", "tồn", "ntk"), "ton_kho", "Tồn kho"),
        (("rủi ro", "rui ro", "sự cố", "su co", "vấn đề", "van de"), "rui_ro_dang_mo", "🔴 Rủi ro đang mở"),
        (("lô hàng", "lo hang", "hàng về", "hang ve", "hàng trả"), "lo_hang", "Lô hàng"),
        (("flash", "ffm", "kho ", "vận chuyển", "van chuyen", "scg", "anchanto"),
         "doi_tac_ffm", "Đối tác FFM / kho"),
    ):
        if any(k in t for k in keys) and d.get(key):
            return f"**{title}** (tới {d['as_of']}):\n" + "\n".join(rows(key, 4))

    # Hỏi chung → rủi ro đang mở + tin mới nhất, không đọc cả bảng.
    lines = [f"**Logistics Thái Lan — tới {d['as_of']}**"]
    if d.get("rui_ro_dang_mo"):
        lines.append("\n🔴 **Đang mở:**")
        lines += rows("rui_ro_dang_mo", 3)
    moi = [r for k in ("doi_tac_ffm", "lo_hang") for r in (d.get(k) or [])
           if r.get("ngay") == d["as_of"]]
    if moi:
        lines.append(f"\n**Hôm nay:**")
        for r in moi[:3]:
            lines.append(f"- {r.get('noi_dung', '')}")
    lines.append("\nHỏi cụ thể hơn được: chi phí · tồn kho · Flash/kho · lô hàng.")
    return "\n".join(lines)


@tool("lsr-chung")
def ploy_how_i_work() -> str:
    """Em lấy số/thông tin từ đâu và chọn tool thế nào — nêu thẳng, kể cả chỗ chưa có."""
    return (
        "Em **không tự học lúc chạy**. Kiến thức = cấu hình do team setup.\n\n"
        "**Em lấy dữ liệu từ 6 chỗ:**\n"
        "1. Config của em — mốc BST · lịch mùa vụ · base target · số KQKD · logistics · tổ chức. "
        "Có sẵn, trả lời tức thì.\n"
        "2. Kho tri thức đã duyệt của squad (brain) — chỉ dùng mục đã có người duyệt.\n"
        "3. **Hỏi agent khác qua A2A** — biên bản họp thì hỏi agent gỡ băng (Mino/Minh Anh), "
        "tồn kho & PO thì hỏi Mira (KHHH). Cần admin cấp quyền gọi trước.\n"
        "4. Tài liệu Lark (wiki/doc/base) — ⛔ chưa nối connector, đang chờ admin.\n"
        "5. Dashboard/DB số liệu (BigQuery, Lark Base KQKD) — ⛔ chưa có quyền đọc; nên số của "
        "em là **snapshot theo ngày**, không phải số sống như Jenny đọc BigQuery.\n"
        "6. Job quét Lark 08:07 mỗi ngày — 14 nhóm Thái Lan, ghi lại mốc/số/rủi ro mới.\n\n"
        "**Cách em chọn việc:** đọc câu hỏi → khớp mảng nào thì gọi tool mảng đó (mốc BST, mùa "
        "vụ, số, logistics, tri thức, biên bản) → không mảng nào khớp mới suy luận bằng model, "
        "và vẫn không được bịa số.\n"
        "**Muốn em khác đi:** đổi số/mốc → sửa config · đổi cách làm → sửa skill · việc mới → "
        "thêm tool. Nói với Vinh (CM). Cấu hình chi tiết em không chia sẻ ra ngoài."
    )


# ---------------- nhóm 8 · lấy dữ liệu từ agent khác (A2A) & danh bạ ----------------


@tool("liên-agent")
def th_agents() -> str:
    """Danh bạ agent LSR: ai làm được gì, em được phép gọi ai (A2A)."""
    if API is None:
        return "Tool này cần chạy trong agent (có token platform) — em chưa gọi được ở đây."
    try:
        d = API("GET", "/v1/self/directory")
    except Exception as exc:
        return f"Chưa tra được danh bạ agent: {exc}"
    rows = d.get("agents") or []
    if not rows:
        return "Danh bạ agent đang trống."
    lines = ["**Agent đang sống trên platform:**"]
    for a in rows:
        skills = a.get("skills") or []
        sk = ", ".join(s if isinstance(s, str) else s.get("name", "?") for s in skills[:4])
        mark = "✅ gọi được" if a.get("can_call") else "⛔ chưa được cấp quyền gọi"
        lines.append(f"- **{a.get('name') or a.get('agent_id')}** ({a.get('agent_id')}) — "
                     f"{sk or 'chưa khai skill'} · {mark}")
    lines.append("\nMuốn em gọi agent nào mà đang ⛔ thì cần admin cấp quyền A2A.")
    return "\n".join(lines)


def th_ask_agent(who: str, question: str, wait: int = 40) -> str:
    """Hỏi agent khác qua A2A rồi chờ kết quả. `who` = agent_id hoặc tên gần đúng."""
    if API is None:
        return "Tool này cần chạy trong agent (có token platform)."
    target, cannot = who, None
    try:
        d = API("GET", "/v1/self/directory")
        low = who.lower()
        for a in d.get("agents") or []:
            if low in (a.get("agent_id", "").lower() + " " + (a.get("name") or "").lower()):
                target = a["agent_id"]
                cannot = not a.get("can_call")
                break
    except Exception:
        pass
    if cannot:
        return (f"Em chưa được cấp quyền gọi **{target}** (A2A grant). Nhờ admin cấp quyền là "
                "em hỏi trực tiếp agent đó được ngay.")
    try:
        r = API("POST", f"/v1/self/a2a/{target}", {"task": question})
    except Exception as exc:
        return f"Không gọi được **{target}**: {exc}"
    req_id = r.get("req_id")
    for _ in range(max(1, wait // 4)):
        time.sleep(4)
        try:
            res = API("GET", f"/v1/self/a2a/{req_id}")
        except Exception:
            continue
        if (res.get("status") or "").lower() in ("done", "completed", "succeeded"):
            out = res.get("result")
            if isinstance(out, dict):
                out = out.get("text") or json.dumps(out, ensure_ascii=False)
            return f"**{target} trả lời:**\n{out}" if out else f"{target} đã xử lý nhưng không trả nội dung."
        if (res.get("status") or "").lower() in ("failed", "error"):
            return f"**{target}** xử lý lỗi: {res.get('last_error') or 'không rõ'}"
    return (f"Đã gửi câu hỏi cho **{target}** (mã {req_id}) nhưng chưa có trả lời trong "
            f"{wait}s. Em sẽ không đoán thay — anh/chị hỏi lại sau ít phút ạ.")


_TOPIC_KEYS = {
    "AG-JENNY-BOD": ("doanh số", "doanh so", "doanh thu", "p&l", "pnl", "bigquery", "số sống",
                     "hôm nay bao nhiêu", "toàn tập đoàn", "cả tập đoàn", "việt nam", "vn "),
    "AG-KD-MATE-MADE": ("tồn kho mate", "roas", "tỷ lệ hoàn", "ty le hoan", "hoa hồng affiliate",
                        "affiliate mate"),
    "AG-SOURCING": ("nhà cung cấp", "nha cung cap", "ncc", "báo giá", "bao gia", "sourcing"),
    "AG-GIAAN": ("logistics tập đoàn", "logistics toàn"),
    "AG-HARRY": ("kế toán", "ke toan", "tài chính kế toán"),
    "AG-LEGAL": ("pháp lý", "phap ly", "hợp đồng", "hop dong"),
}


def agent_hint(q_low: str) -> str | None:
    """1 dòng chỉ rõ agent nào GIỮ dữ liệu này (kèm trạng thái quyền gọi). None nếu không khớp."""
    cfg = load_config("th_agent_routing")
    if not cfg:
        return None
    for agent_id, keys in _TOPIC_KEYS.items():
        if not any(k in q_low for k in keys):
            continue
        row = next((r for r in cfg.get("routing", []) if r["agent"] == agent_id), None)
        if not row:
            continue
        if row.get("can_call"):
            return (f"_Số sống của mảng này do **{row['ten']}** giữ — em hỏi trực tiếp được, "
                    f"anh/chị muốn em hỏi thì nói nhé._")
        return (f"_Số sống mảng này do **{row['ten']}** ({agent_id}) giữ — {row['nang_luc']}. "
                f"Em CHƯA được cấp quyền gọi; nhờ admin cấp A2A grant là em hỏi trực tiếp được._")
    return None


@tool("liên-agent")
def th_ask_best(topic: str, wait: int = 25) -> str:
    """Chọn agent giữ dữ liệu theo chủ đề rồi hỏi qua A2A (nếu đã có quyền)."""
    cfg = load_config("th_agent_routing") or {}
    low = topic.lower()
    for agent_id, keys in _TOPIC_KEYS.items():
        if any(k in low for k in keys):
            row = next((r for r in cfg.get("routing", []) if r["agent"] == agent_id), {})
            if not row.get("can_call"):
                return (f"Dữ liệu này do **{row.get('ten', agent_id)}** giữ. Em chưa được cấp "
                        f"quyền gọi ({agent_id}) — nhờ admin cấp A2A grant.")
            return th_ask_agent(agent_id, topic, wait)
    return "Chủ đề này em chưa map với agent nào — em tự tra trong dữ liệu của mình."


@tool("liên-agent")
def th_meeting_notes(topic: str = "") -> str:
    """Nội dung/biên bản cuộc họp — do agent gỡ băng giữ; em hỏi lại qua A2A."""
    if API is None:
        return ("Biên bản họp do agent gỡ băng giữ (Mino/Minh Anh). Em hỏi lại qua A2A khi "
                "chạy trong agent; ở đây em chưa gọi được.")
    return th_ask_agent("minh", f"Cho tôi nội dung/biên bản cuộc họp liên quan: {topic or 'thị trường Thái Lan'}. "
                                "Chỉ trả phần liên quan thị trường Thái Lan, kèm ngày họp.")


def _name_tokens(ten: str):
    """('Nguyễn Thị Thu Hương (Hom)') -> (['nguyễn','thị','thu','hương'], ['hom'])"""
    base, _, nick = ten.partition("(")
    toks = [w.lower() for w in base.split() if len(w) >= 2]
    nicks = [w.lower().strip(")") for w in nick.split() if len(w) >= 2]
    return toks, nicks


def person_lookup(q_low: str) -> str | None:
    """Câu hỏi nhắc ĐÍCH DANH một người trong danh bạ TH → 1 dòng vị trí.

    Tên người Việt trùng từ thường/địa danh rất nhiều ("Thái" trong "Thái Lan",
    "Trang", "Chi", "Ngân"...). Vì vậy 3 mức, chặt trước lỏng sau:
      1. cụm 2 từ liền nhau trong tên ("thu hương", "thành khôi") — luôn tính
      2. nickname Thái trong ngoặc ("hom", "prim") — luôn tính
      3. một từ trong tên, CHỈ khi câu đang hỏi về người VÀ từ đó không dễ nhầm
    """
    d = load_config("th_people") or {}
    if not d:
        return None
    AMBIG = {"thái", "lan", "trang", "chi", "anh", "linh", "thu", "ngân", "dương", "minh",
             "ngọc", "tùng", "huy", "đức", "hạnh", "nga", "hòa", "hoà", "thảo", "giang",
             "nguyễn", "trần", "lê", "phạm", "hoàng", "vũ", "đinh", "bùi", "thị", "văn"}
    ASK = ("là ai", "vị trí nào", "vi tri nao", "làm gì", "lam gi", "phụ trách gì",
           "chức danh", "chuc danh", "là nhân sự", "la nhan su", "thuộc team", "ở team",
           "trong team", "chức vụ", "chuc vu", "ai là", "làm ở", "phụ trách mảng")
    asking = any(k in q_low for k in ASK)
    pool = list(d.get("nguoi", [])) + [dict(x, nhom="MATE MADE TH (đã đóng)")
                                       for x in (d.get("mate_made_th_da_dong", {}).get("nguoi") or [])]

    def line(r):
        cd = r.get("chuc_danh") or r.get("chuc_danh_cu", "")
        extra = (" _(MATE MADE TH đã đóng 19/08 — vai trò mới chờ Vinh xác nhận)_"
                 if "chuc_danh_cu" in r else "")
        return f"**{r['ten']}** — {cd}{extra}"

    def has(word):
        return re.search(r"(?:^|\s)" + re.escape(word) + r"(?:\s|$|\?|,|\.|!|:)", q_low)

    for r in pool:                                  # 1) cụm 2 từ
        toks, _ = _name_tokens(r["ten"])
        if any(has(f"{toks[i]} {toks[i + 1]}") for i in range(len(toks) - 1)):
            return line(r)
    for r in pool:                                  # 2) nickname Thái
        _, nicks = _name_tokens(r["ten"])
        if any(len(n) >= 3 and has(n) for n in nicks):
            return line(r)
    if not asking:
        return None
    for r in pool:                                  # 3) một từ, chỉ khi hỏi về người
        toks, _ = _name_tokens(r["ten"])
        if any(len(t) >= 3 and t not in AMBIG and has(t) for t in toks):
            return line(r)
    return None


@tool("lsr-chung")
def th_people(nhom: str = "") -> str:
    """Nhân sự thị trường Thái Lan: tên + chức danh, nhóm theo chức năng."""
    d = load_config("th_people")
    if not d:
        return NO_CONFIG.format(key="th_people")
    rows = d.get("nguoi", [])
    q = nhom.lower()
    # 1) Hỏi ĐÍCH DANH một người → trả 1 dòng vị trí của người đó.
    hit = [r for r in rows if q and (r["nhom"] in q or any(
        w in q for w in ("booking", "marketing", "ads", "cskh", "kế toán", "thu mua",
                         "kho vận", "vận hành", "kinh doanh", "dữ liệu", "tuyển dụng",
                         "people", "tài chính", "sản phẩm")
        if w in r["nhom"] or w in r["chuc_danh"].lower()))]
    if hit:
        lines = [f"**Nhân sự TH — {hit[0]['nhom']}** ({len(hit)} người):"]
        lines += [f"- {r['ten']} — {r['chuc_danh']}" for r in hit]
        return "\n".join(lines)
    groups = {}
    for r in rows:
        groups.setdefault(r["nhom"], []).append(r["ten"])
    lines = [f"**Nhân sự thị trường Thái Lan — {len(rows)} người** (danh bạ Lark {d.get('as_of')}):"]
    for g, names in groups.items():
        lines.append(f"- **{g}** ({len(names)}): " + " · ".join(names))
    mm = d.get("mate_made_th_da_dong", {})
    if mm.get("nguoi"):
        lines.append(f"\n_{mm.get('ghi_chu','')}_ " + " · ".join(x["ten"] for x in mm["nguoi"]))
    lines.append("\nHỏi hẹp hơn được: kinh doanh · booking · marketing · vận hành · cskh · nhân sự · tài chính.")
    return "\n".join(lines)


_DATE_RE = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{2,4}))?\b")


@tool("liên-agent")
def th_crosscheck(text: str, today: str = "") -> str | None:
    """Soi ngày/mốc người khác nêu so với dữ liệu Ploy. None nếu không có gì để góp ý.

    Quyền Vinh cấp 19/08: được feedback với người và agent khác, CHỈ về việc và số —
    nêu cả hai bản, đề nghị chốt nguồn chuẩn, không nhận xét ai đúng/sai.
    """
    cfg = load_config("th_bst_milestones")
    if not cfg:
        return None
    bst = _match_bst(text)
    if not bst:
        return None
    said = {f"{int(m.group(2)):02d}-{int(m.group(1)):02d}" for m in _DATE_RE.finditer(text)}
    if not said:
        return None
    want = _match_milestone(text) or "Launching Day"
    rows = [m for m in cfg.get("milestones", [])
            if m["bst"] == bst and want in m["milestone"] and m.get("date")
            and not m.get("superseded")]
    if not rows:
        return None
    official = [m for m in rows if m.get("official")]
    ours = official or rows
    our_md = {m["date"][5:] for m in ours}
    if said & our_md:
        return None                      # khớp rồi, không cần góp ý
    ngay_ta = " hoặc ".join(_dmy(m["date"]) for m in ours[:3])
    ngay_ho = ", ".join(f"{d[3:]}/{d[:2]}" for d in sorted(said))
    if official:
        return (f"Em đối chiếu giúp: **{bst} · {want}** trong dữ liệu của em là **{ngay_ta}** "
                f"(đã chốt), còn tin này ghi {ngay_ho}. Nếu mốc đã đổi thì anh/chị nói để em "
                f"cập nhật; nếu chưa thì bản chốt vẫn là {ngay_ta} ạ.")
    return (f"Em thấy lệch: **{bst} · {want}** — dữ liệu của em ghi **{ngay_ta}**, tin này ghi "
            f"{ngay_ho}. Mốc này hiện chưa ai chốt nguồn chuẩn; anh/chị chốt giúp em một ngày.")


def suggest_menu() -> str:
    """Menu 'em trả lời ngay được mấy dạng này' — dạy người dùng cách hỏi khi em bí.

    Học từ bot Mira (KHHH) trong nhóm 'Sharing ai thích học cái mới': khi không hiểu
    câu hỏi thì liệt kê dạng câu trả lời tốt, thay vì chỉ nói 'không biết'.
    Chỉ liệt kê những gì đang chạy THẬT (tool ready), không hứa thứ chưa có.
    """
    return ("Em trả lời **ngay** mấy dạng này ạ:\n"
            "• \"còn mấy ngày tới hạn KOC Tote?\" — đếm ngược mốc BST, cảnh báo quá hạn\n"
            "• \"tháng 12 làm gì?\" — lịch mùa vụ Thái, kèm kết luận làm / không làm\n"
            "• \"ngày launching Travel bag?\" — soi mốc đang lệch giữa các nguồn\n"
            "• \"đang dùng base target nào?\" — base hiện hành + lịch sử rebase\n"
            "• \"kho tri thức có gì?\" — mục lục nguồn Lark của thị trường TH\n"
            "• dán nội dung họp → em dựng **biên bản**; chủ trì trả lời `chốt` là em lưu "
            "kho + đề xuất đầu việc\n\n"
            "_Giá trị **HỌC HỎI** của LSR: \"đừng xấu hổ khi không biết, hãy xấu hổ khi không "
            "học\" — nên em nói thẳng là chưa biết, chứ không đoán. Anh/chị chỉ nguồn thì em "
            "học ngay ạ._")


# ----------------------------- CLI: --list / --call -----------------------------


def _list() -> str:
    order = ["tri-thức", "báo-cáo", "mùa-vụ-mốc", "giao-việc", "nghiên-cứu", "họp", "bối-cảnh", "lsr-chung"]
    ready = sum(1 for t in TOOLS.values() if t["status"] == "ready")
    lines = [f"Ploy · thailand_tools — {len(TOOLS)} tool ({ready} ready, {len(TOOLS) - ready} stub)"]
    for g in order:
        lines.append(f"\n[{g}]")
        for name, t in TOOLS.items():
            if t["group"] == g:
                mark = "✅" if t["status"] == "ready" else "⬜"
                lines.append(f"  {mark} {name} — {t['doc']}")
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--call":
        name = sys.argv[2]
        if name not in TOOLS:
            sys.exit(f"không có tool `{name}` — xem --list")
        kwargs = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
        print(TOOLS[name]["fn"](**kwargs))
    else:
        print(_list())
