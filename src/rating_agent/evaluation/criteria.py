"""Tiêu chí chấm điểm: đọc trọng số từ config và chuẩn hoá giá trị thô.

Chuẩn hoá theo min-max trong nội bộ nhóm nhân viên được đánh giá (percentile
đơn giản). Với chỉ số ``higher_is_better=False`` (vd thời gian phản hồi) thì đảo
chiều để giá trị nhỏ được điểm cao.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MetricSpec:
    """Định nghĩa một chỉ số con."""

    name: str
    weight: float
    higher_is_better: bool = True


@dataclass(frozen=True)
class AxisSpec:
    """Định nghĩa một trục: danh sách chỉ số + trọng số trục."""

    name: str
    weight: float
    metrics: tuple[MetricSpec, ...]


def parse_criteria(config: dict[str, Any]) -> dict[str, AxisSpec]:
    """Chuyển dict YAML thành các :class:`AxisSpec` theo trục."""

    axis_weights = config.get("axis_weights", {})
    metrics_cfg = config.get("metrics", {})
    specs: dict[str, AxisSpec] = {}
    for axis_name, axis_weight in axis_weights.items():
        metric_specs = tuple(
            MetricSpec(
                name=m_name,
                weight=float(m_cfg.get("weight", 1.0)),
                higher_is_better=bool(m_cfg.get("higher_is_better", True)),
            )
            for m_name, m_cfg in metrics_cfg.get(axis_name, {}).items()
        )
        specs[axis_name] = AxisSpec(
            name=axis_name,
            weight=float(axis_weight),
            metrics=metric_specs,
        )
    return specs


def normalize(value: float, lo: float, hi: float, higher_is_better: bool = True) -> float:
    """Chuẩn hoá ``value`` về thang 0-100 dựa trên khoảng [lo, hi]."""

    if hi <= lo:
        # Mọi người bằng nhau ở chỉ số này → cho điểm trung tính.
        return 50.0
    ratio = (value - lo) / (hi - lo)
    ratio = max(0.0, min(1.0, ratio))
    if not higher_is_better:
        ratio = 1.0 - ratio
    return round(ratio * 100.0, 2)


def grade_for(total: float, bands: list[dict[str, Any]]) -> str:
    """Trả về nhãn xếp loại theo điểm tổng."""

    for band in sorted(bands, key=lambda b: b["min"], reverse=True):
        if total >= band["min"]:
            return str(band["label"])
    return ""
