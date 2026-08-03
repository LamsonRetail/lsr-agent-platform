"""Test cho việc nạp cấu hình chấm điểm hai nhánh."""

from __future__ import annotations

from pathlib import Path

from rating_agent.config import load_scoring_config

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "scoring_config.yaml"


def test_scoring_config_has_both_tracks():
    cfg = load_scoring_config(CONFIG_PATH)
    assert "squad" in cfg
    assert "agent" in cfg


def test_squad_config_shape():
    cfg = load_scoring_config(CONFIG_PATH)["squad"]
    assert "weights" in cfg
    assert "grade_bands" in cfg


def test_agent_config_has_deactivate_policy():
    cfg = load_scoring_config(CONFIG_PATH)["agent"]
    assert "weights" in cfg
    policy = cfg["deactivate_policy"]
    assert policy["mode"] in {"consecutive_fail", "single_fail", "pass_rate"}
    assert policy["consecutive_fail_threshold"] >= 1
