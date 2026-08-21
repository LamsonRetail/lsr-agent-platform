"""Chat dưới danh tính account của agent — poll qua broker C8 (mẫu: jenny-bod-assistant)."""
import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("NLM_NOTEBOOK_KB_ID", "nb-test")

import consumer
from legalkb import userchat
from tests.test_consumer import make

OK_STATUS = {"connected": True, "subject": "ann@x.vn",
             "scope": "im:chat:readonly im:message im:message:readonly offline_access",
             "path_prefixes": ["/open-apis/im/v1/"]}


class PF:
    """Broker giả: ghi lại lời gọi, trả dữ liệu khai trước."""

    def __init__(self, status=None, chats=None, messages=None):
        self.status = status if status is not None else dict(OK_STATUS)
        self.chats = chats or []
        self.messages = messages or {}
        self.calls, self.sent, self.turns, self.events = [], [], [], []
        self._n = 0

    # --- phần broker ---
    def lark_user_status(self, subject):
        return dict(self.status, subject=subject)

    def lark_user_call(self, subject, method, path, body=None):
        self.calls.append((method, path, body))
        if method == "POST" and "/messages?" in path:
            self._n += 1
            self.sent.append((json.loads(body["content"])["text"], body["receive_id"]))
            return {"message_id": f"om_sent_{self._n}"}, None
        if "/chats" in path:
            return {"items": self.chats, "has_more": False}, None
        if "/messages?" in path:
            cid = path.split("container_id=")[1].split("&")[0]
            return {"items": self.messages.get(cid, [])}, None
        return {}, None

    # --- phần platform mà handle() dùng ---
    def context(self, sid, user_ref="", q="", env=None, k=0):
        return {"n_turns": 3, "model": None, "knowledge": [], "user_facts": [],
                "recent_turns": [], "rolling_summary": ""}

    def add_turn(self, sid, role, text, user_ref=None, channel=None):
        self.turns.append((sid, role, text))

    def event(self, jid, kind, data=None):
        self.events.append((jid, kind))

    def add_fact(self, *a, **k):
        return {}

    def facts(self, *a, **k):
        return []

    def lark_send(self, *a, **k):
        return True

    def model_auth_lease(self):
        return {}


def msg(mid, text, sender="ou_nguoi", ts=None):
    return {"message_id": mid, "msg_type": "text",
            "create_time": str(int((ts or time.time()) * 1000)),
            "sender": {"id": sender},
            "body": {"content": json.dumps({"text": text}, ensure_ascii=False)}}


@pytest.fixture(autouse=True)
def _subject(monkeypatch):
    monkeypatch.setenv("AGENT_LARK_SUBJECT", "ann@x.vn")


# ---------------- điều kiện bật ----------------

def test_reports_missing_scope_precisely(monkeypatch):
    """Hai tầng chặn ở hai chỗ khác nhau — phải nói rõ tầng nào, kèm cách gỡ."""
    pf = PF(status={"connected": True, "scope": "approval:approval:read",
                    "path_prefixes": ["/open-apis/approval/v4/"]})
    ok, why = userchat.available(pf)
    assert ok is False
    assert "im:chat:readonly" in why and "C14" in why


def test_reports_missing_grant_precisely():
    pf = PF(status={"connected": True,
                    "scope": "im:chat:readonly im:message",
                    "path_prefixes": ["/open-apis/approval/v4/"]})
    ok, why = userchat.available(pf)
    assert ok is False and "grant chưa mở" in why and "user/grants" in why


def test_available_when_both_layers_open():
    ok, why = userchat.available(PF())
    assert ok is True and "ann@x.vn" in why


# ---------------- vòng poll ----------------

def test_p2p_message_gets_answered(tmp_path):
    """Chat 1-1: trả lời mọi tin, không cần gọi tên — và đi qua đúng handle()."""
    store, _pf, eng, g, b = make(tmp_path)
    pf = PF(chats=[{"chat_id": "oc_p2p", "chat_mode": "p2p", "chat_type": "p2p"}],
            messages={"oc_p2p": [msg("om_1", "pháp chế phụ trách gì?")]})
    b.pf = pf
    consumer._userchat_message(b, pf.chats[0], pf.messages["oc_p2p"][0])
    assert pf.sent, "phải trả lời trong chat 1-1"
    assert pf.sent[0][1] == "oc_p2p"
    assert [t for t in pf.turns if t[0] == "lark_user:oc_p2p"], "phải ghi vào bộ nhớ"


def test_group_message_without_name_is_silent(tmp_path):
    """Trong nhóm vẫn giữ luật cũ: không gọi tên thì im, nhưng VẪN ghi lượt."""
    store, _pf, eng, g, b = make(tmp_path)
    chat = {"chat_id": "oc_grp", "chat_mode": "group"}
    pf = PF(chats=[chat], messages={"oc_grp": [msg("om_2", "trưa nay ăn gì")]})
    b.pf = pf
    consumer._userchat_message(b, chat, pf.messages["oc_grp"][0])
    assert not pf.sent
    assert [t for t in pf.turns if t[1] == "user"], "vẫn ghi lượt để có ngữ cảnh"


def test_group_message_calling_the_name_is_answered(tmp_path):
    store, _pf, eng, g, b = make(tmp_path)
    chat = {"chat_id": "oc_grp", "chat_mode": "group"}
    pf = PF(chats=[chat], messages={"oc_grp": [msg("om_3", "Ann xem giúp mình quy định này")]})
    b.pf = pf
    consumer._userchat_message(b, chat, pf.messages["oc_grp"][0])
    assert pf.sent


def test_own_reply_is_never_answered_again(tmp_path):
    """Không chặn tin của chính mình thì agent trả lời câu trả lời của nó — lặp vô hạn."""
    store, _pf, eng, g, b = make(tmp_path)
    chat = {"chat_id": "oc_p2p", "chat_type": "p2p", "chat_mode": "p2p"}
    pf = PF(chats=[chat], messages={})
    b.pf = pf
    consumer._userchat_message(b, chat, msg("om_a", "câu hỏi"))
    assert len(pf.sent) == 1
    own_id = "om_sent_1"                      # chính tin agent vừa gửi
    consumer._userchat_message(b, chat, msg(own_id, "câu trả lời của agent"))
    assert len(pf.sent) == 1, "tin của chính mình phải bị bỏ qua"


def test_same_message_processed_once(tmp_path):
    """Poll gối đầu nhau: cùng message_id không được xử lý hai lần."""
    store, _pf, eng, g, b = make(tmp_path)
    chat = {"chat_id": "oc_p2p", "chat_type": "p2p", "chat_mode": "p2p"}
    pf = PF(chats=[chat])
    b.pf = pf
    m = msg("om_dup", "hỏi một lần")
    for _ in range(3):
        consumer._userchat_message(b, chat, m)
    assert len(pf.sent) == 1


def test_non_text_message_is_skipped(tmp_path):
    store, _pf, eng, g, b = make(tmp_path)
    chat = {"chat_id": "oc_p2p", "chat_type": "p2p", "chat_mode": "p2p"}
    pf = PF(chats=[chat])
    b.pf = pf
    consumer._userchat_message(b, chat, {"message_id": "om_img", "msg_type": "image",
                                         "create_time": "0", "sender": {"id": "ou_x"}})
    assert not pf.sent


def test_send_uses_chat_id_receive_type():
    """`receive_id_type=chat_id` — gửi sai kiểu thì Lark nhận nhưng vào sai chỗ."""
    pf = PF()
    mid, err = userchat.send_text(pf, "oc_abc", "xin chào")
    assert err is None and mid == "om_sent_1"
    method, path, body = pf.calls[-1]
    assert method == "POST" and "receive_id_type=chat_id" in path
    assert body["receive_id"] == "oc_abc" and body["msg_type"] == "text"


def test_list_chats_includes_p2p():
    """Khác tenant token: user token trả về CẢ chat 1-1 — đây là lý do poll chạy được."""
    pf = PF(chats=[{"chat_id": "oc_g", "chat_mode": "group"},
                   {"chat_id": "oc_p", "chat_mode": "p2p", "chat_type": "p2p"}])
    chats, err = userchat.list_chats(pf)
    assert err is None and len(chats) == 2
    assert [userchat.is_group_chat(c) for c in chats] == [True, False]
