"""Data model cho hai nhánh đánh giá: SQUAD và AGENT.

- SQUAD: chấm theo mục tiêu (Key Result achievement + đúng tiến độ).
- AGENT: chấm theo skill / mức độ sử dụng / kết quả trả về, kèm khuyến nghị
  governance (keep_active / watch / deactivate).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


# =========================== SQUAD ================================


class KeyResult(BaseModel):
    """Một Key Result của squad trong kỳ."""

    objective_name: str
    key_result: str
    target: float
    actual: float
    weight: float = 1.0

    def progress(self, cap: float = 100.0) -> float:
        """Tiến độ đạt KR theo % (0..cap). ``target<=0`` → 0."""

        if self.target <= 0:
            return 0.0
        pct = (self.actual / self.target) * 100.0
        return max(0.0, min(cap, round(pct, 2)))


class SquadMetrics(BaseModel):
    """Chỉ số thô của một squad trong kỳ."""

    squad_id: str
    squad_name: str = ""
    period: str = ""
    key_results: list[KeyResult] = Field(default_factory=list)
    on_time_rate: float = 0.0  # 0..1


class SquadEvaluation(BaseModel):
    """Kết quả đánh giá squad."""

    squad_id: str
    squad_name: str = ""
    period: str = ""
    objective_score: float = 0.0
    on_time_score: float = 0.0
    total_score: float = 0.0
    grade: str = ""


# =========================== AGENT ================================


class AgentStatus(str, Enum):
    DRAFT = "draft"
    REGISTERED = "registered"
    TESTING = "testing"
    ACTIVE = "active"
    DEACTIVATED = "deactivated"


class StatusRecommendation(str, Enum):
    KEEP_ACTIVE = "keep_active"
    WATCH = "watch"
    DEACTIVATE = "deactivate"


class AgentSkillResult(BaseModel):
    """Kết quả test gộp theo một skill của agent."""

    skill_id: str
    skill_name: str = ""
    tests_total: int = 0
    tests_passed: int = 0

    @property
    def pass_rate(self) -> float:
        if self.tests_total == 0:
            return 0.0
        return self.tests_passed / self.tests_total


class AgentMetrics(BaseModel):
    """Chỉ số thô của một agent trong kỳ."""

    agent_id: str
    agent_name: str = ""
    period: str = ""
    status: AgentStatus = AgentStatus.ACTIVE
    # Skill
    skill_results: list[AgentSkillResult] = Field(default_factory=list)
    # Usage
    invocations: int = 0
    unique_users: int = 0
    # Result
    success_rate: float = 0.0  # 0..1
    user_rating: float = 0.0  # 1..5
    avg_latency_ms: float = 0.0
    # Governance: kết quả các lần test gần nhất theo thứ tự thời gian
    # (True = pass). Dùng để áp chính sách auto-deactivate.
    recent_test_results: list[bool] = Field(default_factory=list)

    @property
    def test_pass_rate(self) -> float:
        total = sum(s.tests_total for s in self.skill_results)
        passed = sum(s.tests_passed for s in self.skill_results)
        return passed / total if total else 0.0


class AgentEvaluation(BaseModel):
    """Kết quả đánh giá agent."""

    agent_id: str
    agent_name: str = ""
    period: str = ""
    skill_score: float = 0.0
    usage_score: float = 0.0
    result_score: float = 0.0
    test_pass_rate: float = 0.0
    total_score: float = 0.0
    grade: str = ""
    status_recommendation: StatusRecommendation = StatusRecommendation.KEEP_ACTIVE
    note: str = ""


class RankedItem(BaseModel):
    """Một dòng bảng xếp hạng (dùng chung cho squad/agent)."""

    rank: int
    item_id: str
    name: str
    total_score: float
    grade: str
    extra: str = ""
