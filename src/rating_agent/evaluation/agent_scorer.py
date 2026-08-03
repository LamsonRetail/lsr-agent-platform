"""Chấm điểm AGENT theo skill / usage / kết quả + khuyến nghị governance.

- skill_score: TB có trọng số (theo số test) của pass_rate từng skill.
- usage_score: chuẩn hoá tương đối trong nhóm (invocations, unique_users).
- result_score: kết hợp success_rate, user_rating, latency (nghịch).
- status_recommendation: áp chính sách deactivate_policy lên chuỗi test gần nhất.
"""

from __future__ import annotations

from typing import Any

from .criteria import grade_for, normalize, weighted_mean
from .models import (
    AgentEvaluation,
    AgentMetrics,
    RankedItem,
    StatusRecommendation,
)


class AgentScorer:
    """Chấm điểm agent dựa trên cấu hình nhánh ``agent``."""

    def __init__(self, config: dict[str, Any]):
        agent_cfg = config.get("agent", {})
        self._weights = agent_cfg.get("weights", {})
        self._result_components = agent_cfg.get("result_components", {})
        self._grade_bands = agent_cfg.get("grade_bands", [])
        self._policy = agent_cfg.get("deactivate_policy", {})

    # -- Các thành phần điểm -------------------------------------------
    def _skill_score(self, agent: AgentMetrics) -> float:
        pairs = [
            (s.pass_rate * 100.0, float(s.tests_total)) for s in agent.skill_results
        ]
        return round(weighted_mean(pairs), 2)

    def _result_score(self, agent: AgentMetrics) -> float:
        # success_rate (0..1), user_rating (1..5), latency (nghịch, chuẩn hoá thô)
        success = agent.success_rate * 100.0
        rating = (agent.user_rating / 5.0) * 100.0
        # Latency: giả định 0ms=100đ, >=5000ms=0đ (chuẩn hoá tuyệt đối đơn giản).
        latency = normalize(agent.avg_latency_ms, 0.0, 5000.0, higher_is_better=False)
        return round(
            weighted_mean(
                [
                    (success, float(self._result_components.get("success_rate", 0.5))),
                    (rating, float(self._result_components.get("user_rating", 0.3))),
                    (latency, float(self._result_components.get("latency", 0.2))),
                ]
            ),
            2,
        )

    def _usage_ranges(self, cohort: list[AgentMetrics]) -> dict[str, tuple[float, float]]:
        inv = [a.invocations for a in cohort] or [0]
        usr = [a.unique_users for a in cohort] or [0]
        return {
            "invocations": (float(min(inv)), float(max(inv))),
            "unique_users": (float(min(usr)), float(max(usr))),
        }

    def _usage_score(self, agent: AgentMetrics, ranges: dict[str, tuple[float, float]]) -> float:
        inv = normalize(agent.invocations, *ranges["invocations"])
        usr = normalize(agent.unique_users, *ranges["unique_users"])
        return round((inv + usr) / 2.0, 2)

    # -- Governance -----------------------------------------------------
    def recommend_status(self, agent: AgentMetrics) -> tuple[StatusRecommendation, str]:
        """Áp chính sách deactivate lên chuỗi kết quả test gần nhất."""

        mode = self._policy.get("mode", "consecutive_fail")
        results = agent.recent_test_results

        if mode == "single_fail":
            if results and results[-1] is False:
                return StatusRecommendation.DEACTIVATE, "Fail bài test gần nhất"
        elif mode == "pass_rate":
            threshold = float(self._policy.get("pass_rate_threshold", 0.8))
            if agent.test_pass_rate < threshold:
                return (
                    StatusRecommendation.DEACTIVATE,
                    f"test_pass_rate {agent.test_pass_rate:.0%} < {threshold:.0%}",
                )
        else:  # consecutive_fail (mặc định)
            n = int(self._policy.get("consecutive_fail_threshold", 2))
            if len(results) >= n and all(r is False for r in results[-n:]):
                return (
                    StatusRecommendation.DEACTIVATE,
                    f"Fail {n} bài test liên tiếp",
                )

        # Không tới ngưỡng deactivate → xét cảnh báo "watch"
        watch = float(self._policy.get("watch_pass_rate", 0.9))
        if agent.test_pass_rate < watch:
            return (
                StatusRecommendation.WATCH,
                f"test_pass_rate {agent.test_pass_rate:.0%} < {watch:.0%}",
            )
        return StatusRecommendation.KEEP_ACTIVE, ""

    # -- Chấm cả nhóm ---------------------------------------------------
    def score_all(self, cohort: list[AgentMetrics]) -> list[AgentEvaluation]:
        ranges = self._usage_ranges(cohort)
        return [self._score_one(a, ranges) for a in cohort]

    def _score_one(
        self, agent: AgentMetrics, ranges: dict[str, tuple[float, float]]
    ) -> AgentEvaluation:
        skill = self._skill_score(agent)
        result = self._result_score(agent)
        usage = self._usage_score(agent, ranges)
        total = round(
            weighted_mean(
                [
                    (skill, float(self._weights.get("skill_score", 0.4))),
                    (result, float(self._weights.get("result_score", 0.3))),
                    (usage, float(self._weights.get("usage_score", 0.3))),
                ]
            ),
            2,
        )
        recommendation, note = self.recommend_status(agent)
        return AgentEvaluation(
            agent_id=agent.agent_id,
            agent_name=agent.agent_name,
            period=agent.period,
            skill_score=skill,
            usage_score=usage,
            result_score=result,
            test_pass_rate=round(agent.test_pass_rate * 100.0, 2),
            total_score=total,
            grade=grade_for(total, self._grade_bands),
            status_recommendation=recommendation,
            note=note,
        )


def rank_agents(evaluations: list[AgentEvaluation]) -> list[RankedItem]:
    ordered = sorted(evaluations, key=lambda e: e.total_score, reverse=True)
    return [
        RankedItem(
            rank=i + 1,
            item_id=e.agent_id,
            name=e.agent_name,
            total_score=e.total_score,
            grade=e.grade,
            extra=e.status_recommendation.value,
        )
        for i, e in enumerate(ordered)
    ]
