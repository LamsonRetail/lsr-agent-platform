"""Test cho chỉ số hành vi tool + token, có kết quả tính tay để đối chiếu."""

from __future__ import annotations

import pytest

from rating_agent.telemetry import (
    AgentRunTrace,
    LLMCall,
    TaskLabel,
    ToolCall,
    TokenBudget,
    TokenBudgetExceeded,
    TraceRecorder,
    compute_behavior_metrics,
    compute_token_stats,
)


def _trace(task_id, tools=None, llm=None, result_used=None, fabricated=None,
           answer_correct=None):
    return AgentRunTrace(
        run_id=f"r-{task_id}", agent_id="AG", task_id=task_id,
        tool_calls=tools or [], llm_calls=llm or [],
        result_used=result_used, fabricated=fabricated, answer_correct=answer_correct,
    )


@pytest.fixture()
def scenario():
    labels = {
        "R1": TaskLabel(task_id="R1", needs_tool=True, expected_tool="search"),
        "R2": TaskLabel(task_id="R2", needs_tool=True, expected_tool="search"),
        "R3": TaskLabel(task_id="R3", needs_tool=True, expected_tool="search"),
        "C1": TaskLabel(task_id="C1", needs_tool=False, answer_correct=True),
        "C2": TaskLabel(task_id="C2", needs_tool=False, answer_correct=True),
    }
    search_ok = ToolCall(name="search", ok=True, has_result=True)
    traces = [
        # R1: dùng đúng tool, có kết quả, output dùng kết quả -> clean, ok
        _trace("R1", tools=[search_ok], result_used=True, fabricated=False),
        # R2: bỏ qua tool + bịa -> skip, fabricate
        _trace("R2", tools=[], fabricated=True),
        # R3: dùng đúng tool có kết quả nhưng output phớt lờ -> clean nhưng ignore
        _trace("R3", tools=[search_ok], result_used=False, fabricated=False),
        # C1: không dùng tool, đúng -> ok
        _trace("C1", answer_correct=True),
        # C2: dùng tool thừa, vẫn đúng -> UTR
        _trace("C2", tools=[ToolCall(name="search", ok=True)], answer_correct=True),
    ]
    return traces, labels


def test_behavior_metrics_values(scenario):
    traces, labels = scenario
    m = compute_behavior_metrics(traces, labels)
    assert m.n_required == 3 and m.n_control == 2
    assert m.tsr == pytest.approx(1 / 3)      # R2 bỏ qua
    assert m.ctur == pytest.approx(2 / 3)     # R1, R3 sạch
    assert m.rir == pytest.approx(1 / 2)      # trong {R1,R3} có kết quả, R3 bị phớt lờ
    assert m.ofr == pytest.approx(1 / 3)      # R2 bịa
    assert m.utr == pytest.approx(1 / 2)      # C2 dùng tool thừa
    assert m.ctrl_acc == pytest.approx(1.0)   # C1, C2 đúng


def test_behavior_metrics_percent(scenario):
    traces, labels = scenario
    pct = compute_behavior_metrics(traces, labels).as_percent()
    assert pct["TSR"] == pytest.approx(33.33, abs=0.01)
    assert pct["CTRL-Acc"] == pytest.approx(100.0)


def test_empty_denominator_returns_none():
    # Không có control task -> UTR, CTRL-Acc = None (không xác định)
    labels = {"R1": TaskLabel(task_id="R1", needs_tool=True)}
    m = compute_behavior_metrics([_trace("R1", tools=[])], labels)
    assert m.utr is None and m.ctrl_acc is None


def test_token_stats():
    traces = [
        _trace("R1", llm=[LLMCall(input_tokens=100, output_tokens=50)]),
        _trace("R2", llm=[LLMCall(input_tokens=200, output_tokens=100),
                          LLMCall(input_tokens=10, output_tokens=5)]),
    ]
    s = compute_token_stats(traces)
    assert s.total_tokens == 465
    assert s.runs == 2
    assert s.avg_tokens_per_run == pytest.approx(232.5)


def test_token_budget_blocks_over_limit():
    rec = TraceRecorder("AG", budget=TokenBudget(limit_tokens=100))
    rec.record_llm("m", 40, 30)  # 70 ok
    with pytest.raises(TokenBudgetExceeded):
        rec.record_llm("m", 40, 30)  # 140 > 100


def test_recorder_builds_trace():
    rec = TraceRecorder("AG", task_id="T1", source="test")
    rec.record_llm("m", 10, 5)
    rec.record_tool("search", {"q": "x"}, ok=True, has_result=True)
    rec.set_output("done")
    rec.annotate(result_used=True, fabricated=False)
    tr = rec.build()
    assert tr.total_tokens == 15
    assert tr.called_tool_names == {"search"}
    assert tr.result_used is True and tr.final_output == "done"
