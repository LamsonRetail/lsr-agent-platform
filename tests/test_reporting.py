"""Smoke test cho reporting: dashboard sinh ra hợp lệ và đủ 6 màn hình."""

from __future__ import annotations

from rating_agent.reporting import render_html


def test_render_html_contains_all_screens():
    html = render_html()
    for screen_id in ("scoreboard", "squad-detail", "registry",
                      "agent-detail", "test-dash", "leaderboard"):
        assert f"screen-{screen_id}" in html


def test_render_html_is_self_contained():
    html = render_html()
    assert html.lstrip().startswith("<!doctype html>")
    # Không phụ thuộc tài nguyên ngoài.
    assert "http://" not in html.replace("https://lark.example", "")  # chỉ link mẫu nội bộ
    assert "<script" in html and "<style" in html


def test_render_html_reflects_deactivate_case():
    # Agent fail 2 lần liên tiếp phải xuất hiện khuyến nghị Deactivate trên dashboard.
    assert "Deactivate" in render_html()
