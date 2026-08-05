"""Test cho MinhAnhBot (mock LarkClient) — gửi tin, confirm-gate, event handling."""

from __future__ import annotations

import json

import pytest

from rating_agent.meeting import (
    MeetingMinutes,
    MeetingTask,
    MinhAnhBot,
    MinutesStatus,
)
from rating_agent.resources import ResourceIndex


class FakeClient:
    def __init__(self):
        self.posts = []
        self.gets = []

    def post(self, path, *, json_body=None):
        self.posts.append((path, json_body))
        return {"ok": True, "path": path}

    def get(self, path, *, params=None):
        self.gets.append(path)
        return {"items": [{"chat_id": "oc_1"}]}


def test_send_text_builds_lark_payload():
    c = FakeClient()
    MinhAnhBot(c).send_text("oc_1", "xin chào", receive_id_type="chat_id")
    path, body = c.posts[0]
    assert path == "/im/v1/messages?receive_id_type=chat_id"
    assert body["receive_id"] == "oc_1" and body["msg_type"] == "text"
    assert json.loads(body["content"])["text"] == "xin chào"


def test_ask_confirm_sets_awaiting_and_sends():
    c = FakeClient()
    m = MeetingMinutes(meeting_id="M1", title="Họp", key_points=["a"],
                       tasks=[MeetingTask(title="làm X")])
    MinhAnhBot(c).ask_confirm("ou_owner", m, receive_id_type="open_id")
    assert m.status == MinutesStatus.AWAITING_CONFIRM
    assert c.posts[0][0].endswith("open_id")
    assert "confirm" in json.loads(c.posts[0][1]["content"])["text"].lower()


def test_no_task_before_confirm():
    m = MeetingMinutes(meeting_id="M1", tasks=[MeetingTask(title="X")])
    with pytest.raises(RuntimeError):
        MinhAnhBot(FakeClient()).on_confirm(m)  # chưa ask_confirm


def test_on_confirm_creates_tasks_and_indexes():
    c = FakeClient()
    idx = ResourceIndex()
    m = MeetingMinutes(meeting_id="M1", title="Họp Sprint",
                       key_points=["chốt Q3"], tasks=[MeetingTask(title="X"), MeetingTask(title="Y")])
    bot = MinhAnhBot(c, index=idx)
    bot.ask_confirm("ou_owner", m)
    created = bot.on_confirm(m, minutes_uri="lark://doc/1")
    assert m.status == MinutesStatus.CONFIRMED
    assert len(created) == 2
    task_posts = [p for p in c.posts if p[0] == "/task/v2/tasks"]
    assert len(task_posts) == 2
    # biên bản đã vào meeting-notes index
    assert idx.search("sprint", folder="meeting-notes")


def test_handle_event_url_verification():
    out = MinhAnhBot.handle_event({"type": "url_verification", "challenge": "abc"})
    assert out == {"challenge": "abc"}


def test_handle_event_message():
    body = {
        "header": {"event_type": "im.message.receive_v1"},
        "event": {"message": {"content": json.dumps({"text": "confirm"})}},
    }
    out = MinhAnhBot.handle_event(body)
    assert out["action"] == "message" and out["text"] == "confirm"
