"""Test cho module test agent: runner + assertion."""

from __future__ import annotations

from rating_agent.agent_testing import (
    AssertionType,
    TestCase,
    TestRunner,
    check_assertion,
)


def test_assertion_types():
    assert check_assertion("ok", "all ok here", AssertionType.CONTAINS)
    assert check_assertion("abc", "abc", AssertionType.EXACT)
    assert not check_assertion("abc", "abcd", AssertionType.EXACT)
    assert check_assertion(r"\d{3}", "mã 123", AssertionType.REGEX)
    assert check_assertion("100", "100.4", AssertionType.NUMERIC_TOLERANCE, tolerance=1.0)
    assert not check_assertion("100", "150", AssertionType.NUMERIC_TOLERANCE, tolerance=1.0)


def _case(expected: str, atype: AssertionType) -> TestCase:
    return TestCase(
        test_id="T1", agent_id="AG", skill_id="SK", test_name="t",
        input_payload="hỏi", expected=expected, assertion_type=atype,
    )


def test_runner_pass_and_fail():
    runner = TestRunner(agent=lambda _inp: "đáp án đúng")
    passed = runner.run_case(_case("đúng", AssertionType.CONTAINS))
    failed = runner.run_case(_case("sai", AssertionType.CONTAINS))
    assert passed.passed and passed.status == "pass"
    assert not failed.passed and failed.status == "fail"


def test_runner_captures_agent_error():
    def broken(_inp: str) -> str:
        raise RuntimeError("agent chết")

    run = TestRunner(agent=broken).run_case(_case("x", AssertionType.CONTAINS))
    assert run.status == "error"
    assert "agent chết" in run.error


def test_run_suite_returns_all():
    runner = TestRunner(agent=lambda _inp: "42")
    runs = runner.run_suite([_case("42", AssertionType.EXACT), _case("99", AssertionType.EXACT)])
    assert [r.status for r in runs] == ["pass", "fail"]
