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
import sys

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
    lines = ["**Kho tri thức thị trường Thái Lan** (tra 2 bước: chọn file ở index này rồi mới đọc):"]
    for f in kb.get("master_files", []):
        lines.append(f"- `{f['path']}` ({f.get('size', '?')}) — {f.get('content', '')}")
    rf = kb.get("research_folder")
    if rf:
        lines.append(f"- `{rf['path']}` — {rf.get('count', '')}: {rf.get('content', '')}")
    lines.append(f"Vị trí: {kb.get('location', 'Lark Drive')}")
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


@tool("báo-cáo")
def th_base_targets() -> str:
    """Base target đang dùng — 2 base chạy song song, luôn nói rõ đang dùng base nào."""
    t = load_config("th_base_targets")
    if not t:
        return NO_CONFIG.format(key="th_base_targets")
    monthly = str(t["monthly"]).replace(".", ",")
    daily = str(t["daily"]).replace(".", ",")
    lines = [
        "**Hai base target đang chạy song song:**",
        f"- Báo cáo **tháng**: base {monthly}M THB (gốc)",
        f"- Báo cáo **ngày**: base {daily}M THB",
        f"Ghi chú: {t.get('note', '')}",
    ]
    lines += [f"- {r}" for r in t.get("rules", [])]
    return "\n".join(lines)


@tool("báo-cáo", status="stub")
def th_numbers_read(period: str = "", brand: str = "") -> str:
    """Đọc DT/LNĐG/%MTD từ 3 doc KQKD, chuẩn hoá JSON — cần connector Lark."""
    return _stub("th_numbers_read", "Phase 1")


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


@tool("mùa-vụ-mốc")
def th_milestone_check(today: str = "") -> str:
    """Đếm ngược tới mốc tuyệt đối, cảnh báo trượt; mốc lệch nguồn thì chỉ sang conflict."""
    cfg = load_config("th_bst_milestones")
    if not cfg:
        return NO_CONFIG.format(key="th_bst_milestones")
    ref = datetime.date.fromisoformat(today) if today else None
    groups: dict[tuple, list] = {}
    for m in cfg.get("milestones", []):
        groups.setdefault((m["bst"], m["milestone"]), []).append(m)

    lines = ["**Đếm ngược mốc BST:**"]
    conflicted = False
    for (bst, ms), items in groups.items():
        dates = sorted({i["date"] for i in items})
        if len(dates) > 1:
            conflicted = True
            continue  # mốc lệch nguồn — không đếm ngược hộ, xem phần conflict bên dưới
        m = items[0]
        s = f"- **{bst} · {ms}** — {_dmy(m['date'])} · {_countdown(m['date'], ref)}"
        if m.get("status"):
            s += f"\n    trạng thái: {m['status']}"
        if m.get("note"):
            s += f"\n    lưu ý: {m['note']}"
        lines.append(s)
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
    if brand.lower() in ("mm", "mate made", "matemade"):
        mm = load_config("th_context_mm")
        if not mm:
            return NO_CONFIG.format(key="th_context_mm")
        lo, hi = mm.get("price_band_thb", [0, 0])
        return ("**MATE MADE Thailand** — giai đoạn: " + mm.get("stage", "?") +
                f"\n- Vùng giá: {lo:,}–{hi:,}฿".replace(",", ".") +
                f"\n- {mm.get('ebitda_rule', '')}\n- {mm.get('reporting_rule', '')}")
    tgt = ctx.get("monthly_target", {})
    return ("**Thị trường Thái Lan** — CM: " + ctx.get("cm", "?") +
            "\n- Brand: " + " · ".join(ctx.get("brands", [])) +
            "\n- Squad: " + " · ".join(ctx.get("squads", [])) +
            f"\n- Target tháng: {tgt.get('value') or tgt.get('note', '[CẦN BỔ SUNG SỐ LIỆU]')}" +
            f"\n- Mục tiêu: {ctx.get('market_goal', '')}")


# ----------------------------- route: consumer gọi 1 hàm này -----------------------------

_CONFLICT_Q = ("travel bag", "packed_with_love", "packed with love", "mốc lệch", "moc lech",
               "lệch nguồn", "lech nguon", "nhiều phiên bản")
_MILESTONE_Q = ("mốc", "moc bst", "tote", "koc", "launching", "launch", "đếm ngược",
                "dem nguoc", "xuống đơn", "chốt mẫu", "bst")
_SEASON_Q = ("mùa vụ", "mua vu", "dịp lễ", "dip le", "noel", "năm mới", "nam moi",
             "songkran", "valentine", "tết", "nguyên đán", "ngày của mẹ", "ngay cua me",
             "tháng 12", "thang 12", "giáng sinh")
_TARGET_Q = ("base target", "base nào", "base nao", "target nào", "target nao",
             "target tháng", "target ngày", "rebase", "%mtd", "mtd")
_KB_Q = ("kho tri thức", "kho tri thuc", "master file", "mục lục", "muc luc",
         "file nào", "file nao", "có những file", "tài liệu nào", "tai lieu nao")
_MM_Q = ("mate made", "matemade")


def route(q_low: str) -> str | None:
    """Định tuyến câu hỏi bối cảnh TH → tool tương ứng. Không khớp → None (consumer đi tiếp).

    Gọi SAU các gate của consumer (confirm biên bản, task, save, nhạy cảm) — thứ tự
    trong consumer.answer(). Lưu ý: câu chứa 'chốt'/'duyệt' bị gate confirm bắt trước.
    """
    if any(k in q_low for k in _CONFLICT_Q):
        return th_milestone_conflict()
    if any(k in q_low for k in _MILESTONE_Q):
        return th_milestone_check()
    if any(k in q_low for k in _SEASON_Q):
        return th_season_calendar(filter_q=q_low)
    if any(k in q_low for k in _TARGET_Q):
        return th_base_targets()
    if any(k in q_low for k in _KB_Q):
        return th_kb_index()
    if any(k in q_low for k in _MM_Q):
        return th_context(brand="mm")
    return None


# ----------------------------- CLI: --list / --call -----------------------------


def _list() -> str:
    order = ["tri-thức", "báo-cáo", "mùa-vụ-mốc", "giao-việc", "nghiên-cứu", "họp", "bối-cảnh"]
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
