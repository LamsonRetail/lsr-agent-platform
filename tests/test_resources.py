"""Test cho Resource Index (in-memory)."""

from __future__ import annotations

from rating_agent.resources import ResourceIndex, SharedResource


def _r(rid, agent, title, summary="", folder="", tags=None, when="2026-08-01"):
    return SharedResource(
        resource_id=rid, agent_id=agent, kind="link", title=title,
        summary=summary, folder=folder, tags=tags or [], shared_at=when,
    )


def test_add_and_search_keyword():
    idx = ResourceIndex()
    idx.add(_r("R1", "AG-A", "Báo cáo doanh thu Q3", summary="doanh thu sales HN"))
    idx.add(_r("R2", "AG-A", "Quy trình đổi trả", summary="ops"))
    hits = idx.search("doanh thu")
    assert [h.resource_id for h in hits] == ["R1"]


def test_search_and_terms_all_match():
    idx = ResourceIndex()
    idx.add(_r("R1", "AG-A", "Meeting note họp sprint", tags=["meeting", "sprint"]))
    idx.add(_r("R2", "AG-A", "Meeting note họp KH", tags=["meeting", "khach-hang"]))
    assert {h.resource_id for h in idx.search("meeting sprint")} == {"R1"}


def test_filter_agent_and_folder():
    idx = ResourceIndex()
    idx.add(_r("R1", "AG-A", "x", folder="meeting-notes"))
    idx.add(_r("R2", "AG-B", "x", folder="meeting-notes"))
    idx.add(_r("R3", "AG-A", "x", folder="reports"))
    assert {h.resource_id for h in idx.search(agent_id="AG-A")} == {"R1", "R3"}
    assert {h.resource_id for h in idx.search(folder="meeting-notes")} == {"R1", "R2"}
    assert {h.resource_id for h in idx.search(agent_id="AG-A", folder="meeting-notes")} == {"R1"}


def test_add_is_idempotent_by_id():
    idx = ResourceIndex()
    idx.add(_r("R1", "AG-A", "v1"))
    idx.add(_r("R1", "AG-A", "v2"))
    assert len(idx) == 1
    assert idx.search()[0].title == "v2"


def test_empty_query_lists_recent_first():
    idx = ResourceIndex()
    idx.add(_r("R1", "AG-A", "cũ", when="2026-07-01"))
    idx.add(_r("R2", "AG-A", "mới", when="2026-08-05"))
    assert [h.resource_id for h in idx.search()] == ["R2", "R1"]
