"""Scorer: tính điểm 3 trục và điểm tổng, sinh bản đánh giá + xếp hạng.

Luồng::

    scorer = Scorer.from_config(load_scoring_config(path))
    evaluations = scorer.score_all(list_of_employee_metrics)
    ranking = rank_employees(evaluations)
"""

from __future__ import annotations

from typing import Any, Iterable

from .criteria import AxisSpec, grade_for, normalize, parse_criteria
from .models import (
    Axis,
    AxisScore,
    EmployeeEvaluation,
    EmployeeMetrics,
    RankedEmployee,
)


class Scorer:
    """Chấm điểm nhân viên dựa trên tiêu chí đã cấu hình."""

    def __init__(self, axis_specs: dict[str, AxisSpec], grade_bands: list[dict[str, Any]]):
        self._axis_specs = axis_specs
        self._grade_bands = grade_bands

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "Scorer":
        return cls(
            axis_specs=parse_criteria(config),
            grade_bands=config.get("grade_bands", []),
        )

    # -- Chuẩn hoá theo nhóm -------------------------------------------
    def _metric_ranges(
        self, cohort: list[EmployeeMetrics]
    ) -> dict[tuple[Axis, str], tuple[float, float]]:
        """Tính khoảng [min, max] mỗi chỉ số trong toàn bộ nhóm để chuẩn hoá."""

        ranges: dict[tuple[Axis, str], tuple[float, float]] = {}
        for axis_name, spec in self._axis_specs.items():
            axis = Axis(axis_name)
            for metric in spec.metrics:
                values = [emp.get(axis, metric.name) for emp in cohort]
                ranges[(axis, metric.name)] = (min(values), max(values)) if values else (0.0, 0.0)
        return ranges

    def _weighted(self, pairs: list[tuple[float, float]]) -> float:
        """Trung bình có trọng số; tự chuẩn hoá tổng trọng số về 1."""

        total_w = sum(w for _v, w in pairs)
        if total_w == 0:
            return 0.0
        return sum(v * w for v, w in pairs) / total_w

    # -- Chấm điểm ------------------------------------------------------
    def score_all(self, cohort: list[EmployeeMetrics]) -> list[EmployeeEvaluation]:
        """Chấm điểm cả nhóm (cần cả nhóm để chuẩn hoá tương đối)."""

        ranges = self._metric_ranges(cohort)
        return [self._score_one(emp, ranges) for emp in cohort]

    def _score_one(
        self,
        emp: EmployeeMetrics,
        ranges: dict[tuple[Axis, str], tuple[float, float]],
    ) -> EmployeeEvaluation:
        axis_scores: dict[Axis, AxisScore] = {}
        axis_pairs: list[tuple[float, float]] = []

        for axis_name, spec in self._axis_specs.items():
            axis = Axis(axis_name)
            breakdown: dict[str, float] = {}
            metric_pairs: list[tuple[float, float]] = []
            for metric in spec.metrics:
                lo, hi = ranges.get((axis, metric.name), (0.0, 0.0))
                raw = emp.get(axis, metric.name)
                norm = normalize(raw, lo, hi, metric.higher_is_better)
                breakdown[metric.name] = norm
                metric_pairs.append((norm, metric.weight))

            axis_value = round(self._weighted(metric_pairs), 2)
            axis_scores[axis] = AxisScore(axis=axis, score=axis_value, breakdown=breakdown)
            axis_pairs.append((axis_value, spec.weight))

        total = round(self._weighted(axis_pairs), 2)
        return EmployeeEvaluation(
            employee_id=emp.employee_id,
            full_name=emp.full_name,
            department=emp.department,
            period=emp.period,
            axis_scores=axis_scores,
            total_score=total,
            grade=grade_for(total, self._grade_bands),
        )


def rank_employees(evaluations: Iterable[EmployeeEvaluation]) -> list[RankedEmployee]:
    """Xếp hạng theo điểm tổng giảm dần."""

    ordered = sorted(evaluations, key=lambda e: e.total_score, reverse=True)
    return [
        RankedEmployee(
            rank=i + 1,
            employee_id=e.employee_id,
            full_name=e.full_name,
            total_score=e.total_score,
            grade=e.grade,
        )
        for i, e in enumerate(ordered)
    ]
