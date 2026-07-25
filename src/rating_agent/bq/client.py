"""Khung kết nối BigQuery — client + ví dụ query dữ liệu vận hành kinh doanh.

Xác thực bằng service account: đặt đường dẫn JSON key vào biến môi trường
``GOOGLE_APPLICATION_CREDENTIALS``; thư viện google-cloud sẽ tự nạp.

Bản MVP: client mỏng bọc quanh ``google.cloud.bigquery``. Nếu chưa cài thư viện
hoặc chưa cấu hình credential, ``query()`` sẽ báo lỗi rõ ràng thay vì crash mơ hồ.
"""

from __future__ import annotations

import logging
from typing import Any

from ..config import BigQueryConfig

logger = logging.getLogger(__name__)


class BigQueryService:
    """Client BigQuery cho data warehouse LamsonRetail.

    Ví dụ::

        svc = BigQueryService(config)
        rows = svc.query("SELECT employee_id, SUM(amount) AS revenue "
                         "FROM `{dataset}.sales_fact` GROUP BY 1")
    """

    def __init__(self, config: BigQueryConfig) -> None:
        self._config = config
        self._client: Any | None = None

    def _get_client(self) -> Any:
        """Khởi tạo lazy ``bigquery.Client`` (đọc credential từ env)."""

        if self._client is not None:
            return self._client
        if not self._config.is_configured:
            raise RuntimeError(
                "Thiếu BQ_PROJECT_ID/BQ_DATASET — hãy cấu hình trong .env"
            )
        try:
            from google.cloud import bigquery
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Chưa cài google-cloud-bigquery. Chạy: pip install google-cloud-bigquery"
            ) from exc

        self._client = bigquery.Client(
            project=self._config.project_id,
            location=self._config.location,
        )
        return self._client

    def _format(self, sql: str) -> str:
        """Thay placeholder ``{dataset}``/``{project}`` bằng giá trị cấu hình."""

        return sql.format(
            project=self._config.project_id,
            dataset=f"{self._config.project_id}.{self._config.dataset}",
        )

    def query(self, sql: str) -> list[dict[str, Any]]:
        """Chạy một câu SQL, trả về danh sách dict.

        Hỗ trợ placeholder ``{dataset}`` = ``project.dataset``.
        """

        client = self._get_client()
        formatted = self._format(sql)
        logger.debug("BigQuery SQL: %s", formatted)
        job = client.query(formatted)
        return [dict(row.items()) for row in job.result()]


# --- Ví dụ query (khung) -------------------------------------------------

EXAMPLE_QUERIES: dict[str, str] = {
    # KPI bán hàng theo nhân viên trong kỳ.
    "sales_kpi_by_employee": """
        SELECT
          employee_id,
          SUM(amount)                         AS revenue,
          SAFE_DIVIDE(SUM(amount), ANY_VALUE(target)) AS kpi_ratio
        FROM `{dataset}.sales_fact`
        WHERE period = @period
        GROUP BY employee_id
    """,
    # Chỉ số chất lượng (tỉ lệ đổi trả, điểm hài lòng KH).
    "quality_by_employee": """
        SELECT
          employee_id,
          1 - SAFE_DIVIDE(returns, orders) AS quality_score
        FROM `{dataset}.kpi_monthly`
        WHERE period = @period
    """,
    # Map Lark user id <-> employee id.
    "employee_directory": """
        SELECT employee_id, lark_user_id, full_name, department
        FROM `{dataset}.employees`
    """,
}
