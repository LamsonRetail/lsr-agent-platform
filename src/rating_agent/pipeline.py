"""Điều phối pipeline: thu thập → tính điểm → báo cáo.

Ở bản MVP, hàm :func:`build_sample_cohort` sinh dữ liệu mẫu để chạy end-to-end
mà không cần credential. Khi Lark/BigQuery đã cấu hình, thay bằng
:func:`collect_from_sources`.
"""

from __future__ import annotations

import logging

from .config import Settings, load_scoring_config, load_settings
from .evaluation import EmployeeMetrics, Scorer, rank_employees
from .evaluation.models import Axis, EmployeeEvaluation, RankedEmployee

logger = logging.getLogger(__name__)


def build_sample_cohort() -> list[EmployeeMetrics]:
    """Dữ liệu mẫu 3 nhân viên để minh hoạ luồng chấm điểm."""

    return [
        EmployeeMetrics(
            employee_id="E001",
            full_name="Nguyễn An",
            department="Sales",
            period="2026-07",
            metrics={
                Axis.COLLABORATION: {
                    "response_rate": 0.9,
                    "avg_response_time": 300,  # giây, thấp là tốt
                    "cross_team_tasks": 5,
                    "doc_coauthor": 3,
                },
                Axis.GROW: {
                    "skill_trend": 0.8,
                    "task_complexity_up": 0.7,
                    "learning_docs": 4,
                    "feedback_adoption": 0.9,
                },
                Axis.PERFORMANCE: {
                    "task_completion_rate": 0.95,
                    "on_time_rate": 0.9,
                    "sales_kpi": 1.2,
                    "quality_score": 0.92,
                },
            },
        ),
        EmployeeMetrics(
            employee_id="E002",
            full_name="Trần Bình",
            department="Sales",
            period="2026-07",
            metrics={
                Axis.COLLABORATION: {
                    "response_rate": 0.6,
                    "avg_response_time": 1200,
                    "cross_team_tasks": 2,
                    "doc_coauthor": 1,
                },
                Axis.GROW: {
                    "skill_trend": 0.5,
                    "task_complexity_up": 0.4,
                    "learning_docs": 1,
                    "feedback_adoption": 0.6,
                },
                Axis.PERFORMANCE: {
                    "task_completion_rate": 0.75,
                    "on_time_rate": 0.7,
                    "sales_kpi": 0.9,
                    "quality_score": 0.8,
                },
            },
        ),
        EmployeeMetrics(
            employee_id="E003",
            full_name="Lê Chi",
            department="Ops",
            period="2026-07",
            metrics={
                Axis.COLLABORATION: {
                    "response_rate": 0.75,
                    "avg_response_time": 600,
                    "cross_team_tasks": 4,
                    "doc_coauthor": 2,
                },
                Axis.GROW: {
                    "skill_trend": 0.65,
                    "task_complexity_up": 0.6,
                    "learning_docs": 3,
                    "feedback_adoption": 0.75,
                },
                Axis.PERFORMANCE: {
                    "task_completion_rate": 0.88,
                    "on_time_rate": 0.85,
                    "sales_kpi": 1.05,
                    "quality_score": 0.88,
                },
            },
        ),
    ]


def collect_from_sources(settings: Settings) -> list[EmployeeMetrics]:
    """Thu thập chỉ số thật từ Lark + BigQuery (khung — giai đoạn 2).

    Luồng dự kiến:
      1. BigQueryService.query(employee_directory) → map lark_user_id↔employee_id.
      2. LarkChatService/DocService/TaskService.collect_signals() → tín hiệu Lark.
      3. BigQueryService.query(sales_kpi/quality) → tín hiệu kinh doanh.
      4. Ghép về EmployeeMetrics theo employee_id.
    """

    raise NotImplementedError(
        "Kết nối nguồn thật sẽ triển khai ở giai đoạn 2 (cần credential). "
        "Hiện dùng build_sample_cohort() để chạy demo."
    )


def run(settings: Settings | None = None, *, use_sample: bool = True) -> list[EmployeeEvaluation]:
    """Chạy toàn bộ pipeline, trả về danh sách bản đánh giá."""

    settings = settings or load_settings()
    config = load_scoring_config(settings.scoring_config_path)
    scorer = Scorer.from_config(config)

    cohort = build_sample_cohort() if use_sample else collect_from_sources(settings)
    evaluations = scorer.score_all(cohort)
    return evaluations


def format_ranking(ranking: list[RankedEmployee]) -> str:
    """Định dạng bảng xếp hạng dạng text để in ra."""

    lines = ["Hạng | Mã NV | Họ tên        | Tổng điểm | Xếp loại"]
    lines.append("-" * 60)
    for r in ranking:
        lines.append(
            f"{r.rank:>4} | {r.employee_id:<5} | {r.full_name:<13} | "
            f"{r.total_score:>8.2f} | {r.grade}"
        )
    return "\n".join(lines)


def main() -> None:  # pragma: no cover - tiện chạy tay
    logging.basicConfig(level=logging.INFO)
    evaluations = run(use_sample=True)
    ranking = rank_employees(evaluations)
    print(format_ranking(ranking))


if __name__ == "__main__":  # pragma: no cover
    main()
