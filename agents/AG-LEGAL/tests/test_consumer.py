"""Unit test offline cho consumer — mock engine/platform, không cần secrets/network.

Ba nhóm test tương ứng 3 nguyên tắc ở CLAUDE.md; nhóm "chuẩn platform" là **regression
guard**: nếu ai đó thêm lại việc tự gửi Lark hay hard-code persona, test đỏ ngay.
"""
import os
import pathlib
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("NLM_NOTEBOOK_KB_ID", "nb-test")

import pytest

import consumer
from legalkb.engine import Citation, EngineAnswer
from legalkb.flows import Bundle
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
    def model_auth_lease(self):
        return {}          # test offline: không có credential

    """Đủ bề mặt để consumer chạy: bộ nhớ + job + Lark broker."""

    def __init__(self, ctx=None):
        self.ctx = ctx or {}
        self.turns, self.summaries, self.facts_added = [], [], []
        self.sent, self.replies, self.events = [], [], []
        self.brain_items = []
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

    def add_brain_item(self, title, content, status="approved", source_url=None):
        self.brain_items.append((title, content, source_url))
        return {"ok": True}

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

    def poll(self, wait=25, n=5):
        raise KeyboardInterrupt          # dừng vòng lặp main() trong test


def make(tmp_path, ctx=None, engine_answer=None, lark=None):
    store = SourceStore(str(tmp_path / "t.db"))
    pf = FakePlatform(ctx)
    eng = FakeEngine(engine_answer or EngineAnswer(ok=True, text="ok"))
    g = Gates(store, pf, consumer.GROUP_CHAT_ID, sla_hours=1)
    b = Bundle(pf=pf, store=store, engine=eng, gates=g, lark=lark)
    return store, pf, eng, g, b


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
    store, pf, _, _, b = make(tmp_path)
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
    store, pf, eng, _, b = make(tmp_path, ctx)
    consumer.answer_s1("vậy còn khách lẻ?", ctx, "sess-A", eng, store)
    sent_question = eng.calls[0][0]
    assert "chính sách đổi trả khách sỉ" in sent_question
    assert "phụ trách mua hàng miền Bắc" in sent_question
    assert "vậy còn khách lẻ?" in sent_question


def test_turns_written_back_to_platform(tmp_path):
    store, pf, eng, g, b = make(tmp_path, ctx={"instruction_block": "x"})
    job = {"id": 1, "channel": "lark", "session_id": "s9",
           "payload": {"text": "quy định abc?", "chat_id": "oc_user", "sender_open_id": "ou_u"}}
    consumer.handle(job, b)
    roles = [r for _, r, _ in pf.turns]
    assert roles == ["user", "assistant"]


def test_conversation_id_is_optimisation_not_memory(tmp_path):
    """conversation_id vẫn được giữ per-session, nhưng lỗi thì KHÔNG ghi đè cái cũ."""
    store, pf, _, _, b = make(tmp_path)
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
        if path.name == "lark_kb.py":
            continue                       # ngoại lệ C9, kiểm riêng bên dưới
        assert "open-apis/im/" not in src, f"{path.name} tự gọi Lark IM API"


def test_c9_exception_stays_narrow():
    """Ngoại lệ C9 (gửi trực tiếp khi broker fail) phải HẸP và có điều kiện xoá.

    Chấp nhận đúng MỘT hàm im trong lark_kb.py, kèm ghi chú xoá khi core làm C9. Nếu ai
    thêm hàm im thứ hai hoặc bỏ ghi chú, test đỏ — để ngoại lệ không lặng lẽ phình ra
    thành "agent tự tích hợp Lark" như trước Phase 2A.
    """
    kb = (AGENT_DIR / "legalkb" / "lark_kb.py").read_text(encoding="utf-8")
    # Danh sách ĐÓNG: mỗi ngoại lệ một hàm, mỗi hàm một ĐIỀU KIỆN XOÁ. Thêm hàm im thứ ba
    # là test đỏ — để ngoại lệ không lặng lẽ phình ra thành "agent tự tích hợp Lark".
    assert kb.count("open-apis/im/") == 2, "chỉ được đúng 2 lời gọi IM API"
    assert "def im_send_markdown" in kb            # C9: gửi khi broker fail
    assert "def chat_members" in kb                # C13: đọc open_id theo đúng app
    assert kb.count("ĐIỀU KIỆN XOÁ") == 2, "mỗi ngoại lệ phải có điều kiện xoá"
    assert "C9" in kb and "C5" in kb
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

def test_s2_without_templates_says_so(tmp_path, monkeypatch):
    """Chưa cấu hình kho mẫu thì nói thật, không giả vờ soạn được hợp đồng."""
    store, pf, eng, g, b = make(tmp_path)
    monkeypatch.setattr(consumer.brain, "route",
                        lambda *a, **k: {"intent": "s2_create_contract", "risk": "medium",
                                         "contract_type": "", "reason": ""})
    job = {"id": 2, "channel": "lark", "session_id": "s2",
           "payload": {"text": "tạo hợp đồng dịch vụ", "chat_id": "oc_u"}}
    out = consumer.handle(job, b)
    assert "chưa được cấu hình" in out and "Pháp chế" in out
    assert eng.calls == []                 # không hỏi KB cho việc không thuộc S1


def test_attachment_routes_to_review_even_if_router_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(consumer.brain, "call_claude", lambda *a, **k: "không phải json")
    r = consumer.brain.route("nhờ xem hợp đồng", {}, has_attachment=True)
    assert r["intent"] == "s3_review_contract"


# ---------------- Pháp chế in the loop ----------------

def test_answer_leaves_audit_row_without_notifying_group(tmp_path):
    """Dòng `s1_answer` vẫn ghi — `#ds` và `#<id> tham gia` cần một mã để gọi tới — nhưng
    KHÔNG gửi card. Chốt 21/08: audit, không phải phê duyệt."""
    store, pf, eng, g, b = make(tmp_path)
    job = {"id": 3, "channel": "lark", "session_id": "s3",
           "payload": {"text": "quy định pháp chế?", "chat_id": "oc_user",
                       "sender_open_id": "ou_emp"}}
    consumer.handle(job, b)
    assert not [m for to, m in pf.sent if to == consumer.GROUP_CHAT_ID]
    gate = g.store.one("SELECT * FROM legal_gates WHERE session_id='s3'")
    assert gate["kind"] == "s1_answer" and gate["level"] == "observe"


def test_one_observe_gate_per_conversation(tmp_path):
    """Gom theo hội thoại — không mỗi lượt một card, tránh làm ồn group."""
    store, pf, eng, g, b = make(tmp_path)
    for i in range(3):
        consumer.handle({"id": 10 + i, "channel": "lark", "session_id": "same",
                         "payload": {"text": f"câu {i}", "chat_id": "oc_u"}}, b)
    assert len(g.store.query("SELECT * FROM legal_gates WHERE session_id='same'")) == 1


def test_answer_without_citation_is_high_risk(tmp_path):
    store, pf, eng, g, b = make(tmp_path,
                             engine_answer=EngineAnswer(ok=True, text="chưa quy định"))
    consumer.handle({"id": 4, "channel": "lark", "session_id": "s4",
                     "payload": {"text": "crypto?", "chat_id": "oc_u"}}, b)
    assert g.store.one("SELECT * FROM legal_gates WHERE session_id='s4'")["risk"] == "high"


def test_first_turn_answers_immediately_without_any_approval(tmp_path):
    """Chốt 21/08: chat lần đầu **không cần ai duyệt** — trả lời luôn, cho mọi người.

    Vẫn nói một câu là có ghi log (sự thật + điều kiện golive), nhưng đó là thông báo,
    không phải cổng chặn.
    """
    store, pf, eng, g, b = make(tmp_path, ctx={"n_turns": 0})
    out = consumer.handle({"id": 20, "channel": "lark", "session_id": "s-new",
                           "payload": {"text": "chào bạn", "chat_id": "oc_u"}}, b)
    assert out and out.startswith("Mình là **Legal Agent**")
    assert "ghi log" in out and "bộ nhớ" in out
    # KHÔNG gửi card vào group ở lượt đầu — kể cả khi bị tính rủi ro cao ("chào bạn"
    # không có trích dẫn nào). Đó chính là thứ chốt 21/08 bỏ.
    assert not [m for to, m in pf.sent if to == consumer.GROUP_CHAT_ID], \
        "lượt đầu không được gửi card vào group"


def test_later_turns_do_not_repeat_greeting(tmp_path):
    store, pf, eng, g, b = make(tmp_path, ctx={"n_turns": 4})
    out = consumer.handle({"id": 21, "channel": "lark", "session_id": "s-old",
                           "payload": {"text": "hỏi tiếp", "chat_id": "oc_u"}}, b)
    assert "Mình là **Legal Agent**" not in out
    assert "Pháp chế giám sát" in out          # vẫn còn nhắc ở footer


def test_conversation_turning_high_risk_alerts_reviewers(tmp_path):
    """Lượt đầu im, nhưng hội thoại ĐANG CHẠY mà chuyển sang rủi ro cao thì phải @ người
    trực — đó là báo động an toàn, không phải cổng phê duyệt (nó không chặn ai)."""
    store, pf, eng, g, b = make(tmp_path, engine_answer=EngineAnswer(
        ok=True, text="ok", citations=[Citation("Quy chế", "https://x/wiki/a", "")]))
    store.write("INSERT INTO legal_roles (email, role, contract_type, open_id, active) "
                "VALUES ('thint@hapas.vn','legal_reviewer','*','ou_thint',1)")
    consumer.handle({"id": 22, "channel": "lark", "session_id": "s-hr",
                     "payload": {"text": "giờ làm việc?", "chat_id": "oc_u"}}, b)
    assert not [m for to, m in pf.sent if to == consumer.GROUP_CHAT_ID], "lượt đầu im"

    b.engine.result = EngineAnswer(ok=True, text="chưa quy định")   # lượt sau mất trích dẫn
    consumer.handle({"id": 23, "channel": "lark", "session_id": "s-hr",
                     "payload": {"text": "crypto?", "chat_id": "oc_u"}}, b)
    card = next(m for to, m in pf.sent if to == consumer.GROUP_CHAT_ID)
    assert "<at id=ou_thint></at>" in card and "rủi ro cao" in card


def test_low_risk_conversation_is_audited_not_announced(tmp_path):
    """Rủi ro thấp: **không** gửi gì vào group, nhưng vẫn để lại dấu để tra lại.

    Trước 21/08 mỗi hội thoại đẻ một card trong group — vừa giống một hàng chờ phê duyệt,
    vừa là cách nhanh nhất để người ta tắt thông báo của group.
    """
    store, pf, eng, g, b = make(tmp_path, engine_answer=EngineAnswer(
        ok=True, text="ok", citations=[Citation("Quy chế", "https://x/wiki/a", "")]))
    store.write("INSERT INTO legal_roles (email, role, contract_type, open_id, active) "
                "VALUES ('thint@hapas.vn','legal_reviewer','*','ou_thint',1)")
    consumer.handle({"id": 23, "channel": "lark", "session_id": "s-lr",
                     "payload": {"text": "giờ làm việc?", "chat_id": "oc_u"}}, b)
    assert not [m for to, m in pf.sent if to == consumer.GROUP_CHAT_ID]
    # ba dấu vết audit: event trên job · lượt vào bộ nhớ · một dòng để `#ds`/`tham gia`
    assert any(e[1] == "audit" for e in pf.events), pf.events
    assert [t for t in pf.turns if t[0] == "s-lr"], "phải ghi lượt vào bộ nhớ"
    assert store.one("SELECT level FROM legal_gates WHERE kind='s1_answer'")["level"] == "observe"


def test_group_chatter_gets_no_reply(tmp_path):
    """Tin thường trong group duyệt → agent im lặng, không trả lời bừa."""
    store, pf, eng, g, b = make(tmp_path)
    job = {"id": 5, "channel": "lark", "session_id": "grp",
           "payload": {"text": "trưa nay ăn gì", "chat_id": consumer.GROUP_CHAT_ID,
                       "sender_open_id": "ou_thint"}}
    assert consumer.handle(job, b) is None


def test_agent_silent_while_human_joined(tmp_path):
    store, pf, eng, g, b = make(tmp_path)
    g.set_mode("s-join", "joined", taken_by="thint@hapas.vn")
    job = {"id": 6, "channel": "lark", "session_id": "s-join",
           "payload": {"text": "hỏi tiếp", "chat_id": "oc_u", "sender_open_id": "ou_u"}}
    assert consumer.handle(job, b) is None
    assert eng.calls == []                          # không gọi KB
    assert pf.turns == [("s-join", "user", "hỏi tiếp")]   # vẫn ghi lượt, không mất lịch sử


def test_warns_when_claude_cli_missing(tmp_path, monkeypatch, capsys):
    """Degrade âm thầm là thứ khó phát hiện nhất — phải cảnh báo lúc khởi động."""
    monkeypatch.setattr(consumer.brain, "available", lambda: False)
    store, pf, eng, g, b = make(tmp_path)
    monkeypatch.setattr(consumer, "build", lambda: b)
    monkeypatch.setattr(consumer, "apply_instruction", lambda *a: None)
    monkeypatch.setattr(consumer.threading, "Thread",
                        lambda *a, **k: type("T", (), {"start": lambda s: None})())
    with pytest.raises(KeyboardInterrupt):
        consumer.main()
    assert "KHÔNG tìm thấy CLI `claude`" in capsys.readouterr().err


def test_lark_send_carries_app_id(monkeypatch):
    """Phải gửi bằng ĐÚNG app đang là member của group; app khác thì không ai nhận được."""
    from legalkb.platform import Platform
    monkeypatch.setenv("LARK_BOT_APP_ID", "cli_test123")
    monkeypatch.setenv("LSR_AGENT_TOKEN", "t")
    pf = Platform()
    seen = {}
    monkeypatch.setattr(pf, "call", lambda m, p, payload=None, **k: seen.update(payload or {}))
    pf.lark_send("oc_x", markdown="hi")
    assert seen["app_id"] == "cli_test123" and seen["to"] == "oc_x"


def test_lark_send_ignores_wiki_app_id(monkeypatch):
    """LARK_APP_ID là app đọc Wiki/Drive; broker KHÔNG nạp được nó → truyền vào là 503
    và mất toàn bộ thông báo. Mặc định phải rỗng = app Admin dùng chung."""
    from legalkb.platform import Platform
    monkeypatch.setenv("LARK_APP_ID", "cli_wiki_only")
    monkeypatch.delenv("LARK_BOT_APP_ID", raising=False)
    monkeypatch.setenv("LSR_AGENT_TOKEN", "t")
    pf = Platform()
    seen = {}
    monkeypatch.setattr(pf, "call", lambda m, p, payload=None, **k: seen.update(payload or {}))
    pf.lark_send("oc_x", markdown="hi")
    assert "app_id" not in seen


def test_fallback_used_when_broker_cannot_send(monkeypatch):
    """Broker trả sent:false (app chưa trong LARK_EXTRA_APPS — C9) → phải gửi dự phòng,
    không được im lặng: im lặng là mất thông báo VÀ mất đường phê duyệt."""
    from legalkb.platform import Platform
    monkeypatch.setenv("LSR_AGENT_TOKEN", "t")
    sent = []
    pf = Platform(fallback=lambda chat, md: sent.append((chat, md)))
    monkeypatch.setattr(pf, "call", lambda *a, **k: {"sent": False})
    assert pf.lark_send("oc_x", markdown="cần duyệt #1") is True
    assert sent == [("oc_x", "cần duyệt #1")]


def test_no_fallback_configured_reports_failure(monkeypatch):
    from legalkb.platform import Platform
    monkeypatch.setenv("LSR_AGENT_TOKEN", "t")
    pf = Platform(fallback=None)
    monkeypatch.setattr(pf, "call", lambda *a, **k: {"sent": False})
    assert pf.lark_send("oc_x", markdown="x") is False


# ==================== credential model: lease, không dán token ====================

def test_lease_reads_secret_by_reference_never_from_env_file(tmp_path, monkeypatch):
    """Platform trả **tham chiếu**; secret nằm ở file trên VM (mount ro). Không ai phải
    dán token vào .env của agent hay vào git."""
    from legalkb import brain
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    (tmp_path / "model").mkdir()
    (tmp_path / "model" / "sub-x.env").write_text("sk-ant-oat-GIA-LAP\n")
    monkeypatch.setattr(brain, "SECRETS_DIR", str(tmp_path))

    class PF:
        def model_auth_lease(self):
            return {"mode": "subscription", "credential_id": "sub-x",
                    "secret_ref": "model/sub-x.env",
                    "env_var": "CLAUDE_CODE_OAUTH_TOKEN"}
    note = brain.lease_model_auth(PF())
    assert "sub-x" in note and "subscription" in note
    assert brain._lease["env"] == {"CLAUDE_CODE_OAUTH_TOKEN": "sk-ant-oat-GIA-LAP"}
    brain._lease.update(env=None, note="reset")


def test_lease_failure_is_reported_not_silent(tmp_path, monkeypatch):
    """Không lease được nghĩa là router rơi về mặc định và S2–S5 chỉ trả "chưa rà soát
    được" — degrade âm thầm là thứ khó phát hiện nhất."""
    from legalkb import brain
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setattr(brain, "SECRETS_DIR", str(tmp_path))

    class PF:
        def model_auth_lease(self):
            return {"mode": "subscription", "secret_ref": "model/khong-co.env",
                    "env_var": "CLAUDE_CODE_OAUTH_TOKEN"}
    note = brain.lease_model_auth(PF())
    assert "không đọc được" in note and "mount" in note
    assert brain._lease["env"] is None
    brain._lease.update(env=None, note="reset")


def test_existing_env_token_is_respected(monkeypatch):
    from legalkb import brain
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "co-san")

    class PF:
        def model_auth_lease(self):
            raise AssertionError("đã có token trong env thì không cần lease")
    assert "có sẵn" in brain.lease_model_auth(PF())
    brain._lease.update(env=None, note="reset")


# ==================== ai nhắn cũng được trả lời, đủ tính năng ====================

def test_any_sender_gets_a_full_answer_without_approval(tmp_path):
    """Chốt 21/08: KHÔNG có allowlist người dùng. Người chưa từng xuất hiện, không có
    trong legal_roles, nhắn lần đầu → vẫn được trả lời đầy đủ, không ai phải duyệt."""
    store, pf, eng, g, b = make(tmp_path, ctx={"n_turns": 0}, engine_answer=EngineAnswer(
        ok=True, text="Theo quy chế nội bộ…",
        citations=[Citation("Quy chế", "https://x/wiki/a", "")]))
    out = consumer.handle({"id": 77, "channel": "lark", "payload": {
        "text": "cho mình hỏi về hợp đồng thử việc",
        "chat_id": "oc_nguoi_hoan_toan_moi",
        "sender_open_id": "ou_chua_tung_thay"}}, b)
    assert out and "Theo quy chế nội bộ" in out
    assert not [m for to, m in pf.sent if to == consumer.GROUP_CHAT_ID], \
        "không gửi gì vào group — không phải hàng chờ phê duyệt"
    assert [t for t in pf.turns if t[0] == "lark:oc_nguoi_hoan_toan_moi"], \
        "phải ghi lượt vào bộ nhớ"
    assert any(e[1] == "audit" for e in pf.events), "phải có dấu audit"


def test_only_approval_commands_check_who_you_are(tmp_path):
    """Chỗ DUY NHẤT còn kiểm danh tính là lệnh quyết định trong group admin — bỏ nó thì ai
    cũng duyệt được hợp đồng của công ty."""
    store, pf, eng, g, b = make(tmp_path)
    out = consumer.handle_group({"id": 78, "channel": "lark", "payload": {
        "text": "#1 duyệt", "chat_id": consumer.GROUP_CHAT_ID,
        "sender_open_id": "ou_nguoi_ngoai"}}, b)
    assert "chưa có quyền" in out
