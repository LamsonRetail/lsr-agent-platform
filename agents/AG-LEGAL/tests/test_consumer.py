"""Unit test offline cho consumer — mock engine/platform, không cần secrets/network.

Ba nhóm test tương ứng 3 nguyên tắc ở CLAUDE.md; nhóm "chuẩn platform" là **regression
guard**: nếu ai đó thêm lại việc tự gửi Lark hay hard-code persona, test đỏ ngay.
"""
import os
import pathlib
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("NLM_NOTEBOOK_KB_ID", "nb-test")

import consumer
from legalkb.engine import Citation, EngineAnswer
from legalkb.gates import Gates
from legalkb.store import SourceStore

AGENT_DIR = pathlib.Path(__file__).resolve().parent.parent


class FakeEngine:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def ask(self, question, conversation_id=None):
        self.calls.append((question, conversation_id))
        return self.result


class FakePlatform:
    """Đủ bề mặt để consumer chạy: bộ nhớ + job + Lark broker."""

    def __init__(self, ctx=None):
        self.ctx = ctx or {}
        self.turns, self.summaries, self.facts_added = [], [], []
        self.sent, self.replies, self.events = [], [], []
        self.token = "t"

    # bộ nhớ
    def context(self, session_id, user_ref="", q="", env=None, k=0):
        return dict(self.ctx)

    def add_turn(self, session_id, role, text, user_ref=None, channel=None):
        self.turns.append((session_id, role, text))
        return {}

    def set_summary(self, session_id, summary):
        self.summaries.append((session_id, summary))

    def add_fact(self, user_ref, fact, source=None):
        self.facts_added.append((user_ref, fact))

    # job
    def reply(self, job_id, text):
        self.replies.append((job_id, text))
        return {"sent": True}

    def event(self, job_id, kind, data=None):
        self.events.append((job_id, kind))

    def complete(self, job_id, result=None):
        return {}

    def fail(self, job_id, error):
        return {}

    # Lark broker
    def lark_send(self, to, text=None, markdown=None, to_type="chat_id"):
        self.sent.append((to, markdown or text))
        return True

    def lark_resolve(self, email):
        return "ou_" + email.split("@")[0]

    def lark_chats(self, app_id=""):
        return [{"chat_id": consumer.GROUP_CHAT_ID}]


def make(tmp_path, ctx=None, engine_answer=None):
    store = SourceStore(str(tmp_path / "t.db"))
    pf = FakePlatform(ctx)
    eng = FakeEngine(engine_answer or EngineAnswer(ok=True, text="ok"))
    g = Gates(store, pf, consumer.GROUP_CHAT_ID, sla_hours=1)
    return store, pf, eng, g


# ---------------- hợp đồng câu trả lời ----------------

def test_format_reply_full_contract():
    ans = EngineAnswer(ok=True, text="Thời hạn tối đa 45 ngày.",
                       citations=[Citation("Quy chế TC", "https://tenant/wiki/a", "..."),
                                  Citation("Nguồn #2", "", "...")])
    out = consumer.format_reply(ans, kb_updated_at="2026-08-12 15:00:00")
    assert "📎 **Nguồn:**" in out
    assert "[Quy chế TC](https://tenant/wiki/a)" in out
    assert "Nguồn #2" not in out           # citation không map được link → không liệt kê
    assert "KB cập nhật lúc 2026-08-12" in out
    assert "Tham khảo nội bộ" in out
    assert "Pháp chế giám sát" in out      # nghĩa vụ thông báo giám sát (PLAN §4)


def test_degrade_on_engine_error(tmp_path):
    store, pf, _, _ = make(tmp_path)
    eng = FakeEngine(EngineAnswer(ok=False, error="RPCError: boom"))
    ans = consumer.answer_s1("câu hỏi", {}, "s1", eng, store)
    out = consumer.format_reply(ans)
    assert "không truy cập được kho tài liệu" in out
    assert "boom" not in out               # không lộ lỗi kỹ thuật cho người dùng


# ---------------- nguyên tắc 1: bộ nhớ ở platform ----------------

def test_kb_question_carries_platform_context(tmp_path):
    """Ngữ cảnh phải đi từ /v1/self/context vào câu hỏi, không dựa vào phiên engine."""
    ctx = {"rolling_summary": "Đang hỏi về chính sách đổi trả khách sỉ.",
           "recent_turns": [{"role": "user", "text": "khách sỉ đổi trả thế nào?"}],
           "user_facts": ["phụ trách mua hàng miền Bắc"]}
    store, pf, eng, _ = make(tmp_path, ctx)
    consumer.answer_s1("vậy còn khách lẻ?", ctx, "sess-A", eng, store)
    sent_question = eng.calls[0][0]
    assert "chính sách đổi trả khách sỉ" in sent_question
    assert "phụ trách mua hàng miền Bắc" in sent_question
    assert "vậy còn khách lẻ?" in sent_question


def test_turns_written_back_to_platform(tmp_path):
    store, pf, eng, g = make(tmp_path, ctx={"instruction_block": "x"})
    job = {"id": 1, "channel": "lark", "session_id": "s9",
           "payload": {"text": "quy định abc?", "chat_id": "oc_user", "sender_open_id": "ou_u"}}
    consumer.handle(job, pf, store, eng, g)
    roles = [r for _, r, _ in pf.turns]
    assert roles == ["user", "assistant"]


def test_conversation_id_is_optimisation_not_memory(tmp_path):
    """conversation_id vẫn được giữ per-session, nhưng lỗi thì KHÔNG ghi đè cái cũ."""
    store, pf, _, _ = make(tmp_path)
    eng = FakeEngine(EngineAnswer(ok=True, text="ok", conversation_id="conv-9"))
    consumer.answer_s1("câu 1", {}, "sess-A", eng, store)
    consumer.answer_s1("câu 2", {}, "sess-A", eng, store)
    assert eng.calls[0][1] is None and eng.calls[1][1] == "conv-9"

    store.set_meta("conv:s", "conv-old")
    consumer.answer_s1("q", {}, "s", FakeEngine(EngineAnswer(ok=False, error="x")), store)
    assert store.get_meta("conv:s") == "conv-old"


# ---------------- nguyên tắc 2 & 3: regression guard chuẩn platform ----------------

def _agent_sources():
    for p in list(AGENT_DIR.glob("*.py")) + list((AGENT_DIR / "legalkb").glob("*.py")):
        yield p, p.read_text(encoding="utf-8")


def test_no_direct_lark_messaging_outside_kb_reader():
    """Gửi/nhận tin Lark PHẢI qua platform. lark_kb.py chỉ được đọc Wiki/Drive.

    Bắt theo đường dẫn API thật (`open-apis/im/...`) chứ không theo chữ trong tài liệu —
    nếu không, chính câu ghi chú "không được gọi im/v1/messages" sẽ làm test đỏ.
    """
    for path, src in _agent_sources():
        assert "open-apis/im/" not in src, f"{path.name} tự gọi Lark IM API"
    kb = (AGENT_DIR / "legalkb" / "lark_kb.py").read_text(encoding="utf-8")
    assert "def send_text" not in kb and "def recall" not in kb


def test_persona_not_hardcoded_in_consumer():
    """Hành vi phải đến từ instruction_block, không phải hằng số trong code."""
    src = (AGENT_DIR / "consumer.py").read_text(encoding="utf-8")
    assert "CHAT_PROMPT" not in src
    assert "instruction_block" in src
    assert (AGENT_DIR / "INSTRUCTION.md").exists()
    assert not (AGENT_DIR / "system_prompt.md").exists()


def test_no_telegram_in_scope():
    """Telegram đã bỏ khỏi scope (chốt 17/08) — không còn code nhánh telegram."""
    for path, src in _agent_sources():
        assert "telegram" not in src.lower(), f"{path.name} còn nhắc telegram"


# ---------------- router + luồng không sẵn sàng ----------------

def test_unimplemented_skill_says_so(tmp_path, monkeypatch):
    """S2–S5 chưa mở thì phải nói thật, không giả vờ làm được."""
    store, pf, eng, g = make(tmp_path)
    monkeypatch.setattr(consumer.brain, "route",
                        lambda *a, **k: {"intent": "s2_create_contract", "risk": "medium",
                                         "contract_type": "", "reason": ""})
    job = {"id": 2, "channel": "lark", "session_id": "s2",
           "payload": {"text": "tạo hợp đồng dịch vụ", "chat_id": "oc_u"}}
    out = consumer.handle(job, pf, store, eng, g)
    assert "đang được xây" in out and "Pháp chế" in out
    assert eng.calls == []                 # không hỏi KB cho việc không thuộc S1


def test_attachment_routes_to_review_even_if_router_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(consumer.brain, "call_claude", lambda *a, **k: "không phải json")
    r = consumer.brain.route("nhờ xem hợp đồng", {}, has_attachment=True)
    assert r["intent"] == "s3_review_contract"


# ---------------- Pháp chế in the loop ----------------

def test_answer_opens_observe_gate_and_notifies_group(tmp_path):
    store, pf, eng, g = make(tmp_path)
    job = {"id": 3, "channel": "lark", "session_id": "s3",
           "payload": {"text": "quy định pháp chế?", "chat_id": "oc_user",
                       "sender_open_id": "ou_emp"}}
    consumer.handle(job, pf, store, eng, g)
    assert pf.sent and pf.sent[0][0] == consumer.GROUP_CHAT_ID
    gate = g.store.one("SELECT * FROM legal_gates WHERE session_id='s3'")
    assert gate["kind"] == "s1_answer" and gate["level"] == "observe"


def test_one_observe_gate_per_conversation(tmp_path):
    """Gom theo hội thoại — không mỗi lượt một card, tránh làm ồn group."""
    store, pf, eng, g = make(tmp_path)
    for i in range(3):
        consumer.handle({"id": 10 + i, "channel": "lark", "session_id": "same",
                         "payload": {"text": f"câu {i}", "chat_id": "oc_u"}},
                        pf, store, eng, g)
    assert len(g.store.query("SELECT * FROM legal_gates WHERE session_id='same'")) == 1


def test_answer_without_citation_is_high_risk(tmp_path):
    store, pf, eng, g = make(tmp_path,
                             engine_answer=EngineAnswer(ok=True, text="chưa quy định"))
    consumer.handle({"id": 4, "channel": "lark", "session_id": "s4",
                     "payload": {"text": "crypto?", "chat_id": "oc_u"}}, pf, store, eng, g)
    assert g.store.one("SELECT * FROM legal_gates WHERE session_id='s4'")["risk"] == "high"


def test_group_chatter_gets_no_reply(tmp_path):
    """Tin thường trong group duyệt → agent im lặng, không trả lời bừa."""
    store, pf, eng, g = make(tmp_path)
    job = {"id": 5, "channel": "lark", "session_id": "grp",
           "payload": {"text": "trưa nay ăn gì", "chat_id": consumer.GROUP_CHAT_ID,
                       "sender_open_id": "ou_thint"}}
    assert consumer.handle(job, pf, store, eng, g) is None


def test_agent_silent_while_human_joined(tmp_path):
    store, pf, eng, g = make(tmp_path)
    g.set_mode("s-join", "joined", taken_by="thint@hapas.vn")
    job = {"id": 6, "channel": "lark", "session_id": "s-join",
           "payload": {"text": "hỏi tiếp", "chat_id": "oc_u", "sender_open_id": "ou_u"}}
    assert consumer.handle(job, pf, store, eng, g) is None
    assert eng.calls == []                          # không gọi KB
    assert pf.turns == [("s-join", "user", "hỏi tiếp")]   # vẫn ghi lượt, không mất lịch sử
