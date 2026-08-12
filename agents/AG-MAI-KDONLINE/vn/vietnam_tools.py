#!/usr/bin/env python3
"""MCP server "vn" — bộ công cụ của MAI (Khối KD Online VN).

Chỉ dùng thư viện chuẩn Python (không cài thêm gì) — nói chuyện MCP qua stdio
bằng JSON-RPC newline-delimited: `initialize` · `tools/list` · `tools/call`.

Trạng thái theo PLAN §6:
  - Phase 0 — CHẠY THẬT: nhóm Tri thức (`vn_kb_index`, `vn_kb_read`) + `vn_config_get`.
  - Phase 1→3 — STUB: 6 nhóm còn lại khai báo đủ tên + schema để agent nạp được tool
    list ngay hôm nay; gọi vào thì trả về trạng thái "chưa implement + thuộc phase nào",
    KHÔNG trả dữ liệu giả (nguyên tắc: thà nói chưa có còn hơn bịa).

Chạy thử không cần agent:
    python3 vietnam_tools.py --selftest
    python3 vietnam_tools.py --call vn_kb_index '{"query": "jtbd"}'

Khai báo trong lsr-agent.yaml:  skills: [{name: vn, type: mcp}]
"""

from __future__ import annotations

import json
import os
import sys

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB_DIR = os.path.join(AGENT_DIR, "kb")
CONFIG_DIR = os.path.join(AGENT_DIR, "configs")

PROTOCOL_VERSION = "2025-06-18"
MAX_READ_CHARS = 8000          # chặn 1 lần đọc nuốt hết context
MAX_INDEX_ITEMS = 200

# ---------------------------------------------------------------- tiện ích


def _md_files():
    """Mọi file .md trong kb/, trả về đường dẫn tương đối so với kb/."""
    out = []
    for root, _dirs, files in os.walk(KB_DIR):
        for fn in sorted(files):
            if fn.endswith(".md") and not fn.startswith("_"):
                out.append(os.path.relpath(os.path.join(root, fn), KB_DIR))
    return sorted(out)


def _read(rel):
    with open(os.path.join(KB_DIR, rel), encoding="utf-8") as fh:
        return fh.read()


def _title_and_sections(text):
    """Tiêu đề (# đầu tiên) + danh sách mục (## / ###) của một file .md."""
    title, sections = "", []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("# ") and not title:
            title = s[2:].strip()
        elif s.startswith("## ") or s.startswith("### "):
            sections.append(s.lstrip("#").strip())
    return title, sections


def _safe_rel(rel):
    """Chặn path traversal — chỉ cho đọc trong kb/."""
    rel = (rel or "").strip().lstrip("/")
    full = os.path.abspath(os.path.join(KB_DIR, rel))
    if not full.startswith(os.path.abspath(KB_DIR) + os.sep):
        raise ValueError("đường dẫn nằm ngoài kho tri thức kb/")
    return rel, full


def _extract_section(text, section):
    """Cắt đúng một mục (heading khớp không phân biệt hoa thường) tới heading cùng cấp kế tiếp."""
    lines = text.splitlines()
    want = section.strip().lower()
    start, level = None, 0
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("#") and s.lstrip("#").strip().lower() == want:
            start, level = i, len(s) - len(s.lstrip("#"))
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        s = lines[j].strip()
        if s.startswith("#") and (len(s) - len(s.lstrip("#"))) <= level:
            end = j
            break
    return "\n".join(lines[start:end]).strip()


# ---------------------------------------------------------------- tool THẬT (Phase 0)


def vn_kb_index(query=""):
    """Bước 1 của luật tra 2 bước: mục lục kho tri thức, KHÔNG trả nội dung."""
    if not os.path.isdir(KB_DIR):
        return {"status": "empty", "items": [],
                "note": "Chưa có thư mục kb/ — chưa nạp tri thức nào."}
    q = (query or "").strip().lower()
    items, hidden = [], 0
    for rel in _md_files():
        text = _read(rel)
        title, sections = _title_and_sections(text)
        if q and q not in rel.lower() and q not in title.lower() \
                and q not in " ".join(sections).lower() and q not in text.lower():
            continue
        if len(items) >= MAX_INDEX_ITEMS:
            hidden += 1
            continue
        items.append({"file": rel, "title": title or rel,
                      "sections": sections[:30], "chars": len(text)})
    if not items:
        return {"status": "empty", "items": [], "query": query,
                "note": "Không có mục nào khớp. Trả lời người dùng là 'chưa có trong kho' "
                        "— không được suy đoán."}
    return {"status": "ok", "count": len(items), "hidden": hidden, "items": items,
            "next": "Chọn 1 mục rồi gọi vn_kb_read(file=..., section=...). "
                    "Trả lời phải kèm tên file + mục."}


def vn_kb_read(file="", section=""):
    """Bước 2 của luật tra 2 bước: đọc đúng 1 file (hoặc 1 mục trong file)."""
    rel, full = _safe_rel(file)
    if not rel or not os.path.isfile(full):
        return {"status": "not_found", "file": file,
                "note": "Không có file này trong kb/. Gọi vn_kb_index trước để lấy đúng tên."}
    text = _read(rel)
    if section:
        part = _extract_section(text, section)
        if part is None:
            _t, secs = _title_and_sections(text)
            return {"status": "section_not_found", "file": rel, "section": section,
                    "available_sections": secs}
        text = part
    truncated = len(text) > MAX_READ_CHARS
    return {"status": "ok", "file": rel, "section": section or None,
            "content": text[:MAX_READ_CHARS], "truncated": truncated,
            "cite_as": "{}{}".format(rel, " § " + section if section else ""),
            "note": "Bắt buộc trích nguồn theo cite_as khi trả lời."}


def vn_config_get(key=""):
    """Đọc config (`configs/<key>.json`). Sửa config = đổi hành vi, KHÔNG cần deploy lại."""
    if not key:
        keys = sorted(fn[:-5] for fn in os.listdir(CONFIG_DIR)
                      if fn.endswith(".json")) if os.path.isdir(CONFIG_DIR) else []
        return {"status": "ok", "keys": keys}
    path = os.path.join(CONFIG_DIR, "{}.json".format(os.path.basename(key)))
    if not os.path.isfile(path):
        return {"status": "not_found", "key": key,
                "note": "Chưa có config này. Không được tự đặt giá trị mặc định."}
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    todo = data.get("_status") == "TODO"
    return {"status": "ok", "key": key, "value": data, "unfilled": todo,
            "note": ("Owner CHƯA điền config này — nói rõ 'chưa có' thay vì đoán số."
                     if todo else "Số/ngưỡng trong config là nguồn chuẩn, ưu tiên hơn trí nhớ.")}


# ---------------------------------------------------------------- tool STUB (Phase 1→3)


def _stub(name, phase, purpose, owner_gate=""):
    def handler(**kwargs):
        out = {"status": "not_implemented", "tool": name, "phase": phase,
               "purpose": purpose, "received_args": kwargs,
               "note": "Tool thuộc Phase {} — CHƯA chạy. Nói rõ với người dùng là tính năng "
                       "chưa có, KHÔNG được bịa kết quả.".format(phase)}
        if owner_gate:
            out["human_gate"] = owner_gate
        return out
    return handler


# Tên · schema · phase — bám PLAN §4 và FEATURES §4.
_SPEC = [
    # ---- Tri thức (Phase 0 — THẬT) ----
    ("vn_kb_index", "Mục lục kho tri thức nội bộ (bước 1 của luật tra 2 bước). "
                    "Trả về file + tiêu đề + danh sách mục, KHÔNG trả nội dung.",
     {"query": {"type": "string", "description": "từ khoá lọc (để trống = toàn bộ mục lục)"}},
     [], vn_kb_index),
    ("vn_kb_read", "Đọc đúng 1 file hoặc 1 mục trong kho tri thức (bước 2). "
                   "Trả về nội dung + cite_as để trích nguồn.",
     {"file": {"type": "string", "description": "đường dẫn tương đối trong kb/, lấy từ vn_kb_index"},
      "section": {"type": "string", "description": "tên mục (heading) cần đọc; để trống = cả file"}},
     ["file"], vn_kb_read),
    ("vn_config_get", "Đọc config của MAI (target, ngưỡng, lịch, danh sách người). "
                      "Để trống key = liệt kê mọi key hiện có.",
     {"key": {"type": "string", "description": "tên config, vd vn_context / vn_ads_rules"}},
     [], vn_config_get),
    ("vn_review_report", "Soi báo cáo tuần của manager theo 6 trục "
                         "(reach vs revenue · nhìn sau vs nhìn trước · quyết định lớn bị ghi như "
                         "ghi chú · 'Done' giả · ngày tháng lệch · mảng đang thắng viết ít nhất).",
     {"report_md": {"type": "string", "description": "nội dung báo cáo cần soi"}}, ["report_md"], None),

    # ---- Ads-ops (Phase 1→3) — trục chính, 10 bước ----
    ("vn_jtbd_bank", "B1 · Gom cụm JTBD từ review/comment/tin nhắn/khảo sát + xu hướng search & "
                     "social → xuất ≥5 JTBD chuẩn 'Khi… tôi muốn… để…' kèm quy mô cầu ước tính.",
     {"nganh": {"type": "string"}, "nguon": {"type": "string"}}, [], None),
    ("vn_product_match", "B2 · Đọc catalog (tính năng, giá, tồn, lịch sử bán) → xếp hạng SP theo "
                         "từng JTBD; cảnh báo hết hàng / biên thấp.",
     {"jtbd": {"type": "string"}, "nganh": {"type": "string"}}, ["jtbd"], None),
    ("vn_idea_scan", "B3 · Quét Ad Library / TikTok / nguồn TQ theo SP·JTBD → phân loại "
                     "angle/hook/format, tóm tắt vì sao hiệu quả, đề xuất bản địa hoá.",
     {"san_pham": {"type": "string"}, "jtbd": {"type": "string"}}, [], None),
    ("vn_creative_brief", "B4 · Sinh script + storyboard hoặc brief cho ekip quay.",
     {"idea": {"type": "string"}, "brand": {"type": "string", "description": "HAPAS | MATE MADE"}},
     ["idea"], None),
    ("vn_edit_variants", "B5 · Auto-cut theo script, phụ đề, lồng nhạc, xuất đa tỉ lệ "
                         "(9:16/1:1/4:5), nhiều biến thể hook 3s.",
     {"script": {"type": "string"}, "ty_le": {"type": "array", "items": {"type": "string"}}},
     ["script"], None),
    ("vn_camp_build", "B6 · Dựng camp/adset theo naming convention + ngân sách test chuẩn, "
                      "đề xuất targeting, nạp creative, gắn tracking, ghi giả thuyết + KPI.",
     {"creative_id": {"type": "string"}, "tep": {"type": "string"}, "ngan_sach": {"type": "number"}},
     ["creative_id"], None),
    ("vn_camp_ops", "B7 · Giám sát chỉ số theo ngưỡng; đề xuất (hoặc tự chạy TRONG hạn mức "
                    "vn_ads_rules) tắt/bật, tăng/giảm, nhân bản; cảnh báo bất thường.",
     {"camp_id": {"type": "string"}, "hanh_dong": {"type": "string"}}, ["camp_id"], None),
    ("vn_ads_report", "B8 · Kéo dữ liệu → báo cáo (spend, CPM, CTR, CPC, CPA, ROAS, CIR); "
                      "so target & kỳ trước; highlight top/bottom.",
     {"kenh": {"type": "string"}, "tu_ngay": {"type": "string"}, "den_ngay": {"type": "string"}},
     [], None),
    ("vn_ads_review", "B9 · Đối chiếu creative × tệp × chỉ số → pattern thắng/thua theo "
                      "FACT → WHY → SO WHAT → ACTION; tách dữ kiện vs giả thuyết.",
     {"camp_ids": {"type": "array", "items": {"type": "string"}}}, [], None),
    ("vn_scale_kill_reco", "B10 · Chấm điểm camp-creative theo hiệu quả & tiềm năng scale; "
                           "khuyến nghị nhân bản/giữ/bỏ + mức tự tin; mô phỏng tác động khi scale.",
     {"camp_ids": {"type": "array", "items": {"type": "string"}}}, [], None),

    # ---- Báo cáo (Phase 1) ----
    ("vn_numbers_read", "Đọc DT / LNĐG / %MTD từ nguồn số đã khai ở vn_report_sources.",
     {"ky": {"type": "string"}, "nganh": {"type": "string"}}, [], None),
    ("vn_report_draft", "Dựng .md theo template WBR, khung FACT → WHY → SO WHAT → ACTION, "
                        "ưu tiên theo tác động kinh doanh. Lãnh đạo: ≤1 trang, 3–5 điểm.",
     {"ky": {"type": "string"}, "pham_vi": {"type": "string"}}, [], None),
    ("vn_report_charts", "Chart chuẩn: DT luỹ kế vs target · chỉ số MKT kỳ này vs kỳ trước · "
                         "phễu DT theo kênh/ngành.",
     {"loai": {"type": "string"}, "ky": {"type": "string"}}, [], None),
    ("vn_report_publish", "Tạo Lark Doc + gửi chat — CHỈ sau khi được người duyệt.",
     {"draft_path": {"type": "string"}, "approved_by": {"type": "string"}},
     ["draft_path", "approved_by"], None),

    # ---- Mùa vụ & mốc (Phase 1) ----
    ("vn_season_calendar", "Dịp lễ & peak VN kèm KẾT LUẬN làm / không làm (không phải danh sách "
                           "ngày suông).",
     {"thang": {"type": "string"}}, [], None),
    ("vn_milestone_list", "Danh sách mốc BST đang theo dõi.",
     {"bst": {"type": "string"}}, [], None),
    ("vn_milestone_check", "Đếm ngược tới mốc tuyệt đối, cảnh báo khi trượt "
                           "(chốt mẫu · xuống PO · lên kệ · chốt KOC).",
     {"bst": {"type": "string"}}, [], None),
    ("vn_milestone_conflict", "Phát hiện 1 mốc BST có nhiều phiên bản ngày giữa các nguồn → "
                              "bảng đối chiếu, bắt chốt 1 nguồn chuẩn.",
     {"bst": {"type": "string"}}, [], None),

    # ---- Giao việc (Phase 2) ----
    ("vn_assignment_create", "Tạo assignment — BẮT BUỘC đủ 4 yếu tố: việc gì · bối cảnh · "
                             "đầu ra chấm được · PIC. Thiếu 1 yếu tố thì từ chối tạo.",
     {"viec": {"type": "string"}, "boi_canh": {"type": "string"},
      "dau_ra": {"type": "string"}, "pic": {"type": "string"},
      "han": {"type": "string"}}, ["viec", "boi_canh", "dau_ra", "pic"], None),
    ("vn_assignment_list", "Liệt kê assignment theo PIC / trạng thái / hạn.",
     {"pic": {"type": "string"}, "trang_thai": {"type": "string"}}, [], None),
    ("vn_assignment_update", "Cập nhật trạng thái/kết quả một assignment.",
     {"id": {"type": "string"}, "trang_thai": {"type": "string"}, "ghi_chu": {"type": "string"}},
     ["id"], None),
    ("vn_assignment_remind", "Nhắc PIC về assignment sắp/đã quá hạn.",
     {"id": {"type": "string"}}, [], None),
    ("vn_assignment_escalate", "Luật 24h: PIC im 24h → escalate theo cây RACI (CV → TN → TP/PM).",
     {"id": {"type": "string"}}, ["id"], None),

    # ---- Nghiên cứu (Phase 2) ----
    ("vn_research_index", "Mục lục các file nghiên cứu đã có. LUẬT: luôn tra trước khi làm bài "
                          "mới — để không làm lại việc đã làm.",
     {"query": {"type": "string"}}, [], None),
    ("vn_research_search", "Tìm trong kho nghiên cứu đã có.",
     {"query": {"type": "string"}}, ["query"], None),
    ("vn_research_sop", "SOP chuẩn theo nguồn: Kalodata · Ad Library · POP · Taobao/nguồn TQ · "
                        "TikTok Ads Audience Insights.",
     {"nguon": {"type": "string"}}, [], None),
    ("vn_research_report_build", "Dựng HTML báo cáo nghiên cứu: card ảnh thật → brand + năm → "
                                 "trường ngắn → lớp '→ HAPAS làm được gì' → nguồn + cấp A/B/C.",
     {"du_lieu": {"type": "string"}}, ["du_lieu"], None),

    # ---- Họp (Phase 3) ----
    ("vn_meeting_to_assignment", "Biến action item trong biên bản họp thành assignment 4 yếu tố "
                                 "theo đúng cây RACI.",
     {"meeting_id": {"type": "string"}}, ["meeting_id"], None),
]

# Phase của từng tool (dùng cho stub + tài liệu).
_PHASE = {
    "vn_jtbd_bank": 1, "vn_idea_scan": 1, "vn_ads_report": 1, "vn_ads_review": 1,
    "vn_numbers_read": 1, "vn_report_draft": 1, "vn_report_charts": 1, "vn_report_publish": 1,
    "vn_season_calendar": 1, "vn_milestone_list": 1, "vn_milestone_check": 1,
    "vn_milestone_conflict": 1, "vn_review_report": 1,
    "vn_creative_brief": 2, "vn_edit_variants": 2, "vn_camp_build": 2,
    "vn_assignment_create": 2, "vn_assignment_list": 2, "vn_assignment_update": 2,
    "vn_assignment_remind": 2, "vn_assignment_escalate": 2,
    "vn_research_index": 2, "vn_research_search": 2, "vn_research_sop": 2,
    "vn_research_report_build": 2,
    "vn_camp_ops": 3, "vn_product_match": 3, "vn_scale_kill_reco": 3,
    "vn_meeting_to_assignment": 3,
}

# Cổng WHY — tool nào chạm vào thì bắt buộc có người duyệt (FEATURES §3.1).
_HUMAN_GATE = {
    "vn_jtbd_bank": "B1 — con người chọn JTBD hợp chiến lược.",
    "vn_product_match": "B2 — con người quyết SP nào đẩy theo mục tiêu KD.",
    "vn_creative_brief": "B4 — con người chốt concept cuối.",
    "vn_camp_ops": "B7 — người duyệt ngân sách lớn; chỉ tự chạy trong hạn mức vn_ads_rules.",
    "vn_scale_kill_reco": "B10 — CON NGƯỜI RA QUYẾT ĐỊNH CUỐI, chịu trách nhiệm P&L.",
    "vn_report_publish": "Chỉ phát hành sau khi được duyệt.",
}

TOOLS = {}
for _name, _desc, _props, _req, _fn in _SPEC:
    TOOLS[_name] = {
        "name": _name,
        "description": _desc,
        "inputSchema": {"type": "object", "properties": _props, "required": _req},
        "handler": _fn or _stub(_name, _PHASE.get(_name, 1), _desc, _HUMAN_GATE.get(_name, "")),
    }


def call_tool(name, args):
    tool = TOOLS.get(name)
    if not tool:
        return {"status": "unknown_tool", "tool": name, "available": sorted(TOOLS)}
    try:
        return tool["handler"](**(args or {}))
    except TypeError as exc:
        return {"status": "bad_args", "tool": name, "error": str(exc),
                "schema": tool["inputSchema"]}
    except Exception as exc:                                   # noqa: BLE001
        return {"status": "error", "tool": name, "error": str(exc)}


# ---------------------------------------------------------------- MCP stdio


def _tool_list():
    return [{k: t[k] for k in ("name", "description", "inputSchema")} for t in TOOLS.values()]


def _handle(msg):
    """Trả về response dict, hoặc None nếu là notification (không cần trả lời)."""
    method, mid = msg.get("method"), msg.get("id")
    if method == "initialize":
        ver = (msg.get("params") or {}).get("protocolVersion") or PROTOCOL_VERSION
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": ver,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "vn", "version": "0.1.0"}}}
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": _tool_list()}}
    if method == "tools/call":
        p = msg.get("params") or {}
        result = call_tool(p.get("name", ""), p.get("arguments") or {})
        is_error = result.get("status") in ("error", "bad_args", "unknown_tool")
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "content": [{"type": "text",
                         "text": json.dumps(result, ensure_ascii=False, indent=2)}],
            "isError": is_error}}
    if mid is None:
        return None
    return {"jsonrpc": "2.0", "id": mid,
            "error": {"code": -32601, "message": "method không hỗ trợ: {}".format(method)}}


def serve():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = _handle(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


# ---------------------------------------------------------------- selftest / CLI


def selftest():
    ok = True

    def check(label, cond):
        nonlocal ok
        ok = ok and bool(cond)
        print("{} {}".format("✓" if cond else "✗", label))

    check("nạp đủ 7 nhóm tool (>= 30 tool)", len(TOOLS) >= 30)
    check("tools/list trả schema hợp lệ",
          all("inputSchema" in t for t in _tool_list()))

    idx = call_tool("vn_kb_index", {})
    check("vn_kb_index chạy (status={})".format(idx.get("status")),
          idx.get("status") in ("ok", "empty"))

    if idx.get("status") == "ok":
        first = idx["items"][0]
        rd = call_tool("vn_kb_read", {"file": first["file"]})
        check("vn_kb_read đọc được '{}'".format(first["file"]), rd.get("status") == "ok")
        check("vn_kb_read trả cite_as để trích nguồn", bool(rd.get("cite_as")))
    else:
        print("  … kb/ chưa có file .md — bỏ qua test đọc (chưa nạp tri thức)")

    check("chặn path traversal", call_tool(
        "vn_kb_read", {"file": "../../../etc/passwd"}).get("status") == "error")

    cfg = call_tool("vn_config_get", {})
    check("vn_config_get liệt kê {} config".format(len(cfg.get("keys", []))),
          cfg.get("status") == "ok")

    stub = call_tool("vn_camp_build", {"creative_id": "x"})
    check("stub trả not_implemented (không bịa dữ liệu)",
          stub.get("status") == "not_implemented")
    check("stub B10 kèm cổng WHY cho con người",
          call_tool("vn_scale_kill_reco", {}).get("human_gate"))

    init = _handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    check("bắt tay MCP initialize", init["result"]["serverInfo"]["name"] == "vn")

    print("\n{}  —  {} tool ({} thật, {} stub)".format(
        "TẤT CẢ PASS" if ok else "CÓ TEST FAIL", len(TOOLS),
        sum(1 for n, _d, _p, _r, fn in _SPEC if fn), sum(1 for n, _d, _p, _r, fn in _SPEC if not fn)))
    return 0 if ok else 1


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "--selftest":
        return selftest()
    if argv and argv[0] == "--list":
        for t in _tool_list():
            print("{:28s} phase {}  {}".format(
                t["name"], _PHASE.get(t["name"], 0), t["description"][:70]))
        return 0
    if argv and argv[0] == "--call":
        name = argv[1] if len(argv) > 1 else ""
        args = json.loads(argv[2]) if len(argv) > 2 else {}
        print(json.dumps(call_tool(name, args), ensure_ascii=False, indent=2))
        return 0
    serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
