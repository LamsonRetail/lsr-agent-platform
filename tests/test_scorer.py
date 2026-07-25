"""Test cho scorer và tiêu chí chấm điểm."""

from __future__ import annotations

from pathlib import Path

import pytest

from rating_agent.config import load_scoring_config
from rating_agent.evaluation import Scorer, rank_employees
from rating_agent.evaluation.criteria import normalize
from rating_agent.pipeline import build_sample_cohort

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "scoring_config.yaml"


@pytest.fixture()
def scorer() -> Scorer:
    return Scorer.from_config(load_scoring_config(CONFIG_PATH))


def test_normalize_higher_is_better():
    assert normalize(10, 0, 10, higher_is_better=True) == 100.0
    assert normalize(0, 0, 10, higher_is_better=True) == 0.0


def test_normalize_lower_is_better():
    # Giá trị nhỏ nhất được điểm cao nhất khi higher_is_better=False.
    assert normalize(0, 0, 10, higher_is_better=False) == 100.0
    assert normalize(10, 0, 10, higher_is_better=False) == 0.0


def test_normalize_equal_range_is_neutral():
    assert normalize(5, 5, 5) == 50.0


def test_score_all_returns_one_eval_per_employee(scorer: Scorer):
    cohort = build_sample_cohort()
    evaluations = scorer.score_all(cohort)
    assert len(evaluations) == len(cohort)


def test_scores_within_bounds(scorer: Scorer):
    for ev in scorer.score_all(build_sample_cohort()):
        assert 0.0 <= ev.total_score <= 100.0
        assert ev.grade  # có nhãn xếp loại


def test_top_performer_ranks_first(scorer: Scorer):
    # E001 có chỉ số tốt nhất ở mọi trục → phải đứng đầu.
    evaluations = scorer.score_all(build_sample_cohort())
    ranking = rank_employees(evaluations)
    assert ranking[0].employee_id == "E001"
    assert ranking[0].rank == 1
    # Điểm giảm dần theo hạng.
    scores = [r.total_score for r in ranking]
    assert scores == sorted(scores, reverse=True)
