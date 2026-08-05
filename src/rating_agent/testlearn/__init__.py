"""Test & Learn: bài test (review→active), làm bài (agent/người), fail→training."""

from .grader import (
    NotTakeableError,
    approve,
    archive,
    grade,
    make_attempt,
    new_auto_draft,
    recommend_training,
    submit_for_review,
)
from .models import (
    Answer,
    Attempt,
    Question,
    TakerType,
    Test,
    TestStatus,
    TrainingMaterial,
)
from .generator import (
    build_draft_test,
    generate_questions,
    heuristic_questions,
    parse_llm_questions,
)
from .training import import_training_file, to_markdown

__all__ = [
    # models
    "Test", "TestStatus", "Question", "Answer", "Attempt", "TakerType",
    "TrainingMaterial",
    # grader/lifecycle
    "grade", "make_attempt", "NotTakeableError",
    "submit_for_review", "approve", "archive", "new_auto_draft",
    "recommend_training",
    # training
    "to_markdown", "import_training_file",
    # generator (b)
    "build_draft_test", "generate_questions", "heuristic_questions", "parse_llm_questions",
]
