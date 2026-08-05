"""Data model cho Test & Learn.

- Một **Test** gồm nhiều **Question** (test case). Test có vòng đời review:
  draft → in_review → active (chỉ ACTIVE mới được làm) → archived.
- **Attempt**: một lượt làm bài của **agent hoặc người** (cùng cơ chế).
- **TrainingMaterial**: nội dung training (do HR cung cấp, import từ file → markdown).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class TestStatus(str, Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    ACTIVE = "active"
    ARCHIVED = "archived"


class TakerType(str, Enum):
    AGENT = "agent"
    HUMAN = "human"


class Question(BaseModel):
    """Một test case trong bài test."""

    question_id: str
    prompt: str
    expected: str
    assertion_type: str = "contains"  # exact|contains|regex|numeric_tolerance|semantic
    weight: float = 1.0
    tolerance: float = 0.0
    skill_id: str = ""  # để gợi ý training theo kỹ năng
    tags: list[str] = Field(default_factory=list)


class Test(BaseModel):
    """Bài test (nhiều question) + trạng thái review."""

    test_id: str
    title: str = ""
    description: str = ""
    questions: list[Question] = Field(default_factory=list)
    status: TestStatus = TestStatus.DRAFT
    source: str = "manual"  # manual | auto (sinh tự động, vẫn phải review)
    created_by: str = ""
    reviewed_by: str = ""
    pass_threshold: float = 0.8  # tỉ lệ điểm (0..1) để pass

    def is_takeable(self) -> bool:
        return self.status == TestStatus.ACTIVE

    @property
    def total_weight(self) -> float:
        return sum(q.weight for q in self.questions) or 1.0

    @property
    def topic_tags(self) -> set[str]:
        tags: set[str] = set()
        for q in self.questions:
            tags.update(q.tags)
            if q.skill_id:
                tags.add(q.skill_id)
        return tags


class Answer(BaseModel):
    question_id: str
    response: str


class Attempt(BaseModel):
    """Một lượt làm bài (agent hoặc người)."""

    attempt_id: str
    test_id: str
    taker_type: TakerType
    taker_id: str
    answers: list[Answer] = Field(default_factory=list)
    score: float = 0.0  # 0..1
    passed: bool = False
    detail: list[dict] = Field(default_factory=list)
    at: str = ""


class TrainingMaterial(BaseModel):
    """Tài liệu training do HR cung cấp (đã chuyển sang markdown)."""

    material_id: str
    title: str
    md_content: str
    source_file: str = ""
    tags: list[str] = Field(default_factory=list)
    provided_by: str = "HR"
    created_at: str = ""
