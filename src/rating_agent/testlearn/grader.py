"""Chấm điểm bài test + vòng đời review + gợi ý training khi trượt."""

from __future__ import annotations

from ..agent_testing.runner import AssertionType, check_assertion
from .models import (
    Answer,
    Attempt,
    Question,
    TakerType,
    Test,
    TestStatus,
    TrainingMaterial,
)


class NotTakeableError(RuntimeError):
    """Bài test chưa ACTIVE (chưa review xong) thì không được làm."""


# ----------------------- Chấm điểm -----------------------

def grade(test: Test, answers: list[Answer]) -> tuple[float, bool, list[dict]]:
    """Chấm một lượt làm bài. Trả về (score 0..1, passed, chi tiết từng câu)."""

    if not test.is_takeable():
        raise NotTakeableError(
            f"Test {test.test_id} đang {test.status.value}, chưa được làm (cần ACTIVE)."
        )
    by_id = {a.question_id: a.response for a in answers}
    got = 0.0
    detail: list[dict] = []
    for q in test.questions:
        resp = by_id.get(q.question_id, "")
        ok = check_assertion(q.expected, resp, AssertionType(q.assertion_type), q.tolerance)
        if ok:
            got += q.weight
        detail.append({"question_id": q.question_id, "ok": ok, "skill_id": q.skill_id})
    score = round(got / test.total_weight, 4)
    passed = score >= test.pass_threshold
    return score, passed, detail


def make_attempt(
    test: Test,
    taker_type: TakerType,
    taker_id: str,
    answers: list[Answer],
    *,
    attempt_id: str,
    at: str = "",
) -> Attempt:
    score, passed, detail = grade(test, answers)
    return Attempt(
        attempt_id=attempt_id, test_id=test.test_id, taker_type=taker_type,
        taker_id=taker_id, answers=answers, score=score, passed=passed,
        detail=detail, at=at,
    )


# ----------------------- Vòng đời review -----------------------

def submit_for_review(test: Test) -> Test:
    if test.status not in (TestStatus.DRAFT, TestStatus.IN_REVIEW):
        raise ValueError(f"Không thể đưa test {test.status.value} vào review.")
    test.status = TestStatus.IN_REVIEW
    return test


def approve(test: Test, reviewer: str) -> Test:
    """Người review DUYỆT → ACTIVE. Bắt buộc qua bước con người này mới được dùng."""

    if test.status != TestStatus.IN_REVIEW:
        raise ValueError("Chỉ duyệt được test đang in_review.")
    if not reviewer:
        raise ValueError("Cần reviewer (người duyệt).")
    test.reviewed_by = reviewer
    test.status = TestStatus.ACTIVE
    return test


def archive(test: Test) -> Test:
    test.status = TestStatus.ARCHIVED
    return test


def new_auto_draft(
    test_id: str, title: str, questions: list[Question], *, created_by: str = "auto-generator"
) -> Test:
    """Tạo bài test sinh tự động — LUÔN ở DRAFT, phải review mới active."""

    return Test(
        test_id=test_id, title=title, questions=questions,
        status=TestStatus.DRAFT, source="auto", created_by=created_by,
    )


# ----------------------- Gợi ý training khi trượt -----------------------

def recommend_training(test: Test, materials: list[TrainingMaterial]) -> list[TrainingMaterial]:
    """Khi trượt: gợi ý tài liệu training khớp skill/tag của bài test."""

    topics = {t.lower() for t in test.topic_tags}
    if not topics:
        return list(materials)
    hits = [m for m in materials if topics & {t.lower() for t in m.tags}]
    return hits or list(materials)
