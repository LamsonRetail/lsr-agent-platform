"""Test cho việc nạp cấu hình."""

from __future__ import annotations

from pathlib import Path

from rating_agent.config import load_scoring_config
from rating_agent.evaluation.criteria import parse_criteria

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "scoring_config.yaml"


def test_scoring_config_loads():
    cfg = load_scoring_config(CONFIG_PATH)
    assert "axis_weights" in cfg
    assert "metrics" in cfg


def test_parse_criteria_has_three_axes():
    cfg = load_scoring_config(CONFIG_PATH)
    specs = parse_criteria(cfg)
    assert set(specs) == {"collaboration", "grow", "performance"}
    for spec in specs.values():
        assert spec.metrics  # mỗi trục có ít nhất 1 chỉ số
        assert spec.weight > 0
