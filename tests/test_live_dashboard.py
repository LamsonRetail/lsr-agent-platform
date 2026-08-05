"""Test render dashboard live (pure — không network)."""

from __future__ import annotations

from rating_agent.reporting.live_dashboard import render_html


def test_render_live_with_data():
    agents = [{"agent_id": "AG-1", "name": "Bot 1", "squad": "SQ", "owner": "T", "status": "active"}]
    stats = [{"agent_id": "AG-1", "total_tokens": 465, "runs": 2}]
    tests = [{"test_id": "TL-1", "title": "KT", "status": "active", "source": "auto",
              "num_questions": 2, "reviewed_by": "hr.lan"}]
    attempts = [{"taker_id": "AG-1", "taker_type": "agent", "test_id": "TL-1",
                 "score": 0.5, "passed": False}]
    training = [{"material_id": "M1", "title": "Đơn hàng", "tags": ["order"],
                 "provided_by": "HR", "source_file": "x.md"}]
    html = render_html(agents, stats, tests, attempts, training)
    assert "LIVE" in html
    assert "Bot 1" in html and "465" in html          # token thật
    assert "KT" in html and "hr.lan" in html
    assert "fail" in html                              # attempt trượt


def test_render_live_empty_safe():
    html = render_html([], [], [], [], [])
    assert "chưa có agent" in html and "chưa có bài test" in html
