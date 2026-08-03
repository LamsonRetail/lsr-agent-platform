"""Module test agent: định nghĩa test case, runner, và cổng governance.

Cho phép chạy bộ test của một agent (pre-golive hoặc định kỳ), ghi kết quả, và
quyết định trạng thái (giữ active / cảnh báo / deactivate) theo chính sách.
"""

from .runner import (
    AgentCallable,
    AssertionType,
    TestCase,
    TestRun,
    TestRunner,
    check_assertion,
)

__all__ = [
    "AgentCallable",
    "AssertionType",
    "TestCase",
    "TestRun",
    "TestRunner",
    "check_assertion",
]
