"""Test logic thuần của plugin telemetry (parse transcript, dựng trace, outcome)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "plugins" / "lsr-telemetry" / "scripts" / "lsr_trace.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("lsr_trace", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lsr = _load()


def test_tool_outcome_ok_and_result():
    assert lsr.tool_outcome({"content": "abc"}) == (True, True)
    assert lsr.tool_outcome({"error": "boom"})[0] is False
    assert lsr.tool_outcome({"is_error": True})[0] is False
    assert lsr.tool_outcome("")[1] is False


def test_parse_transcript_sums_tokens_and_last_text(tmp_path):
    lines = [
        {"message": {"role": "user", "content": [{"type": "text", "text": "hi"}]}},
        {"message": {"role": "assistant",
                     "usage": {"input_tokens": 100, "output_tokens": 40},
                     "content": [{"type": "text", "text": "first"}]}},
        {"message": {"role": "assistant",
                     "usage": {"input_tokens": 20, "output_tokens": 10},
                     "content": [{"type": "text", "text": "final answer"}]}},
    ]
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    it, ot, final = lsr.parse_transcript(str(p))
    assert it == 120 and ot == 50
    assert final == "final answer"


def test_parse_transcript_missing_file_is_safe():
    assert lsr.parse_transcript("/no/such/file") == (0, 0, "")


def test_build_trace_shape():
    trace = lsr.build_trace(
        session_id="S1",
        tool_records=[{"name": "search", "ok": True, "has_result": True}],
        input_tokens=120, output_tokens=50, final_output="done",
        agent_id="AG-X",
    )
    assert trace["run_id"] == "S1"
    assert trace["agent_id"] == "AG-X"
    assert trace["llm_calls"][0]["input_tokens"] == 120
    assert trace["tool_calls"][0]["name"] == "search"
    assert trace["final_output"] == "done"


def test_record_then_stop_roundtrip(tmp_path, monkeypatch):
    # Buffer -> stop dựng trace; không có LSR_COLLECTOR nên post no-op (trả False).
    monkeypatch.setenv("LSR_TRACE_DIR", str(tmp_path))
    monkeypatch.setenv("LSR_AGENT_ID", "AG-Y")
    monkeypatch.delenv("LSR_COLLECTOR", raising=False)
    lsr.record_tool({"session_id": "S9", "tool_name": "bq", "tool_response": {"content": "x"}})
    lsr.record_tool({"session_id": "S9", "tool_name": "bad", "tool_response": {"error": "e"}})
    buf = tmp_path / "S9.jsonl"
    assert buf.exists()
    # transcript trống -> token 0; stop phải xoá buffer sau khi xử lý
    lsr.stop({"session_id": "S9", "transcript_path": ""})
    assert not buf.exists()


def test_post_trace_noop_without_collector(monkeypatch):
    monkeypatch.delenv("LSR_COLLECTOR", raising=False)
    assert lsr.post_trace({"run_id": "x"}) is False
