"""Cấu hình tập trung: đọc biến môi trường và file YAML chấm điểm.

Mọi credential đều lấy từ môi trường (hoặc file .env) — không hard-code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

try:  # tải .env nếu có, không bắt buộc
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - dotenv là optional
    pass


@dataclass(frozen=True)
class LarkConfig:
    """Thông tin xác thực Lark Custom App."""

    app_id: str
    app_secret: str
    domain: str = "https://open.larksuite.com"

    @property
    def is_configured(self) -> bool:
        return bool(self.app_id and self.app_secret)


@dataclass(frozen=True)
class BigQueryConfig:
    """Thông tin kết nối BigQuery."""

    project_id: str
    dataset: str
    location: str = "asia-southeast1"
    credentials_path: str | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self.project_id and self.dataset)


@dataclass(frozen=True)
class Settings:
    """Toàn bộ cấu hình runtime của agent."""

    lark: LarkConfig
    bigquery: BigQueryConfig
    scoring_config_path: Path
    evaluation_period: str
    extra: dict[str, Any] = field(default_factory=dict)


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def load_settings() -> Settings:
    """Tạo :class:`Settings` từ biến môi trường."""

    lark = LarkConfig(
        app_id=_get("LARK_APP_ID"),
        app_secret=_get("LARK_APP_SECRET"),
        domain=_get("LARK_DOMAIN", "https://open.larksuite.com"),
    )
    bigquery = BigQueryConfig(
        project_id=_get("BQ_PROJECT_ID"),
        dataset=_get("BQ_DATASET"),
        location=_get("BQ_LOCATION", "asia-southeast1"),
        credentials_path=_get("GOOGLE_APPLICATION_CREDENTIALS") or None,
    )
    return Settings(
        lark=lark,
        bigquery=bigquery,
        scoring_config_path=Path(_get("SCORING_CONFIG_PATH", "config/scoring_config.yaml")),
        evaluation_period=_get("EVALUATION_PERIOD", "2026-07"),
    )


def load_scoring_config(path: str | Path) -> dict[str, Any]:
    """Đọc file YAML trọng số chấm điểm."""

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Không tìm thấy file cấu hình chấm điểm: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}
