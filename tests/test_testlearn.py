"""Test cho Test & Learn: lifecycle review, chấm điểm, agent/người, fail→training."""

from __future__ import annotations

import pytest

from rating_agent.testlearn import (
    Answer,
    NotTakeableError,
    Question,
    TakerType,
    Test,
    TestStatus,
    TrainingMaterial,
    approve,
    grade,
    import_training_file,
    make_attempt,
    new_auto_draft,
    recommend_training,
    submit_for_review,
)


def _test(status=TestStatus.ACTIVE, threshold=0.8):
    return Test(
        test_id="T1", title="Kiến thức đơn hàng", status=status, pass_threshold=threshold,
        questions=[
            Question(question_id="q1", prompt="Trạng thái đơn đã giao?",
                     expected="delivered", assertion_type="contains", skill_id="order"),
            Question(question_id="q2", prompt="2+2=?", expected="4",
                     assertion_type="exact", skill_id="math"),
        ],
    )


# ---- lifecycle ----
def test_auto_draft_needs_review_before_active():
    t = new_auto_draft("T9", "Auto", [Question(question_id="q", prompt="p", expected="x")])
    assert t.status == TestStatus.DRAFT and t.source == "auto"
    assert not t.is_takeable()


def test_review_flow_requires_human_reviewer():
    t = _test(status=TestStatus.DRAFT)
    submit_for_review(t)
    assert t.status == TestStatus.IN_REVIEW
    with pytest.raises(ValueError):
        approve(t, "")            # thiếu reviewer
    approve(t, "hr.lan")
    assert t.status == TestStatus.ACTIVE and t.reviewed_by == "hr.lan"


def test_cannot_take_before_active():
    t = _test(status=TestStatus.DRAFT)
    with pytest.raises(NotTakeableError):
        grade(t, [Answer(question_id="q1", response="delivered")])


# ---- chấm điểm ----
def test_grade_pass_and_fail():
    t = _test()
    ok = grade(t, [Answer(question_id="q1", response="order is delivered"),
                   Answer(question_id="q2", response="4")])
    assert ok == (1.0, True, ok[2])
    fail = grade(t, [Answer(question_id="q1", response="delivered"),
                     Answer(question_id="q2", response="5")])
    assert fail[0] == 0.5 and fail[1] is False


# ---- agent vs người: cùng cơ chế ----
def test_agent_and_human_same_grading():
    t = _test()
    ans = [Answer(question_id="q1", response="delivered"), Answer(question_id="q2", response="4")]
    a = make_attempt(t, TakerType.AGENT, "AG-ORDER-BOT", ans, attempt_id="at1")
    h = make_attempt(t, TakerType.HUMAN, "nv.binh", ans, attempt_id="at2")
    assert a.passed and h.passed
    assert a.taker_type == TakerType.AGENT and h.taker_type == TakerType.HUMAN


# ---- training ----
def test_import_training_txt_to_markdown(tmp_path):
    f = tmp_path / "quy_trinh_don_hang.txt"
    f.write_text("Bước 1: kiểm tra kho.\nBước 2: xác nhận đơn.", encoding="utf-8")
    m = import_training_file(f, material_id="M1", tags=["order"])
    assert m.md_content.startswith("# quy trinh don hang")
    assert "Bước 1" in m.md_content and m.provided_by == "HR"


def test_recommend_training_on_fail_matches_skill():
    t = _test()  # skills: order, math
    mats = [
        TrainingMaterial(material_id="M1", title="Đơn hàng", md_content="...", tags=["order"]),
        TrainingMaterial(material_id="M2", title="Marketing", md_content="...", tags=["ads"]),
    ]
    rec = recommend_training(t, mats)
    assert [m.material_id for m in rec] == ["M1"]
