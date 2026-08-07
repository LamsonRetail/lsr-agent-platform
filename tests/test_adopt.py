"""Test script adopt agent external (không network)."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "lsr_adopt.py"


def _load():
    spec = importlib.util.spec_from_file_location("lsr_adopt", _SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


adopt = _load()


class Args:
    id = "AG-EXT"
    name = "External Bot"
    owner = "an@lamsonretail.vn"
    squad = "SQ-SALES"
    connect_mode = "bot"
    model = "claude-sonnet-5"
    host_note = "VPS của team"
    collector = "https://collector.example"


def test_manifest_là_external_và_auth_subscription():
    md = adopt.build_manifest(Args(), "git@github.com:x/y.git", ["bigquery", "lark-task"])
    assert "mode: external" in md
    assert "auth: subscription" in md          # auth của owner, không dùng khoá chung
    assert "enabled: true" in md               # telemetry bắt buộc
    assert "repo_url: git@github.com:x/y.git" in md
    assert "{name: bigquery, type: mcp}" in md  # giữ nguyên MCP đang dùng


def test_dò_mcp_từ_cấu_hình_sẵn_có(tmp_path: Path):
    (tmp_path / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"bigquery": {}, "lark": {}}}), encoding="utf-8")
    assert adopt.detect_mcp_skills(tmp_path) == ["bigquery", "lark"]


def test_detect_project_name(tmp_path: Path):
    (tmp_path / "package.json").write_text(json.dumps({"name": "my-agent"}), encoding="utf-8")
    assert adopt.detect_project_name(tmp_path) == "my-agent"


def test_install_hooks_giữ_cấu_hình_cũ(tmp_path: Path):
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text(
        json.dumps({"model": "opus", "hooks": {}}), encoding="utf-8")
    trace = tmp_path / "src_trace.py"
    trace.write_text("# trace", encoding="utf-8")

    written = adopt.install_hooks(tmp_path, trace)
    data = json.loads((claude / "settings.json").read_text(encoding="utf-8"))
    assert data["model"] == "opus"                      # KHÔNG phá cấu hình sẵn có
    assert data["hooks"]["PostToolUse"] and data["hooks"]["Stop"]
    assert (tmp_path / ".lsr" / "lsr_trace.py").exists()
    assert ".claude/settings.json" in written
