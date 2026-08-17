"""Khung "Pháp chế in the loop" — PLAN §4.

Ba mức can thiệp, một cơ chế:
  observe  N1  báo vào group, KHÔNG chặn      (S1, S5 bước 3/5)
  gate     N2  chặn tới khi có người quyết    (S2 draft, S4 digest, S3 bước cuối)
  takeover N3  người thay Agent trong 1 session

Nhận quyết định bằng **lệnh nhắn trong group** (PLAN §2.5) — chạy được ngay, không
chờ core làm nút card Lark:

    #12 duyệt              #12 sửa: <góp ý>        #12 huỷ: <lý do>
    #12 tham gia           #12 trả lại             #ds
    #12 nhắn: <nội dung>   (chuyển lời tới người hỏi khi đang tham gia — Lark DM 1-1)

Chỉ người trong `legal_roles` gõ mới có hiệu lực (đối chiếu `sender_open_id`).
"""
import json
import re
import time
import unicodedata

OBSERVE = "observe"
GATE = "gate"

KINDS = {"s1_answer", "s2_draft", "s3_review", "s4_digest", "s5_step3", "s5_step5"}
OPEN_STATUSES = ("open", "joined", "changes_requested")

# Nhãn tiếng Việt cho card gửi vào group
KIND_LABEL = {
    "s1_answer": "Hỏi đáp pháp chế",
    "s2_draft": "Bản thảo hợp đồng — CHỜ DUYỆT",
    "s3_review": "Review hợp đồng đối tác — CHỜ DUYỆT",
    "s4_digest": "Digest văn bản luật — CHỜ DUYỆT",
    "s5_step3": "Trình ký · Bước 3 — rà soát sơ bộ",
    "s5_step5": "Trình ký · Bước 5 — cross-check",
}
RISK_MARK = {"high": "🔴", "medium": "🟠", "low": "🟢"}

# Hết hạn thì làm gì: observe không bao giờ chặn nên tự thông; gate thì CHỜ, chỉ nhắc.
SLA_ACTION = {OBSERVE: "auto_passed", GATE: "remind"}


def _plain(s):
    """Bỏ dấu + hạ chữ để so lệnh: 'Duyệt' == 'duyet'."""
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


_CMD_RE = re.compile(r"^\s*#\s*(\d+)\s+(.+)$", re.S)
_LIST_RE = re.compile(r"^\s*#\s*(ds|danh\s*sach)\s*$")

# Từ khoá → action. Đặt cụm 2 từ trước để 'tra lai' không khớp nhầm.
_ACTIONS = [
    ("tham gia", "join"), ("thamgia", "join"),
    ("tra lai", "release"), ("tralai", "release"), ("nha", "release"),
    ("duyet", "approve"), ("ok", "approve"), ("dong y", "approve"),
    ("sua", "changes"), ("chinh", "changes"),
    ("huy", "reject"), ("tu choi", "reject"), ("khong duyet", "reject"),
    ("nhan", "relay"), ("noi", "relay"),
]


def parse_command(text):
    """Tách lệnh trong group. Trả (gate_id|None, action, arg) hoặc None nếu không phải lệnh.

    action ∈ approve | changes | reject | join | release | relay | list
    """
    if not text:
        return None
    if _LIST_RE.match(text):
        return (None, "list", "")
    m = _CMD_RE.match(text)
    if not m:
        return None
    gate_id, rest = int(m.group(1)), m.group(2).strip()
    # Phần sau dấu ':' là góp ý/lý do — tách trước khi so từ khoá.
    head, _, arg = rest.partition(":")
    head_plain = _plain(head)
    for kw, action in _ACTIONS:
        if head_plain == kw or head_plain.startswith(kw + " ") or head_plain == kw.replace(" ", ""):
            return (gate_id, action, arg.strip())
    return None


class Gates:
    def __init__(self, store, platform, group_chat_id, sla_hours=4.0):
        self.store = store
        self.pf = platform
        self.group = group_chat_id
        self.sla_hours = float(sla_hours)

    # ---------- quyền ----------

    def roles(self, role=None):
        sql = "SELECT * FROM legal_roles WHERE active=1"
        params = ()
        if role:
            sql += " AND role=?"
            params = (role,)
        return self.store.query(sql, params)

    def reviewer_by_open_id(self, open_id):
        """open_id người gõ lệnh → dòng legal_roles, hoặc None nếu không có quyền.

        open_id được resolve từ email 1 lần rồi cache — xem sync_roles().
        """
        if not open_id:
            return None
        return self.store.one(
            "SELECT * FROM legal_roles WHERE open_id=? AND active=1 LIMIT 1", (open_id,))

    def sync_roles(self):
        """Resolve email → open_id qua broker platform cho các dòng còn thiếu."""
        done = 0
        for r in self.store.query("SELECT * FROM legal_roles WHERE active=1 AND "
                                  "(open_id IS NULL OR open_id='')"):
            oid = self.pf.lark_resolve(r["email"])
            if oid:
                self.store.write("UPDATE legal_roles SET open_id=? WHERE email=?",
                                 (oid, r["email"]))
                done += 1
        return done

    # ---------- mở / thông báo ----------

    def open(self, kind, level, *, title="", payload=None, risk="low", session_id=None,
             channel=None, requester_ref=None, sla_hours=None, round_no=1, notify=True):
        assert kind in KINDS, f"kind lạ: {kind}"
        assert level in (OBSERVE, GATE)
        now = time.time()
        hours = self.sla_hours if sla_hours is None else float(sla_hours)
        gid = self.store.write(
            "INSERT INTO legal_gates (kind, level, risk, session_id, channel, "
            "requester_ref, title, payload, status, round, sla_deadline, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,'open',?,?,?)",
            (kind, level, risk, session_id, channel, requester_ref, title,
             json.dumps(payload or {}, ensure_ascii=False), round_no,
             now + hours * 3600, now))
        if notify:
            self.notify(self.get(gid))
        return gid

    def get(self, gate_id):
        g = self.store.one("SELECT * FROM legal_gates WHERE id=?", (gate_id,))
        if g:
            try:
                g["payload"] = json.loads(g.get("payload") or "{}")
            except json.JSONDecodeError:
                g["payload"] = {}
        return g

    def open_list(self):
        return self.store.query(
            "SELECT id, kind, level, risk, title, status, created_at FROM legal_gates "
            f"WHERE status IN ({','.join('?' * len(OPEN_STATUSES))}) ORDER BY id",
            OPEN_STATUSES)

    def notify(self, gate):
        """Gửi card vào group Pháp chế/Admin. Lỗi gửi không được làm chết luồng chính."""
        if not (gate and self.group):
            return False
        return self.pf.lark_send(self.group, markdown=self.render(gate))

    def mentions(self, role="legal_reviewer"):
        """Chuỗi @ những người cần đọc ngay. Không có open_id thì bỏ qua, không chèn rác."""
        ids = [r["open_id"] for r in self.roles(role) if r.get("open_id")]
        return " ".join(f"<at id={i}></at>" for i in ids)

    def render(self, gate):
        p = gate.get("payload") or {}
        mark = RISK_MARK.get(gate.get("risk") or "low", "")
        lines = []
        # Rủi ro cao thì phải có người đọc NGAY → gắn @; các mức khác chỉ để theo dõi,
        # @ tất cả mọi thứ là cách nhanh nhất để người ta tắt thông báo của group.
        if (gate.get("risk") or "low") == "high":
            at = self.mentions()
            if at:
                lines.append(at + " **cần xem ngay**")
        lines.append(f"**#{gate['id']} · {KIND_LABEL.get(gate['kind'], gate['kind'])}** {mark}")
        if gate.get("title"):
            lines.append(gate["title"])
        for label, key in (("Người yêu cầu", "requester_name"), ("Câu hỏi", "question"),
                           ("Nội dung", "summary"), ("Tệp", "file")):
            if p.get(key):
                lines.append(f"- **{label}:** {p[key]}")
        if p.get("sources"):
            lines.append("- **📎 Nguồn:** " + " · ".join(p["sources"][:5]))
        if gate["level"] == GATE:
            lines.append(f"\n➡️ Trả lời trong nhóm: `#{gate['id']} duyệt` · "
                         f"`#{gate['id']} sửa: <góp ý>` · `#{gate['id']} huỷ: <lý do>`")
        else:
            lines.append(f"\nℹ️ Chỉ để theo dõi. Muốn vào hỗ trợ trực tiếp: "
                         f"`#{gate['id']} tham gia`")
        return "\n".join(lines)

    # ---------- quyết định ----------

    def decide(self, gate_id, action, reviewer_email, comment=""):
        """Ghi quyết định. Trả gate đã cập nhật, hoặc None nếu không hợp lệ."""
        g = self.get(gate_id)
        if not g:
            return None
        if g["status"] not in OPEN_STATUSES:
            return {**g, "_error": f"đã ở trạng thái {g['status']}"}
        status = {"approve": "approved", "changes": "changes_requested",
                  "reject": "rejected", "join": "joined"}.get(action)
        if not status:
            return {**g, "_error": f"hành động lạ: {action}"}
        self.store.write(
            "UPDATE legal_gates SET status=?, reviewer=?, comment=?, decided_at=? "
            "WHERE id=?", (status, reviewer_email, comment or None, time.time(), gate_id))
        return self.get(gate_id)

    # ---------- takeover ----------

    def mode(self, session_id):
        r = self.store.one("SELECT * FROM session_modes WHERE session_id=?", (session_id,))
        return (r or {}).get("mode", "auto")

    def set_mode(self, session_id, mode, taken_by=None, chat_id=None):
        self.store.write(
            "INSERT INTO session_modes (session_id, mode, taken_by, chat_id, since) "
            "VALUES (?,?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET "
            "mode=excluded.mode, taken_by=excluded.taken_by, since=excluded.since",
            (session_id, mode, taken_by, chat_id, time.time()))

    # ---------- SLA ----------

    def sla_tick(self):
        """Nhắc gate quá hạn; observe quá hạn thì tự thông (không bao giờ chặn S1/S5).

        Nguyên tắc: **gate KHÔNG tự động thông qua** — quá hạn chỉ nhắc, để người quyết.
        """
        now, acted = time.time(), []
        for g in self.store.query(
                "SELECT * FROM legal_gates WHERE status='open' AND sla_deadline<? "
                "ORDER BY id", (now,)):
            if SLA_ACTION[g["level"]] == "auto_passed":
                self.store.write(
                    "UPDATE legal_gates SET status='auto_passed', decided_at=? WHERE id=?",
                    (now, g["id"]))
                acted.append(("auto_passed", g["id"]))
            elif not g["reminded"]:
                self.store.write("UPDATE legal_gates SET reminded=1 WHERE id=?", (g["id"],))
                self.pf.lark_send(
                    self.group,
                    markdown=f"⏰ **Nhắc: #{g['id']} quá hạn duyệt** — "
                             f"{KIND_LABEL.get(g['kind'], g['kind'])}. "
                             f"Việc này **không tự động thông qua**, cần người quyết: "
                             f"`#{g['id']} duyệt` / `#{g['id']} sửa:` / `#{g['id']} huỷ:`")
                acted.append(("reminded", g["id"]))
        return acted
