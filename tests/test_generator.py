"""Test sinh test tự động (b) + PlatformClient/CollectorClient (mock)."""

from __future__ import annotations

from rating_agent.testlearn import (
    TestStatus,
    build_draft_test,
    generate_questions,
    heuristic_questions,
    parse_llm_questions,
)
from rating_agent import platform_client as pc


# ---- generator ----
def test_heuristic_questions_from_material():
    md = "# Tiêu đề\nĐơn giao thành công gọi là delivered.\nMã đơn có tiền tố A."
    qs = heuristic_questions(md, skill="order", n=2)
    assert len(qs) == 2
    assert all(q.skill_id == "order" and q.prompt and q.expected for q in qs)


def test_parse_llm_questions_json():
    out = 'Đây là đề: [{"prompt":"Trạng thái giao?","expected":"delivered"}] xong.'
    qs = parse_llm_questions(out, skill="order")
    assert len(qs) == 1 and qs[0].expected == "delivered" and qs[0].skill_id == "order"


def test_generate_uses_llm_when_provided():
    called = {}

    def fake_llm(prompt):
        called["prompt"] = prompt
        return '[{"prompt":"2+2?","expected":"4","assertion_type":"exact"}]'

    qs = generate_questions("tài liệu", skill="math", n=1, llm=fake_llm)
    assert qs[0].assertion_type == "exact"
    assert "TÀI LIỆU" in called["prompt"]


def test_build_draft_test_is_draft_auto():
    t = build_draft_test("TL-AUTO", "Auto từ tài liệu", "# H\ndòng nội dung một", skill="order")
    assert t.status == TestStatus.DRAFT and t.source == "auto"
    assert t.created_by == "llm-generator" and len(t.questions) >= 1


# ---- clients ----
class _Resp:
    def __init__(self, p, code=200):
        self._p = p; self.status_code = code

    def raise_for_status(self):
        if self.status_code >= 300:
            raise RuntimeError("http")

    def json(self):
        return self._p


def test_platform_client_review_calls_admin(monkeypatch):
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, json=json, auth=headers.get("Authorization"))
        return _Resp({"status": "active"})

    monkeypatch.setattr(pc.requests, "post", fake_post)
    out = pc.PlatformClient("http://x", "admintok").review_test("TL-1", "hr.lan")
    assert out["status"] == "active"
    assert seen["url"].endswith("/v1/tests/TL-1/review")
    assert seen["json"] == {"reviewed_by": "hr.lan"}
    assert seen["auth"] == "Bearer admintok"


def test_platform_client_list_agents(monkeypatch):
    monkeypatch.setattr(pc.requests, "get",
                        lambda url, params=None, timeout=None: _Resp([{"agent_id": "AG-1"}]))
    assert pc.PlatformClient("http://x").list_agents()[0]["agent_id"] == "AG-1"


def test_collector_token_stats(monkeypatch):
    monkeypatch.setattr(pc.requests, "get",
                        lambda url, params=None, timeout=None: _Resp([{"agent_id": "AG-1", "total_tokens": 300}]))
    assert pc.CollectorClient("http://x").token_stats()[0]["total_tokens"] == 300
