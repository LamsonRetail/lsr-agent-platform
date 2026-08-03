"""Runner chạy test cho agent và kiểm tra assertion.

Agent được trừu tượng hoá thành một callable ``AgentCallable``:
    (input_payload: str) -> str
Nhờ vậy runner độc lập với cách agent được triển khai (HTTP, SDK, mock...).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

# Chữ ký của một agent để test: nhận input, trả về output dạng chuỗi.
AgentCallable = Callable[[str], str]


class AssertionType(str, Enum):
    EXACT = "exact"
    CONTAINS = "contains"
    REGEX = "regex"
    NUMERIC_TOLERANCE = "numeric_tolerance"
    SEMANTIC = "semantic"  # giai đoạn sau: so khớp bằng LLM/embedding


@dataclass
class TestCase:
    """Một bài test cho agent (ánh xạ tới bảng ``agent_test_cases``)."""

    __test__ = False  # để pytest không nhầm là test class

    test_id: str
    agent_id: str
    skill_id: str
    test_name: str
    input_payload: str
    expected: str
    assertion_type: AssertionType = AssertionType.CONTAINS
    weight: float = 1.0
    tolerance: float = 0.0  # dùng cho NUMERIC_TOLERANCE


@dataclass
class TestRun:
    """Kết quả một lần chạy test (ánh xạ tới bảng ``agent_test_runs``)."""

    __test__ = False  # để pytest không nhầm là test class

    test_id: str
    agent_id: str
    skill_id: str
    status: str  # "pass" | "fail" | "error"
    actual_output: str = ""
    latency_ms: float = 0.0
    error: str = ""

    @property
    def passed(self) -> bool:
        return self.status == "pass"


def check_assertion(expected: str, actual: str, atype: AssertionType, tolerance: float = 0.0) -> bool:
    """Kiểm tra output thực tế so với kỳ vọng theo loại assertion."""

    if atype is AssertionType.EXACT:
        return actual.strip() == expected.strip()
    if atype is AssertionType.CONTAINS:
        return expected.strip().lower() in actual.strip().lower()
    if atype is AssertionType.REGEX:
        return re.search(expected, actual) is not None
    if atype is AssertionType.NUMERIC_TOLERANCE:
        try:
            return abs(float(actual) - float(expected)) <= tolerance
        except (TypeError, ValueError):
            return False
    if atype is AssertionType.SEMANTIC:
        # Khung: giai đoạn sau dùng LLM/embedding. Tạm fallback về CONTAINS.
        return expected.strip().lower() in actual.strip().lower()
    return False


@dataclass
class TestRunner:
    """Chạy các :class:`TestCase` với một agent callable.

    Ví dụ::

        runner = TestRunner(agent_fn)
        runs = runner.run_suite(cases)
    """

    __test__ = False  # để pytest không nhầm là test class

    agent: AgentCallable
    clock_ms: Callable[[], float] = field(default=lambda: 0.0)

    def run_case(self, case: TestCase) -> TestRun:
        start = self.clock_ms()
        try:
            output = self.agent(case.input_payload)
        except Exception as exc:  # agent lỗi khi gọi
            return TestRun(
                test_id=case.test_id,
                agent_id=case.agent_id,
                skill_id=case.skill_id,
                status="error",
                error=str(exc),
                latency_ms=self.clock_ms() - start,
            )
        ok = check_assertion(case.expected, output, case.assertion_type, case.tolerance)
        return TestRun(
            test_id=case.test_id,
            agent_id=case.agent_id,
            skill_id=case.skill_id,
            status="pass" if ok else "fail",
            actual_output=output,
            latency_ms=self.clock_ms() - start,
        )

    def run_suite(self, cases: list[TestCase]) -> list[TestRun]:
        return [self.run_case(c) for c in cases]
