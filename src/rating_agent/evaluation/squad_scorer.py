"""Chấm điểm SQUAD theo hiệu quả mục tiêu (Key Result achievement + tiến độ)."""

from __future__ import annotations

from typing import Any

from .criteria import grade_for, weighted_mean
from .models import RankedItem, SquadEvaluation, SquadMetrics


class SquadScorer:
    """Chấm điểm squad dựa trên cấu hình nhánh ``squad``."""

    def __init__(self, config: dict[str, Any]):
        squad_cfg = config.get("squad", {})
        self._weights = squad_cfg.get("weights", {})
        self._kr_cap = float(squad_cfg.get("kr_progress_cap", 100))
        self._grade_bands = squad_cfg.get("grade_bands", [])

    def score(self, squad: SquadMetrics) -> SquadEvaluation:
        # objective_achievement = TB có trọng số tiến độ các KR
        kr_pairs = [(kr.progress(self._kr_cap), kr.weight) for kr in squad.key_results]
        objective_score = round(weighted_mean(kr_pairs), 2)
        on_time_score = round(squad.on_time_rate * 100.0, 2)

        total = round(
            weighted_mean(
                [
                    (objective_score, float(self._weights.get("objective_achievement", 0.7))),
                    (on_time_score, float(self._weights.get("on_time_rate", 0.3))),
                ]
            ),
            2,
        )
        return SquadEvaluation(
            squad_id=squad.squad_id,
            squad_name=squad.squad_name,
            period=squad.period,
            objective_score=objective_score,
            on_time_score=on_time_score,
            total_score=total,
            grade=grade_for(total, self._grade_bands),
        )

    def score_all(self, squads: list[SquadMetrics]) -> list[SquadEvaluation]:
        return [self.score(s) for s in squads]


def rank_squads(evaluations: list[SquadEvaluation]) -> list[RankedItem]:
    ordered = sorted(evaluations, key=lambda e: e.total_score, reverse=True)
    return [
        RankedItem(
            rank=i + 1,
            item_id=e.squad_id,
            name=e.squad_name,
            total_score=e.total_score,
            grade=e.grade,
        )
        for i, e in enumerate(ordered)
    ]
