"""Test cho squad scorer và agent scorer."""

from __future__ import annotations

from pathlib import Path

import pytest

from rating_agent.config import load_scoring_config
from rating_agent.evaluation import (
    AgentScorer,
    SquadScorer,
    StatusRecommendation,
    rank_agents,
    rank_squads,
)
from rating_agent.evaluation.criteria import normalize, weighted_mean
from rating_agent.pipeline import build_sample_agents, build_sample_squads

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "scoring_config.yaml"


@pytest.fixture()
def config() -> dict:
    return load_scoring_config(CONFIG_PATH)


# ---- helpers ----
def test_normalize_bounds():
    assert normalize(10, 0, 10) == 100.0
    assert normalize(0, 0, 10) == 0.0
    assert normalize(0, 0, 10, higher_is_better=False) == 100.0
    assert normalize(5, 5, 5) == 50.0  # khoảng rỗng -> trung tính


def test_weighted_mean_normalizes_weights():
    assert weighted_mean([(100, 1), (0, 1)]) == 50.0
    assert weighted_mean([]) == 0.0


# ---- squad ----
def test_squad_scores_within_bounds(config: dict):
    scorer = SquadScorer(config)
    for ev in scorer.score_all(build_sample_squads()):
        assert 0.0 <= ev.total_score <= 100.0
        assert ev.grade


def test_squad_overachievement_capped(config: dict):
    # SQ-SALES có KR vượt chỉ tiêu (1150/1000) -> objective_score <= 100.
    scorer = SquadScorer(config)
    evals = {e.squad_id: e for e in scorer.score_all(build_sample_squads())}
    assert evals["SQ-SALES"].objective_score <= 100.0


def test_squad_ranking_descending(config: dict):
    evals = SquadScorer(config).score_all(build_sample_squads())
    ranking = rank_squads(evals)
    scores = [r.total_score for r in ranking]
    assert scores == sorted(scores, reverse=True)


# ---- agent ----
def test_agent_scores_within_bounds(config: dict):
    for ev in AgentScorer(config).score_all(build_sample_agents()):
        assert 0.0 <= ev.total_score <= 100.0
        assert ev.grade


def test_failing_agent_recommended_deactivate(config: dict):
    # AG-CHAT-HELPER fail 2 lần liên tiếp -> deactivate (policy mặc định N=2).
    evals = {e.agent_id: e for e in AgentScorer(config).score_all(build_sample_agents())}
    assert evals["AG-CHAT-HELPER"].status_recommendation is StatusRecommendation.DEACTIVATE


def test_healthy_agent_kept_active(config: dict):
    evals = {e.agent_id: e for e in AgentScorer(config).score_all(build_sample_agents())}
    assert evals["AG-ORDER-BOT"].status_recommendation is StatusRecommendation.KEEP_ACTIVE


def test_agent_leaderboard_top_is_best(config: dict):
    evals = AgentScorer(config).score_all(build_sample_agents())
    ranking = rank_agents(evals)
    assert ranking[0].item_id == "AG-ORDER-BOT"
