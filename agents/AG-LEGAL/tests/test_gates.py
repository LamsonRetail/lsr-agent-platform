"""Test khung gate + lệnh duyệt trong group (PLAN §2.5, §4) — offline."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("NLM_NOTEBOOK_KB_ID", "nb-test")

import consumer
from legalkb.gates import GATE, OBSERVE, Gates, parse_command
from legalkb.store import SourceStore
from tests.test_consumer import FakeEngine, FakePlatform

GROUP = consumer.GROUP_CHAT_ID


def make(tmp_path, sla_hours=1):
    store = SourceStore(str(tmp_path / "g.db"))
    pf = FakePlatform()
    g = Gates(store, pf, GROUP, sla_hours=sla_hours)
    store.write("INSERT INTO legal_roles (email, role, contract_type, open_id, name, active)"
                " VALUES ('thint@hapas.vn','approver',NULL,'ou_thint','Thi',1)")
    return store, pf, g


# ---------------- parser ----------------

def test_parse_basic_commands():
    assert parse_command("#12 duyệt") == (12, "approve", "")
    assert parse_command("#12 duyet") == (12, "approve", "")
    assert parse_command("#7 sửa: thiếu điều khoản phạt") == (7, "changes", "thiếu điều khoản phạt")
    assert parse_command("#7 huỷ: sai pháp nhân") == (7, "reject", "sai pháp nhân")
    assert parse_command("#3 tham gia") == (3, "join", "")
    assert parse_command("#3 trả lại") == (3, "release", "")
    assert parse_command("#3 nhắn: anh chờ em xem lại") == (3, "relay", "anh chờ em xem lại")
    assert parse_command("#ds") == (None, "list", "")


def test_parse_ignores_normal_chat():
    for t in ["trưa nay ăn gì", "", "#", "#abc duyệt", "duyệt #12", "12 duyệt",
              "#12 xoá hết dữ liệu"]:
        assert parse_command(t) is None, t


def test_parse_tolerates_spacing_and_case():
    assert parse_command("  # 12   DUYỆT  ") == (12, "approve", "")
    assert parse_command("#12 Sửa:  bỏ mục 3 ") == (12, "changes", "bỏ mục 3")


# ---------------- quyền ----------------

def test_only_roster_can_decide(tmp_path):
    store, pf, g = make(tmp_path)
    gid = g.open("s2_draft", GATE, title="HĐ dịch vụ ABC", payload={"chat_id": "oc_u"})
    job = {"id": 1, "session_id": "x", "channel": "lark",
           "payload": {"text": f"#{gid} duyệt", "chat_id": GROUP,
                       "sender_open_id": "ou_nguoi_la"}}
    out = consumer.handle_group(job, pf, store, g)
    assert "chưa có quyền" in out
    assert g.get(gid)["status"] == "open"          # không đổi trạng thái


def test_approver_can_approve(tmp_path):
    store, pf, g = make(tmp_path)
    gid = g.open("s2_draft", GATE, title="HĐ dịch vụ ABC", payload={"chat_id": "oc_u"})
    job = {"id": 2, "session_id": "x", "channel": "lark",
           "payload": {"text": f"#{gid} duyệt", "chat_id": GROUP,
                       "sender_open_id": "ou_thint"}}
    out = consumer.handle_group(job, pf, store, g)
    assert "DUYỆT" in out
    g2 = g.get(gid)
    assert g2["status"] == "approved" and g2["reviewer"] == "thint@hapas.vn"


def test_changes_requires_reason(tmp_path):
    store, pf, g = make(tmp_path)
    gid = g.open("s2_draft", GATE, payload={"chat_id": "oc_u"})
    job = {"id": 3, "payload": {"text": f"#{gid} sửa", "chat_id": GROUP,
                                "sender_open_id": "ou_thint"}}
    assert "Cần nêu lý do" in consumer.handle_group(job, pf, store, g)
    assert g.get(gid)["status"] == "open"


def test_cannot_decide_twice(tmp_path):
    store, pf, g = make(tmp_path)
    gid = g.open("s2_draft", GATE, payload={"chat_id": "oc_u"})
    for _ in range(2):
        out = consumer.handle_group(
            {"id": 4, "payload": {"text": f"#{gid} duyệt", "chat_id": GROUP,
                                  "sender_open_id": "ou_thint"}}, pf, store, g)
    assert "đã ở trạng thái approved" in out


def test_observe_gate_cannot_be_approved(tmp_path):
    """Card theo dõi S1 không phải việc cần duyệt — tránh nhầm lẫn."""
    store, pf, g = make(tmp_path)
    gid = g.open("s1_answer", OBSERVE, session_id="s", payload={"chat_id": "oc_u"})
    out = consumer.handle_group(
        {"id": 5, "payload": {"text": f"#{gid} duyệt", "chat_id": GROUP,
                              "sender_open_id": "ou_thint"}}, pf, store, g)
    assert "không cần duyệt" in out


def test_unknown_gate_id(tmp_path):
    store, pf, g = make(tmp_path)
    out = consumer.handle_group(
        {"id": 6, "payload": {"text": "#999 duyệt", "chat_id": GROUP,
                              "sender_open_id": "ou_thint"}}, pf, store, g)
    assert "Không thấy việc" in out


# ---------------- takeover ----------------

def test_join_switches_mode_and_tells_requester(tmp_path):
    store, pf, g = make(tmp_path)
    gid = g.open("s1_answer", OBSERVE, session_id="sess-J",
                 payload={"chat_id": "oc_user"})
    pf.sent.clear()
    out = consumer.handle_group(
        {"id": 7, "payload": {"text": f"#{gid} tham gia", "chat_id": GROUP,
                              "sender_open_id": "ou_thint"}}, pf, store, g)
    assert g.mode("sess-J") == "joined" and "tham gia" in out
    assert any(to == "oc_user" and "đã tham gia" in msg for to, msg in pf.sent)


def test_release_returns_to_agent(tmp_path):
    store, pf, g = make(tmp_path)
    gid = g.open("s1_answer", OBSERVE, session_id="sess-R", payload={"chat_id": "oc_user"})
    consumer.handle_group({"id": 8, "payload": {"text": f"#{gid} tham gia",
                                                "chat_id": GROUP,
                                                "sender_open_id": "ou_thint"}}, pf, store, g)
    consumer.handle_group({"id": 9, "payload": {"text": f"#{gid} trả lại",
                                                "chat_id": GROUP,
                                                "sender_open_id": "ou_thint"}}, pf, store, g)
    assert g.mode("sess-R") == "auto"


def test_relay_forwards_to_requester(tmp_path):
    store, pf, g = make(tmp_path)
    gid = g.open("s1_answer", OBSERVE, session_id="s", payload={"chat_id": "oc_user"})
    pf.sent.clear()
    consumer.handle_group({"id": 10, "payload": {"text": f"#{gid} nhắn: em xem lại nhé",
                                                 "chat_id": GROUP,
                                                 "sender_open_id": "ou_thint"}},
                          pf, store, g)
    assert any(to == "oc_user" and "em xem lại nhé" in msg for to, msg in pf.sent)


# ---------------- SLA ----------------

def test_gate_never_auto_approves(tmp_path):
    """Quá hạn thì NHẮC, tuyệt đối không tự thông qua — đây là điểm an toàn cốt lõi."""
    store, pf, g = make(tmp_path, sla_hours=0)
    gid = g.open("s2_draft", GATE, payload={"chat_id": "oc_u"})
    store.write("UPDATE legal_gates SET sla_deadline=? WHERE id=?", (time.time() - 10, gid))
    pf.sent.clear()
    acted = g.sla_tick()
    assert acted == [("reminded", gid)]
    assert g.get(gid)["status"] == "open"
    assert any("không tự động thông qua" in (m or "") for _, m in pf.sent)


def test_observe_auto_passes_so_it_never_blocks(tmp_path):
    store, pf, g = make(tmp_path, sla_hours=0)
    gid = g.open("s1_answer", OBSERVE, session_id="s", payload={})
    store.write("UPDATE legal_gates SET sla_deadline=? WHERE id=?", (time.time() - 10, gid))
    assert g.sla_tick() == [("auto_passed", gid)]
    assert g.get(gid)["status"] == "auto_passed"


def test_reminder_sent_once(tmp_path):
    store, pf, g = make(tmp_path, sla_hours=0)
    gid = g.open("s3_review", GATE, payload={})
    store.write("UPDATE legal_gates SET sla_deadline=? WHERE id=?", (time.time() - 10, gid))
    g.sla_tick()
    assert g.sla_tick() == []          # lần 2 không nhắc lại nữa


# ---------------- danh sách ----------------

def test_list_shows_open_items(tmp_path):
    store, pf, g = make(tmp_path)
    g.open("s2_draft", GATE, payload={})
    g.open("s4_digest", GATE, payload={})
    out = consumer.handle_group({"id": 11, "payload": {"text": "#ds", "chat_id": GROUP,
                                                       "sender_open_id": "ou_thint"}},
                                pf, store, g)
    assert "Bản thảo hợp đồng" in out and "Digest văn bản luật" in out


def test_sync_roles_resolves_open_id(tmp_path):
    store, pf, g = make(tmp_path)
    store.write("INSERT INTO legal_roles (email, role, contract_type, active) "
                "VALUES ('anh@hapas.vn','approver','HĐ dịch vụ',1)")
    assert g.sync_roles() == 1
    assert g.reviewer_by_open_id("ou_anh")["email"] == "anh@hapas.vn"
