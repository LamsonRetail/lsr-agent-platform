"""Data model cho việc đánh giá nhân viên.

Ba trục: collaboration, grow, performance. Mỗi trục gồm nhiều chỉ số con dạng
số. Chỉ số thô được scorer chuẩn hoá về thang 0-100 trước khi áp trọng số.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Axis(str, Enum):
    """Ba trục đánh giá chính."""

    COLLABORATION = "collaboration"
    GROW = "grow"
    PERFORMANCE = "performance"


class EmployeeMetrics(BaseModel):
    """Chỉ số thô của một nhân viên trong một kỳ đánh giá.

    ``metrics`` gom theo trục → {tên_chỉ_số: giá_trị_thô}. Giá trị thô có thể ở
    bất kỳ thang nào (tỉ lệ 0-1, số đếm, giây...); scorer sẽ chuẩn hoá.
    """

    employee_id: str
    full_name: str = ""
    department: str = ""
    period: str = ""
    metrics: dict[Axis, dict[str, float]] = Field(default_factory=dict)

    def get(self, axis: Axis, name: str, default: float = 0.0) -> float:
        return self.metrics.get(axis, {}).get(name, default)


class AxisScore(BaseModel):
    """Điểm một trục (0-100) kèm chi tiết đóng góp từng chỉ số."""

    axis: Axis
    score: float
    breakdown: dict[str, float] = Field(default_factory=dict)


class EmployeeEvaluation(BaseModel):
    """Kết quả đánh giá đầy đủ của một nhân viên."""

    employee_id: str
    full_name: str = ""
    department: str = ""
    period: str = ""
    axis_scores: dict[Axis, AxisScore] = Field(default_factory=dict)
    total_score: float = 0.0
    grade: str = ""

    def axis(self, axis: Axis) -> float:
        score = self.axis_scores.get(axis)
        return score.score if score else 0.0


class RankedEmployee(BaseModel):
    """Một dòng trong bảng xếp hạng."""

    rank: int
    employee_id: str
    full_name: str
    total_score: float
    grade: str
