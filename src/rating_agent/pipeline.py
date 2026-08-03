"""Điều phối pipeline hai nhánh: SQUAD (mục tiêu) và AGENT (skill/usage/kết quả).

Bản MVP: dùng dữ liệu mẫu để chạy end-to-end mà không cần credential. Khi Lark
Base/BigQuery đã cấu hình, thay bằng các hàm ``collect_*_from_sources``.
"""

from __future__ import annotations

import logging

from .config import Settings, load_scoring_config, load_settings
from .evaluation import (
    AgentMetrics,
    AgentScorer,
    AgentSkillResult,
    KeyResult,
    RankedItem,
    SquadMetrics,
    SquadScorer,
    rank_agents,
    rank_squads,
)
from .evaluation.models import AgentEvaluation, SquadEvaluation

logger = logging.getLogger(__name__)


# =========================== Dữ liệu mẫu ===========================


def build_sample_squads() -> list[SquadMetrics]:
    return [
        SquadMetrics(
            squad_id="SQ-SALES",
            squad_name="Squad Sales HN",
            period="2026-07",
            on_time_rate=0.9,
            key_results=[
                KeyResult(objective_name="Tăng doanh thu", key_result="Doanh thu quý",
                          target=1000, actual=1150, weight=0.5),
                KeyResult(objective_name="Mở điểm bán", key_result="Số điểm bán mới",
                          target=10, actual=8, weight=0.3),
                KeyResult(objective_name="Giữ chân KH", key_result="Tỉ lệ quay lại %",
                          target=60, actual=55, weight=0.2),
            ],
        ),
        SquadMetrics(
            squad_id="SQ-OPS",
            squad_name="Squad Vận hành",
            period="2026-07",
            on_time_rate=0.75,
            key_results=[
                KeyResult(objective_name="Giao hàng đúng hạn", key_result="On-time %",
                          target=95, actual=88, weight=0.6),
                KeyResult(objective_name="Giảm tồn kho", key_result="Ngày tồn kho",
                          target=30, actual=34, weight=0.4),
            ],
        ),
    ]


def build_sample_agents() -> list[AgentMetrics]:
    return [
        # Agent tốt, ổn định.
        AgentMetrics(
            agent_id="AG-ORDER-BOT",
            agent_name="Order Lookup Bot",
            period="2026-07",
            skill_results=[
                AgentSkillResult(skill_id="SK-LOOKUP", skill_name="Tra cứu đơn",
                                 tests_total=10, tests_passed=10),
                AgentSkillResult(skill_id="SK-SUMMARY", skill_name="Tóm tắt",
                                 tests_total=5, tests_passed=4),
            ],
            invocations=1200, unique_users=45,
            success_rate=0.96, user_rating=4.6, avg_latency_ms=800,
            recent_test_results=[True, True, True, True],
        ),
        # Agent dùng ít, kết quả trung bình.
        AgentMetrics(
            agent_id="AG-KPI-BOT",
            agent_name="KPI Insight Bot",
            period="2026-07",
            skill_results=[
                AgentSkillResult(skill_id="SK-ANALYZE", skill_name="Phân tích KPI",
                                 tests_total=8, tests_passed=6),
            ],
            invocations=300, unique_users=12,
            success_rate=0.82, user_rating=3.9, avg_latency_ms=2200,
            recent_test_results=[True, False, True, True],
        ),
        # Agent fail 2 lần liên tiếp -> phải bị khuyến nghị deactivate.
        AgentMetrics(
            agent_id="AG-CHAT-HELPER",
            agent_name="Chat Helper Bot",
            period="2026-07",
            skill_results=[
                AgentSkillResult(skill_id="SK-REPLY", skill_name="Trả lời tự động",
                                 tests_total=10, tests_passed=4),
            ],
            invocations=150, unique_users=8,
            success_rate=0.55, user_rating=2.8, avg_latency_ms=3500,
            recent_test_results=[True, False, False],
        ),
    ]


# =========================== Kết nối thật (khung) ===========================


def collect_squads_from_sources(settings: Settings) -> list[SquadMetrics]:
    raise NotImplementedError(
        "Giai đoạn 2: đọc squads/squad_objectives từ Lark Base, lấy actual từ "
        "BigQuery/Lark Task."
    )


def collect_agents_from_sources(settings: Settings) -> list[AgentMetrics]:
    raise NotImplementedError(
        "Giai đoạn 2: đọc agents/agent_usage từ Lark Base và tổng hợp agent_test_runs."
    )


# =========================== Chạy pipeline ===========================


def run(settings: Settings | None = None, *, use_sample: bool = True) -> dict[str, list]:
    """Chạy cả hai nhánh, trả về dict {'squads': [...], 'agents': [...]}."""

    settings = settings or load_settings()
    config = load_scoring_config(settings.scoring_config_path)

    squads = build_sample_squads() if use_sample else collect_squads_from_sources(settings)
    agents = build_sample_agents() if use_sample else collect_agents_from_sources(settings)

    squad_evals = SquadScorer(config).score_all(squads)
    agent_evals = AgentScorer(config).score_all(agents)
    return {"squads": squad_evals, "agents": agent_evals}


# =========================== Định dạng báo cáo ===========================


def format_squad_board(evals: list[SquadEvaluation]) -> str:
    lines = ["== SQUAD SCOREBOARD (hiệu quả theo mục tiêu) =="]
    lines.append("Hạng | Squad            | Mục tiêu | Đúng hạn | Tổng  | Xếp loại")
    lines.append("-" * 70)
    for r in rank_squads(evals):
        e = next(x for x in evals if x.squad_id == r.item_id)
        lines.append(
            f"{r.rank:>4} | {e.squad_name:<16} | {e.objective_score:>8.1f} | "
            f"{e.on_time_score:>8.1f} | {e.total_score:>5.1f} | {e.grade}"
        )
    return "\n".join(lines)


def format_agent_board(evals: list[AgentEvaluation]) -> str:
    lines = ["== AGENT LEADERBOARD (skill / usage / kết quả) =="]
    lines.append("Hạng | Agent             | Skill | Usage | Result | Test% | Tổng | Khuyến nghị")
    lines.append("-" * 88)
    for r in rank_agents(evals):
        e = next(x for x in evals if x.agent_id == r.item_id)
        lines.append(
            f"{r.rank:>4} | {e.agent_name:<17} | {e.skill_score:>5.0f} | "
            f"{e.usage_score:>5.0f} | {e.result_score:>6.0f} | {e.test_pass_rate:>5.0f} | "
            f"{e.total_score:>4.0f} | {e.status_recommendation.value}"
            + (f" ({e.note})" if e.note else "")
        )
    return "\n".join(lines)


def main() -> None:  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    result = run(use_sample=True)
    print(format_squad_board(result["squads"]))
    print()
    print(format_agent_board(result["agents"]))


if __name__ == "__main__":  # pragma: no cover
    main()
