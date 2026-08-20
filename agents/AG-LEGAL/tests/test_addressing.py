"""Ann gọi tên mới trả lời, nghe được tin thoại, và nhớ ngữ cảnh theo chat/nhóm."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("NLM_NOTEBOOK_KB_ID", "nb-test")

import consumer
from legalkb import addressing, voice
from legalkb.engine import EngineAnswer
from tests.test_consumer import FakeEngine, make

GROUP_ADMIN = consumer.GROUP_CHAT_ID
GROUP_OTHER = "oc_7323f9808ed5c376662c1bbe8e3a5d67"


import pytest


@pytest.fixture(autouse=True)
def _declare_group(monkeypatch):
    """GROUP_OTHER là nhóm. Lark không cho phân biệt nhóm/chat riêng bằng chat_id nên
    phải khai tường minh (hoặc chờ core truyền chat_type — C12)."""
    monkeypatch.setenv("AGENT_GROUP_CHAT_IDS", GROUP_OTHER)


# ---------------- bộ nhớ theo chat/nhóm ----------------

def test_session_keyed_by_chat_not_by_job():
    """Gateway không set session_id. Nếu khoá theo job id thì mỗi tin là một phiên mới và
    agent không nhớ gì — đây chính là bug đã có."""
    j1 = {"id": 1, "channel": "lark", "payload": {"chat_id": GROUP_OTHER}}
    j2 = {"id": 999, "channel": "lark", "payload": {"chat_id": GROUP_OTHER}}
    s1 = addressing.session_for(j1, j1["payload"])
    s2 = addressing.session_for(j2, j2["payload"])
    assert s1 == s2 == f"lark:{GROUP_OTHER}"      # hai tin khác job → CÙNG phiên


def test_session_prefers_platform_value():
    j = {"id": 5, "session_id": "sess-cua-platform", "payload": {"chat_id": "oc_x"}}
    assert addressing.session_for(j, j["payload"]) == "sess-cua-platform"


def test_session_falls_back_to_job_only_without_chat():
    j = {"id": 7, "channel": "web", "payload": {}}
    assert addressing.session_for(j, {}) == "job-7"


def test_two_groups_have_separate_memory():
    a = addressing.session_for({"id": 1, "payload": {"chat_id": "oc_a"}}, {"chat_id": "oc_a"})
    b = addressing.session_for({"id": 2, "payload": {"chat_id": "oc_b"}}, {"chat_id": "oc_b"})
    assert a != b


# ---------------- gọi tên ----------------

def test_called_by_name_variants():
    for t in ["Ann xem giúp hợp đồng này", "ANN NGUYEN ơi", "ann nguyễn cho hỏi",
              "@_user_1 cho hỏi chính sách", "hỏi Legal Agent chút", "AG-LEGAL ơi"]:
        assert addressing.called_by_name(t), t


def test_not_called_when_nobody_names_agent():
    for t in ["trưa nay ăn gì", "gửi anh bản hợp đồng nhé", "", None]:
        assert not addressing.called_by_name(t), t


def test_aliases_configurable(monkeypatch):
    monkeypatch.setenv("AGENT_NAME_ALIASES", "cô luật,legalbot")
    assert addressing.called_by_name("cô luật ơi xem giúp")
    assert not addressing.called_by_name("Ann ơi")     # alias mặc định đã bị thay


# ---------------- khi nào trả lời ----------------

def test_dm_always_answered():
    """Chat riêng: không cần gọi tên. Lark dùng 'oc_' cho cả p2p nên không được đoán theo
    tiền tố — chat không khai trong AGENT_GROUP_CHAT_IDS thì coi là chat riêng."""
    for payload in ({"chat_id": "oc_chat_rieng", "text": "hỏi gì đó"},
                    {"text": "hỏi gì đó"}):
        ok, why = addressing.should_answer(payload, None, admin_group=GROUP_ADMIN)
        assert ok and "riêng" in why, payload


def test_chat_type_wins_over_config():
    """Khi core truyền chat_type (C12) thì tin nó, không cần khai danh sách nữa."""
    ok, _ = addressing.should_answer(
        {"chat_id": "oc_chua_khai", "chat_type": "group", "text": "bàn việc"}, None)
    assert not ok
    ok, _ = addressing.should_answer(
        {"chat_id": GROUP_OTHER, "chat_type": "p2p", "text": "bàn việc"}, None)
    assert ok


def test_group_needs_name():
    payload = {"chat_id": GROUP_OTHER, "text": "mọi người xem hộ cái hợp đồng"}
    ok, why = addressing.should_answer(payload, None, admin_group=GROUP_ADMIN)
    assert not ok and "không gọi tên" in why

    payload["text"] = "Ann xem hộ cái hợp đồng"
    ok, why = addressing.should_answer(payload, None, admin_group=GROUP_ADMIN)
    assert ok and "gọi tên" in why


def test_admin_group_is_command_only():
    ok, why = addressing.should_answer({"chat_id": GROUP_ADMIN, "text": "Ann ơi"}, None,
                                       admin_group=GROUP_ADMIN)
    assert not ok and "chỉ xử lý lệnh" in why


def test_group_chatter_still_recorded_for_context(tmp_path):
    """Không trả lời NHƯNG vẫn ghi lượt: để khi có người gọi tên, agent đã có ngữ cảnh."""
    store, pf, eng, g, b = make(tmp_path)
    job = {"id": 11, "channel": "lark",
           "payload": {"chat_id": GROUP_OTHER, "text": "bên A đòi giảm 10%",
                       "sender_open_id": "ou_nv"}}
    assert consumer.handle(job, b) is None
    assert pf.turns == [(f"lark:{GROUP_OTHER}", "user", "bên A đòi giảm 10%")]
    assert eng.calls == []                     # không hỏi KB khi không được gọi


def test_named_message_in_group_gets_answered(tmp_path):
    store, pf, eng, g, b = make(tmp_path,
                                engine_answer=EngineAnswer(ok=True, text="Theo tài liệu…"))
    job = {"id": 12, "channel": "lark",
           "payload": {"chat_id": GROUP_OTHER, "text": "Ann cho hỏi chính sách đổi trả",
                       "sender_open_id": "ou_nv"}}
    out = consumer.handle(job, b)
    assert "Theo tài liệu" in out
    assert eng.calls, "được gọi tên thì phải tra KB"


def test_group_conversation_shares_one_session(tmp_path):
    """Cả nhóm dùng chung một mạch hội thoại — câu sau hiểu được câu trước."""
    store, pf, eng, g, b = make(tmp_path,
                                engine_answer=EngineAnswer(ok=True, text="ok"))
    for i, text in enumerate(["bên A đòi giảm 10%", "Ann thấy có ổn không?"]):
        consumer.handle({"id": 20 + i, "channel": "lark",
                         "payload": {"chat_id": GROUP_OTHER, "text": text,
                                     "sender_open_id": "ou_nv"}}, b)
    sids = {s for s, _, _ in pf.turns}
    assert sids == {f"lark:{GROUP_OTHER}"}     # cùng một phiên, không tách theo job


# ---------------- nghe tin thoại ----------------

def test_voice_detected_by_message_type():
    assert voice.is_voice({"message_type": "audio"})
    assert voice.is_voice({"message_type": "media"})
    assert not voice.is_voice({"message_type": "text"})


def test_voice_without_transcriber_says_so_not_silence(tmp_path, monkeypatch):
    """Im lặng là tệ nhất: người gửi voice sẽ tưởng agent đã nghe, hoặc tưởng nó hỏng."""
    monkeypatch.delenv("LSR_TRANSCRIBE_URL", raising=False)
    store, pf, eng, g, b = make(tmp_path)
    job = {"id": 30, "channel": "lark",
           "payload": {"message_type": "audio", "file_key": "fk", "message_id": "om",
                       "duration": 5000, "sender_open_id": "ou_nv"}}
    out = consumer.handle(job, b)
    assert out and "chưa nghe được tin nhắn thoại" in out
    assert eng.calls == []
    assert pf.turns and pf.turns[0][2] == "(tin nhắn thoại)"   # vẫn có dấu vết


def test_voice_too_long_is_refused_politely(monkeypatch):
    monkeypatch.setenv("LSR_TRANSCRIBE_URL", "http://x/transcribe")
    monkeypatch.setattr(voice, "MAX_SECONDS", 60)
    text, err = voice.hear(None, {}, {"duration": 120}, log=lambda m: None)
    assert text is None and "dài quá" in err


def test_voice_transcript_becomes_the_question(tmp_path, monkeypatch):
    monkeypatch.setenv("LSR_TRANSCRIBE_URL", "http://x/transcribe")
    monkeypatch.setattr(voice, "transcribe", lambda data, hint="": "chính sách đổi trả sỉ")
    store, pf, eng, g, b = make(tmp_path,
                                engine_answer=EngineAnswer(ok=True, text="Theo tài liệu…"))
    monkeypatch.setattr(pf, "lark_resource", lambda *a, **k: b"audio-bytes", raising=False)
    job = {"id": 31, "channel": "lark",
           "payload": {"message_type": "audio", "file_key": "fk", "message_id": "om",
                       "duration": 3000, "sender_open_id": "ou_nv"}}
    out = consumer.handle(job, b)
    assert "Theo tài liệu" in out
    assert "chính sách đổi trả sỉ" in eng.calls[0][0]      # transcript đi vào câu hỏi
    assert any("chính sách đổi trả sỉ" in t for _, _, t in pf.turns)


def test_voice_download_failure_reports_instead_of_crashing(tmp_path, monkeypatch):
    monkeypatch.setenv("LSR_TRANSCRIBE_URL", "http://x/transcribe")
    store, pf, eng, g, b = make(tmp_path)

    def boom(*a, **k):
        raise RuntimeError("403")

    monkeypatch.setattr(pf, "lark_resource", boom, raising=False)
    out = consumer.handle({"id": 32, "channel": "lark",
                           "payload": {"message_type": "audio", "file_key": "fk",
                                       "message_id": "om", "sender_open_id": "ou_nv"}}, b)
    assert "không tải được tin nhắn thoại" in out


# ---------------- không cần approve ----------------

def test_answering_when_called_needs_no_approval(tmp_path):
    """Trả lời khi được gọi là luồng observe — không mở gate chặn, không chờ ai duyệt."""
    store, pf, eng, g, b = make(tmp_path,
                                engine_answer=EngineAnswer(ok=True, text="Theo tài liệu…"))
    consumer.handle({"id": 40, "channel": "lark",
                     "payload": {"chat_id": GROUP_OTHER, "text": "Ann cho hỏi",
                                 "sender_open_id": "ou_nv"}}, b)
    gates = store.query("SELECT * FROM legal_gates")
    assert gates and all(x["level"] == "observe" for x in gates)
    assert not [x for x in gates if x["level"] == "gate"]
