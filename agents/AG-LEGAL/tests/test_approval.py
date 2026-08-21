"""S5 qua Lark Approval — broker C8 (user token do platform giữ, agent không thấy)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("NLM_NOTEBOOK_KB_ID", "nb-test")

import consumer
from legalkb import approval, flows, signing
from tests.test_consumer import make


class FakePF:
    """Platform giả: ghi lại lời gọi broker + tin gửi đi."""

    def __init__(self, status=None, calls=None):
        self._status = status or {"connected": True, "subject": "ann@x.vn",
                                  "refresh_days_left": 6,
                                  "path_prefixes": ["/open-apis/approval/v4/"]}
        self._calls = calls or {}
        self.sent = []
        self.seen = []

    def lark_user_status(self, subject):
        return dict(self._status, subject=subject)

    def lark_user_call(self, subject, method, path, body=None):
        self.seen.append((method, path, body))
        for key, val in self._calls.items():
            if key in path:
                return val
        return None, "không khai trong test"

    def lark_send(self, to, text=None, markdown=None, to_type="chat_id", app_id=None):
        self.sent.append((to, markdown or text))
        return True


@pytest.fixture(autouse=True)
def _subject(monkeypatch):
    monkeypatch.setenv(approval.SUBJECT_ENV, "ann@x.vn")


def test_no_subject_configured_is_reported_not_crashed(monkeypatch):
    """Thiếu cấu hình phải nói rõ, không được ném lỗi giữa việc."""
    monkeypatch.delenv(approval.SUBJECT_ENV, raising=False)
    st = approval.status(FakePF())
    assert st["connected"] is False and approval.SUBJECT_ENV in st["reason"]
    assert "chưa nối" in approval.summarise_status(st)


def test_pending_tasks_uses_topic_1():
    """`topic` là BẮT BUỘC — thiếu thì Lark trả 99992402 (options: 1,2,17,18)."""
    pf = FakePF(calls={"/tasks": ({"tasks": [{"id": "t1"}]}, None)})
    tasks, err = approval.pending_tasks(pf)
    assert err is None and [t["id"] for t in tasks] == ["t1"]
    method, path, _ = pf.seen[0]
    assert method == "GET" and "topic=1" in path and "user_id_type=open_id" in path


def test_instance_read_explains_the_tenant_token_gap():
    """Đo 20/08: `instances/{code}` trả 99991668 với user token → phải nói cần C5, chứ
    không được trả rỗng làm như hồ sơ không có gì."""
    pf = FakePF(calls={"/instances/": (None, "Lark code=99991668 user access token not support")})
    data, err = approval.instance(pf, "abc")
    assert data is None
    assert "TENANT token" in err and "C5" in err


def test_refresh_expiry_warning_shows_up():
    st = {"connected": True, "subject": "ann@x.vn", "refresh_days_left": 1,
          "path_prefixes": ["/open-apis/approval/v4/"]}
    assert "sắp hết hạn" in approval.summarise_status(st)
    st["refresh_days_left"] = 6
    assert "sắp hết hạn" not in approval.summarise_status(st)


# ==================== vòng lặp trong consumer ====================

def test_pending_task_reported_once_only(tmp_path, monkeypatch):
    """`topic=1` trả lại ĐÚNG việc đó ở mọi lần poll cho tới khi người xử lý xong —
    không khoá theo task_id thì group bị spam mỗi 5 phút."""
    store, _pf, eng, g, b = make(tmp_path)
    pf = FakePF(calls={"/instances/": (None, "Lark code=99991668 user access token not support")})
    b.pf = pf
    task = {"id": "t1", "instance_code": "inst-1", "title": "HĐ dịch vụ ABC"}
    for _ in range(3):
        consumer._handle_pending_task(b, task)
    assert len(pf.sent) == 1, "chỉ được báo một lần"
    assert "Hồ sơ trình ký mới" in pf.sent[0][1]
    assert "inst-1" in pf.sent[0][1]


def test_unreadable_dossier_still_gets_reported(tmp_path):
    """Chưa đọc được nội dung KHÔNG phải lý do im lặng: một hồ sơ đã tới mà không ai biết
    còn tệ hơn một tin báo thiếu."""
    store, _pf, eng, g, b = make(tmp_path)
    pf = FakePF(calls={"/instances/": (None, "Lark code=99991668 user access token not support")})
    b.pf = pf
    consumer._handle_pending_task(b, {"id": "t9", "instance_code": "i9", "title": "HĐ X"})
    msg = pf.sent[0][1]
    assert "Chưa đọc được nội dung" in msg and "Pháp chế mở trực tiếp" in msg


def test_task_without_id_is_skipped(tmp_path):
    store, _pf, eng, g, b = make(tmp_path)
    pf = FakePF()
    b.pf = pf
    consumer._handle_pending_task(b, {"instance_code": "i1"})
    assert pf.sent == []


# ==================== s5_from_instance: đường vào THẬT ====================

def _instance_form(name, desc, atts=None):
    import json
    items = [{"id": signing.APPROVAL_FORM["contract_name"], "value": name},
             {"id": signing.APPROVAL_FORM["description"], "value": desc}]
    if atts:
        items.append({"id": signing.APPROVAL_FORM["attachments"], "value": atts})
    return {"form": json.dumps(items, ensure_ascii=False)}


def test_s5_from_instance_reviews_using_step3(tmp_path, monkeypatch):
    store, _pf, eng, g, b = make(tmp_path)
    b.pf = FakePF()
    monkeypatch.setattr(flows.brain, "call_claude", lambda *a, **k:
                        '{"missing_docs": ["Giấy ĐKKD đối tác"], "findings": []}')
    out = flows.s5_from_instance(b, "inst-7", "HĐ mua bán ABC",
                                _instance_form("HĐ mua bán ABC", "mua 100 kệ hàng"))
    assert "Hồ sơ trình ký mới" in out and "inst-7" in out
    assert store.one("SELECT step FROM signing_dossiers WHERE instance_code='inst-7'")["step"] == "step3"


def test_s5_from_instance_says_when_attachment_unread(tmp_path, monkeypatch):
    """Rà soát trên mô tả trong form là chấp nhận được — nhưng phải NÓI là chưa đọc file."""
    store, _pf, eng, g, b = make(tmp_path)
    b.pf = FakePF()
    monkeypatch.setattr(flows.brain, "call_claude", lambda *a, **k:
                        '{"missing_docs": [], "findings": []}')
    out = flows.s5_from_instance(b, "inst-8", "HĐ X",
                                _instance_form("HĐ X", "nội dung", atts="file.pdf"))
    assert "chưa đọc được nội dung file" in out


def test_s5_from_instance_refuses_when_form_is_empty(tmp_path, monkeypatch):
    """Form rỗng thì KHÔNG rà soát — không được sinh báo cáo từ không có gì."""
    store, _pf, eng, g, b = make(tmp_path)
    b.pf = FakePF()
    monkeypatch.setattr(flows.brain, "call_claude",
                        lambda *a, **k: pytest.fail("không được gọi model khi form rỗng"))
    out = flows.s5_from_instance(b, "inst-9", "HĐ Y", {"form": "[]"})
    assert "chưa rà soát được" in out
