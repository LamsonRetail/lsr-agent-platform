"""Enforce tiêu chuẩn cho MỌI agent trong platform (quét agents/*/lsr-agent.yaml).

Chạy trong pytest + CI → tạo agent mới không đúng chuẩn sẽ FAIL, không merge/deploy được.
Chuẩn:
  - có id/name; owner là email THẬT của người sở hữu (không dùng chung chung).
  - runtime.auth == 'subscription'  → mỗi agent dùng auth của OWNER, KHÔNG api key,
    KHÔNG auth chung platform.
  - KHÔNG có trường khoá LLM (api_key/anthropic_api_key/*_api_key) trong manifest.
  - telemetry.enabled == true  (control point bắt buộc).
  - connect_mode ∈ {bot, user}.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_AGENTS_DIR = Path(__file__).resolve().parents[1] / "agents"
_MANIFESTS = sorted(_AGENTS_DIR.glob("*/lsr-agent.yaml"))
_EMAIL = re.compile(r"^[^@]+@[^@]+\.[^@]+$")


def test_có_ít_nhất_một_agent():
    assert _MANIFESTS, "Chưa có agent nào trong agents/*/lsr-agent.yaml"


@pytest.mark.parametrize("path", _MANIFESTS, ids=lambda p: p.parent.name)
def test_agent_manifest_đúng_chuẩn(path: Path):
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    agent = data.get("agent", {})
    runtime = data.get("runtime", {})
    telemetry = data.get("telemetry", {})

    # id / name
    assert agent.get("id"), f"{path}: thiếu agent.id"
    assert agent.get("name"), f"{path}: thiếu agent.name"

    # owner = email thật (auth theo từng owner)
    owner = str(agent.get("owner", ""))
    assert _EMAIL.match(owner), f"{path}: agent.owner phải là email của owner (được: {owner!r})"

    # connect_mode hợp lệ
    assert agent.get("connect_mode") in ("bot", "user"), f"{path}: connect_mode phải là bot|user"

    # auth = subscription của owner, KHÔNG api key / KHÔNG auth chung
    assert runtime.get("auth") == "subscription", (
        f"{path}: runtime.auth phải = 'subscription' (mỗi agent dùng auth của owner, "
        "không dùng api key / auth chung platform)"
    )

    # telemetry bắt buộc
    assert telemetry.get("enabled") is True, f"{path}: telemetry.enabled phải = true"

    # cấm mọi khoá LLM lộ trong manifest
    blob = path.read_text(encoding="utf-8").lower()
    for bad in ("api_key", "api-key", "apikey", "anthropic_api_key", "sk-ant-"):
        assert bad not in blob, f"{path}: không được chứa khoá/field '{bad}' (dùng subscription của owner)"
