"""Hàm dùng chung cho chấm điểm: chuẩn hoá, trung bình có trọng số, xếp loại."""

from __future__ import annotations

from typing import Any


def normalize(value: float, lo: float, hi: float, higher_is_better: bool = True) -> float:
    """Chuẩn hoá ``value`` về thang 0-100 dựa trên khoảng [lo, hi].

    Nếu ``hi <= lo`` (mọi giá trị bằng nhau) → điểm trung tính 50.
    ``higher_is_better=False`` → đảo chiều (giá trị nhỏ được điểm cao).
    """

    if hi <= lo:
        return 50.0
    ratio = (value - lo) / (hi - lo)
    ratio = max(0.0, min(1.0, ratio))
    if not higher_is_better:
        ratio = 1.0 - ratio
    return round(ratio * 100.0, 2)


def weighted_mean(pairs: list[tuple[float, float]]) -> float:
    """Trung bình có trọng số; tự chuẩn hoá tổng trọng số về 1.

    ``pairs`` = danh sách ``(giá_trị, trọng_số)``. Trả về 0 nếu tổng trọng số 0.
    """

    total_w = sum(w for _v, w in pairs)
    if total_w == 0:
        return 0.0
    return sum(v * w for v, w in pairs) / total_w


def grade_for(total: float, bands: list[dict[str, Any]]) -> str:
    """Trả về nhãn xếp loại theo điểm tổng."""

    for band in sorted(bands, key=lambda b: b["min"], reverse=True):
        if total >= band["min"]:
            return str(band["label"])
    return ""
