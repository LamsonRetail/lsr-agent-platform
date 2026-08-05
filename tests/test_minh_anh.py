"""Test cho Meeting Agent Minh Anh: share dictionary + biên bản họp."""

from __future__ import annotations

from rating_agent.meeting import (
    MeetingMinutes,
    MeetingTask,
    MinutesStatus,
    build_dictionary_resource,
    share_dictionary_to,
)
from rating_agent.resources import ResourceIndex


def test_share_dictionary_to_new_agent_indexes_it():
    idx = ResourceIndex()
    res = share_dictionary_to(idx, "AG-NEW", shared_at="2026-08-05")
    assert res.agent_id == "AG-NEW"
    assert res.folder == "meeting-notes"
    # Agent mới tra được từ điển meeting-notes của mình.
    hits = idx.search(agent_id="AG-NEW", folder="meeting-notes")
    assert len(hits) == 1 and hits[0].title == "Meeting Notes Dictionary"


def test_dictionary_resource_is_searchable():
    res = build_dictionary_resource("AG-X")
    assert "meeting-notes" in res.tags
    assert "meeting" in res.haystack()


def test_minutes_lifecycle_and_task():
    m = MeetingMinutes(
        meeting_id="M-100", title="Họp Sprint 32", owner="Nguyễn An",
        key_points=["Chốt mục tiêu Q3", "Giao KPI cho Sales"],
        decisions=["Tăng ngân sách ads 10%"],
        tasks=[MeetingTask(title="Cập nhật plan Q3", assignee="Trần Bình", due="2026-08-08")],
    )
    assert m.status == MinutesStatus.DRAFT
    m.request_confirm()
    assert m.status == MinutesStatus.AWAITING_CONFIRM
    m.confirm()
    assert m.status == MinutesStatus.CONFIRMED


def test_confirmed_minutes_goes_to_meeting_notes_index():
    idx = ResourceIndex()
    m = MeetingMinutes(meeting_id="M-100", title="Họp Sprint 32",
                       key_points=["Chốt mục tiêu Q3"])
    m.confirm()
    idx.add(m.as_resource(shared_at="2026-08-05"))
    hits = idx.search("sprint", folder="meeting-notes")
    assert hits and hits[0].resource_id == "minutes::M-100"
