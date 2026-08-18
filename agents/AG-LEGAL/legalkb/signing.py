"""S5 — hỗ trợ quy trình trình ký (PLAN Phase 6).

Quy trình công ty 6 bước:
  1 Nhân sự khởi tạo → 2 Quản lý duyệt → **3 Agent rà soát sơ bộ** →
  4 Pháp chế rồi Tài chính/Nhân sự rà soát → **5 Agent cross-check** → 6 Admin trình ký.

Hai nguyên tắc không được phá:
  - **Agent không phải node duyệt.** Nó sinh báo cáo đính kèm hồ sơ; người vẫn quyết.
  - **Agent không bao giờ chặn hồ sơ.** Quá SLA hoặc engine lỗi → `auto_passed` kèm ghi
    chú "chưa rà soát kịp". Máy không được làm nghẽn quy trình người.

⚠️ TRẠNG THÁI: chạy **shadow**. Đúng chuẩn thì hồ sơ phải đến từ **Lark Approval**
(`channel=lark_approval`) và báo cáo phải ghi comment vào instance — nhưng broker
platform chưa có nhóm Approval (yêu cầu core **C5**), và agent KHÔNG được tự gọi Approval
API. Vì vậy hiện nhận hồ sơ qua chat/nhóm trình ký và trả báo cáo bằng tin nhắn.
Khi C5 xong: chỉ cần đổi phần vào/ra, phần logic Bước 3/Bước 5 dưới đây dùng lại nguyên.
"""
import json
import re
import time

SLA_MINUTES = 30

STEP3_LABEL = "Bước 3 — rà soát sơ bộ"
STEP5_LABEL = "Bước 5 — cross-check sau rà soát của người"
MAX_BOUNCE = 2          # tối đa 2 lần quay lại Bước 4 do phát hiện của Agent

_STEP3_PROMPT = """Bạn hỗ trợ rà soát sơ bộ một hồ sơ trình ký của công ty bán lẻ LSR.

Việc 1 — ĐỦ ĐẦU MỤC: đối chiếu hồ sơ với danh mục bắt buộc, chỉ ra mục nào thiếu.
Việc 2 — NỘI DUNG: nêu điểm cần lưu ý trong hợp đồng, dựa trên checklist/chính sách.

Trả về DUY NHẤT một JSON:
{"missing_docs": ["..."], "findings": [{"severity":"high|medium|low","issue":"...",
 "suggestion":"..."}], "note":"1-2 câu"}

=== DANH MỤC ĐẦU MỤC BẮT BUỘC ({contract_type}) ===
{checklist_docs}

=== CHECKLIST / CHÍNH SÁCH ===
{policy}

=== HỒ SƠ ===
{dossier}
"""

_STEP5_PROMPT = """Bạn là lớp kiểm tra chéo CUỐI (Bước 5) của hồ sơ trình ký, sau khi Pháp
chế và Tài chính/Nhân sự đã rà soát. Nhiệm vụ: tìm thứ mà người rà soát có thể đã bỏ sót.

Phân loại nghiêm ngặt — chỉ đặt severity=high khi thật sự chặn được việc trình ký:
thiếu/đối lập điều khoản bắt buộc, giá trị vượt hạn mức, sai chủ thể/pháp nhân.
Còn lại là medium/low (cảnh báo tham khảo, KHÔNG chặn hồ sơ).

Trả về DUY NHẤT một JSON:
{"findings": [{"severity":"high|medium|low","issue":"...","suggestion":"..."}],
 "note":"1-2 câu"}

=== CHECKLIST / CHÍNH SÁCH ===
{policy}

=== GÓP Ý CỦA NGƯỜI Ở BƯỚC 4 (đã xử lý) ===
{step4_notes}

=== BẢN CUỐI CỦA HỒ SƠ ===
{dossier}
"""


def checklist_docs(store, contract_type):
    r = store.one("SELECT * FROM dossier_checklists WHERE contract_type=?",
                  (contract_type or "",))
    if not r:
        r = store.one("SELECT * FROM dossier_checklists WHERE contract_type='*'")
    if not r:
        return []
    try:
        return json.loads(r["items"])
    except json.JSONDecodeError:
        return []


def set_checklist(store, contract_type, items):
    store.write(
        "INSERT INTO dossier_checklists (contract_type, items, updated_at) VALUES (?,?,?) "
        "ON CONFLICT(contract_type) DO UPDATE SET items=excluded.items, "
        "updated_at=excluded.updated_at",
        (contract_type, json.dumps(items, ensure_ascii=False), time.time()))


def _json_of(raw):
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


class Dossiers:
    def __init__(self, store):
        self.store = store

    def open(self, instance_code, contract_type=None, requester=None, chat_id=None):
        self.store.write(
            "INSERT INTO signing_dossiers (instance_code, contract_type, requester, "
            "chat_id, step, status, created_at, updated_at) "
            "VALUES (?,?,?,?,'step3','open',?,?) ON CONFLICT(instance_code) DO NOTHING",
            (instance_code, contract_type, requester, chat_id, time.time(), time.time()))
        return self.get(instance_code)

    def get(self, instance_code):
        return self.store.one("SELECT * FROM signing_dossiers WHERE instance_code=?",
                              (instance_code,))

    def save(self, instance_code, **f):
        f["updated_at"] = time.time()
        sets = ", ".join(f"{k}=?" for k in f)
        self.store.write(f"UPDATE signing_dossiers SET {sets} WHERE instance_code=?",
                         (*f.values(), instance_code))
        return self.get(instance_code)


def step3(brain, store, dossier_text, contract_type, policy="", model=None):
    """Rà soát sơ bộ. Lỗi model → báo 'chưa rà soát kịp', KHÔNG chặn hồ sơ."""
    docs = checklist_docs(store, contract_type)
    raw = brain.call_claude(
        _STEP3_PROMPT
        .replace("{contract_type}", contract_type or "(chưa rõ loại)")
        .replace("{checklist_docs}", "\n".join(f"- {d}" for d in docs)
                 or "(chưa cấu hình danh mục đầu mục cho loại hợp đồng này)")
        .replace("{policy}", policy or "(chưa có checklist trong KB)")
        .replace("{dossier}", (dossier_text or "")[:60_000]),
        model=model, timeout=240)
    out = _json_of(raw)
    if out is None:
        return {"ok": False, "missing_docs": [], "findings": [],
                "note": "Agent chưa rà soát kịp — hồ sơ vẫn đi tiếp, người rà soát "
                        "vui lòng kiểm tay.", "has_checklist": bool(docs)}
    return {"ok": True,
            "missing_docs": out.get("missing_docs") or [],
            "findings": out.get("findings") or [],
            "note": out.get("note") or "", "has_checklist": bool(docs)}


def step5(brain, dossier_text, policy="", step4_notes="", model=None):
    """Cross-check cuối. Trả thêm `blocking` = có mục high hay không."""
    raw = brain.call_claude(
        _STEP5_PROMPT
        .replace("{policy}", policy or "(chưa có checklist trong KB)")
        .replace("{step4_notes}", step4_notes or "(không có ghi chú)")
        .replace("{dossier}", (dossier_text or "")[:60_000]),
        model=model, timeout=240)
    out = _json_of(raw)
    if out is None:
        return {"ok": False, "findings": [], "blocking": False,
                "note": "Agent chưa cross-check kịp — hồ sơ vẫn đi tiếp."}
    findings = out.get("findings") or []
    return {"ok": True, "findings": findings,
            "blocking": any(f.get("severity") == "high" for f in findings),
            "note": out.get("note") or ""}


def render_step3(res, contract_type=None):
    lines = [f"**{STEP3_LABEL}**" + (f" — {contract_type}" if contract_type else "")]
    if not res["ok"]:
        return "\n".join(lines + ["", "⚠️ " + res["note"]])
    if not res["has_checklist"]:
        lines.append("_⚠️ Chưa cấu hình danh mục đầu mục cho loại hợp đồng này — "
                     "phần kiểm đủ hồ sơ chỉ mang tính tham khảo._")
    lines.append("")
    if res["missing_docs"]:
        lines.append("**Thiếu đầu mục:**")
        lines += [f"- ❌ {d}" for d in res["missing_docs"]]
    else:
        lines.append("**Đầu mục hồ sơ:** ✅ đủ theo danh mục.")
    if res["findings"]:
        lines.append("\n**Điểm cần lưu ý về nội dung:**")
        for f in res["findings"]:
            mark = {"high": "🔴", "medium": "🟠", "low": "🟢"}.get(f.get("severity"), "")
            lines.append(f"- {mark} {f.get('issue')}"
                         + (f" ↳ {f['suggestion']}" if f.get("suggestion") else ""))
    if res["note"]:
        lines.append(f"\n{res['note']}")
    lines.append("\n_Đây là rà soát sơ bộ để hỗ trợ, không thay thế rà soát của "
                 "Pháp chế / Tài chính / Nhân sự._")
    return "\n".join(lines)


def render_step5(res, bounce_count=0):
    lines = [f"**{STEP5_LABEL}**"]
    if not res["ok"]:
        return "\n".join(lines + ["", "⚠️ " + res["note"]])
    if not res["findings"]:
        lines.append("\n✅ Không phát hiện thêm vấn đề. Hồ sơ có thể chuyển Admin trình ký.")
        return "\n".join(lines)
    lines.append("")
    for f in res["findings"]:
        mark = {"high": "🔴", "medium": "🟠", "low": "🟢"}.get(f.get("severity"), "")
        lines.append(f"- {mark} {f.get('issue')}"
                     + (f" ↳ {f['suggestion']}" if f.get("suggestion") else ""))
    if res["blocking"]:
        if bounce_count >= MAX_BOUNCE:
            lines.append(f"\n⚠️ Đã quay lại Bước 4 {bounce_count} lần — **không quay lại "
                         f"nữa**. Chuyển trưởng Pháp chế quyết; Agent chỉ ghi nhận.")
        else:
            lines.append("\n🔴 **Có vấn đề mức chặn → đề nghị quay lại Bước 4** cho đúng "
                         "người đã rà soát. Admin tạm dừng trình ký tới khi xử lý xong.")
    else:
        lines.append("\nℹ️ Các điểm trên là **cảnh báo tham khảo**, không chặn trình ký. "
                     "Admin tiếp tục Bước 6; ghi log để Pháp chế review định kỳ.")
    return "\n".join(lines)
