"""S3 — review hợp đồng đối tác (PLAN Phase 4).

Luồng: nhận file → trích text → lấy checklist pháp chế từ KB (NotebookLM) → Claude đối
chiếu → báo cáo rủi ro cho người nộp → vòng nộp lại → khi sạch thì **gate người có thẩm
quyền** xác nhận.

Checklist KHÔNG hard-code: legal team soạn "Checklist review hợp đồng" trên Wiki, sync
vào KB, module này hỏi KB ra. Không có checklist thì nói rõ là đang dùng nguyên tắc
chung — không im lặng giả vờ có.
"""
import json
import re
import time

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
SEVERITY_MARK = {"high": "🔴", "medium": "🟠", "low": "🟢"}

CHECKLIST_QUESTION = ("Checklist review hợp đồng của công ty gồm những mục nào? "
                      "Liệt kê đầy đủ từng mục cần kiểm tra.")

_REVIEW_PROMPT = """Bạn là trợ lý pháp chế nội bộ của Lam Son Retail (bán lẻ).

Đối chiếu HỢP ĐỒNG dưới đây với CHECKLIST/CHÍNH SÁCH của công ty. Chỉ dựa vào hai nguồn
này, không suy diễn thêm quy định không có.

Trả về DUY NHẤT một JSON, không thêm chữ nào khác:
{"findings": [{"severity": "high|medium|low", "clause": "điều/khoản hoặc 'THIẾU'",
               "issue": "vấn đề là gì", "suggestion": "đề xuất sửa cụ thể"}],
 "clean": true|false, "note": "nhận xét chung 1-2 câu"}

severity: high = có thể gây thiệt hại/tranh chấp hoặc trái quy định công ty;
medium = cần làm rõ trước khi ký; low = góp ý câu chữ.
clean = true chỉ khi KHÔNG còn mục high và medium.

=== CHECKLIST / CHÍNH SÁCH CÔNG TY ===
{checklist}

=== HỢP ĐỒNG ({file_name}) ===
{contract}
"""


def get_checklist(engine, store, ttl_h=24):
    """Lấy checklist từ KB, cache lại để mỗi hợp đồng không phải hỏi lại engine."""
    cached = store.get_meta("review_checklist")
    ts = float(store.get_meta("review_checklist_at") or 0)
    if cached and time.time() - ts < ttl_h * 3600:
        return cached, True
    ans = engine.ask(CHECKLIST_QUESTION)
    if not ans.ok or not (ans.text or "").strip():
        return "", False
    store.set_meta("review_checklist", ans.text.strip())
    store.set_meta("review_checklist_at", time.time())
    return ans.text.strip(), True


def analyse(brain, contract_text, checklist, file_name, model=None):
    """Đối chiếu bằng Claude. Trả (findings, clean, note) — lỗi model → findings rỗng +
    clean=False để KHÔNG bao giờ tự kết luận 'hợp đồng sạch' khi chưa thật sự rà được."""
    prompt = (_REVIEW_PROMPT
              .replace("{checklist}", checklist or "(chưa có checklist trong KB — dùng "
                                                   "nguyên tắc pháp lý chung)")
              .replace("{file_name}", file_name or "hợp đồng")
              .replace("{contract}", contract_text[:80_000]))
    raw = brain.call_claude(prompt, model=model, timeout=240)
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        return [], False, "Chưa rà soát được tự động (model không trả kết quả đọc được)."
    try:
        out = json.loads(m.group(0))
    except json.JSONDecodeError:
        return [], False, "Chưa rà soát được tự động (kết quả không đúng định dạng)."
    findings = [f for f in (out.get("findings") or []) if f.get("issue")]
    findings.sort(key=lambda f: SEVERITY_ORDER.get(f.get("severity"), 3))
    blocking = [f for f in findings if f.get("severity") in ("high", "medium")]
    return findings, (not blocking), (out.get("note") or "")


def render_report(findings, clean, note, file_name, has_checklist, round_no=1):
    head = f"**Kết quả rà soát** — {file_name or 'hợp đồng'}"
    if round_no > 1:
        head += f" (vòng {round_no})"
    lines = [head]
    if not has_checklist:
        lines.append("_⚠️ KB chưa có 'Checklist review hợp đồng' — kết quả dưới đây dựa "
                     "trên nguyên tắc chung, chưa đối chiếu checklist công ty._")
    if note:
        lines.append(note)
    if not findings:
        lines.append("\nKhông phát hiện điểm cần sửa theo checklist.")
    else:
        lines.append("")
        for i, f in enumerate(findings, 1):
            mark = SEVERITY_MARK.get(f.get("severity"), "")
            lines.append(f"{i}. {mark} **{f.get('clause') or 'THIẾU'}** — {f['issue']}")
            if f.get("suggestion"):
                lines.append(f"   ↳ Đề xuất: {f['suggestion']}")
    lines.append("")
    if clean:
        lines.append("✅ Không còn vấn đề chặn — mình đã chuyển bộ phận Pháp chế xác nhận.")
    else:
        lines.append("Sửa xong bạn gửi lại file để mình rà vòng tiếp. "
                     "Cần trao đổi thêm thì nhắn ở đây.")
    return "\n".join(lines)


class Reviews:
    def __init__(self, store):
        self.store = store

    def open(self, session_id, requester, chat_id, file_name, contract_type=None):
        prev = self.latest(session_id)
        round_no = (prev["round"] + 1) if prev and prev["status"] != "approved" else 1
        rid = self.store.write(
            "INSERT INTO contract_reviews (session_id, requester, chat_id, file_name, "
            "contract_type, status, round, created_at, updated_at) "
            "VALUES (?,?,?,?,?,'received',?,?,?)",
            (session_id, requester, chat_id, file_name, contract_type, round_no,
             time.time(), time.time()))
        return self.get(rid)

    def get(self, rid):
        r = self.store.one("SELECT * FROM contract_reviews WHERE id=?", (rid,))
        if r:
            try:
                r["findings"] = json.loads(r.get("findings") or "[]")
            except json.JSONDecodeError:
                r["findings"] = []
        return r

    def latest(self, session_id):
        return self.store.one("SELECT * FROM contract_reviews WHERE session_id=? "
                              "ORDER BY id DESC LIMIT 1", (session_id,))

    def save(self, rid, **f):
        if "findings" in f:
            f["findings"] = json.dumps(f["findings"], ensure_ascii=False)
        f["updated_at"] = time.time()
        sets = ", ".join(f"{k}=?" for k in f)
        self.store.write(f"UPDATE contract_reviews SET {sets} WHERE id=?",
                         (*f.values(), rid))
        return self.get(rid)
