"""SDK telemetry — agent trên VPS dùng để ghi trace, kiểm soát token, gửi về collector.

Ý tưởng: bọc (wrap) lời gọi LLM và tool của agent để tự động ghi lại token, tool
call, kết quả và output. Cuối lượt chạy, gọi ``build()`` để lấy :class:`AgentRunTrace`
rồi ``TelemetryClient.report()`` gửi về Rating Agent.

Đây là *khung* (interface + luồng). Phần gửi HTTP cần endpoint collector + API key
cấp khi đăng ký agent.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from .trace import AgentRunTrace, LLMCall, ToolCall

logger = logging.getLogger(__name__)


class TokenBudgetExceeded(RuntimeError):
    """Ném ra khi lượt chạy vượt hạn mức token cho phép."""


class TokenBudget:
    """Kiểm soát token dạng soft-limit trong process agent.

    Kiểm soát 'cứng' hơn nên đặt ở LLM gateway (virtual key + budget). Lớp này là
    lớp phòng vệ tại chỗ: cộng dồn token và chặn khi vượt ``limit_tokens``.
    """

    def __init__(self, limit_tokens: int | None = None) -> None:
        self.limit_tokens = limit_tokens
        self.used = 0

    def add(self, tokens: int) -> None:
        self.used += tokens
        if self.limit_tokens is not None and self.used > self.limit_tokens:
            raise TokenBudgetExceeded(
                f"Vượt hạn mức token: {self.used} > {self.limit_tokens}"
            )

    @property
    def remaining(self) -> int | None:
        if self.limit_tokens is None:
            return None
        return max(0, self.limit_tokens - self.used)


class TraceRecorder:
    """Ghi lại một lượt chạy agent.

    Ví dụ tích hợp trong agent::

        rec = TraceRecorder(agent_id="AG-ORDER-BOT", task_id="T-123",
                            budget=TokenBudget(limit_tokens=50_000))
        resp = call_llm(...)
        rec.record_llm(resp.model, resp.usage.input_tokens, resp.usage.output_tokens)
        result = run_tool("order_lookup", {"id": "A1"})
        rec.record_tool("order_lookup", {"id": "A1"}, ok=True, has_result=bool(result))
        rec.set_output(final_answer)
        trace = rec.build()
    """

    def __init__(
        self,
        agent_id: str,
        *,
        run_id: str = "",
        task_id: str = "",
        source: str = "production",
        budget: TokenBudget | None = None,
    ) -> None:
        self._trace = AgentRunTrace(
            run_id=run_id or f"{agent_id}-run",
            agent_id=agent_id,
            task_id=task_id,
            source=source,
        )
        self._budget = budget

    def record_llm(self, model: str, input_tokens: int, output_tokens: int) -> None:
        self._trace.llm_calls.append(
            LLMCall(model=model, input_tokens=input_tokens, output_tokens=output_tokens)
        )
        if self._budget is not None:
            self._budget.add(input_tokens + output_tokens)

    def record_tool(
        self, name: str, arguments: dict[str, Any] | None = None,
        *, ok: bool = True, has_result: bool = True,
        used_in_output: bool | None = None,
    ) -> None:
        self._trace.tool_calls.append(
            ToolCall(name=name, arguments=arguments or {}, ok=ok,
                     has_result=has_result, used_in_output=used_in_output)
        )

    def set_output(self, text: str) -> None:
        self._trace.final_output = text

    def annotate(self, *, result_used: bool | None = None,
                 fabricated: bool | None = None, answer_correct: bool | None = None) -> None:
        """Điền nhãn judge (heuristic/LLM/tay) trước khi gửi."""

        if result_used is not None:
            self._trace.result_used = result_used
        if fabricated is not None:
            self._trace.fabricated = fabricated
        if answer_correct is not None:
            self._trace.answer_correct = answer_correct

    def build(self) -> AgentRunTrace:
        return self._trace


class TelemetryClient:
    """Gửi trace về collector của Rating Agent (khung).

    ``api_key`` được cấp khi đăng ký agent (xem AGENT_INTEGRATION.md).
    """

    def __init__(self, endpoint: str, api_key: str, *, timeout: int = 10) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    def report(self, trace: AgentRunTrace) -> None:
        """POST trace dạng JSON lên collector (khung)."""

        resp = requests.post(
            f"{self._endpoint}/v1/traces",
            json=trace.model_dump(),
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        logger.debug("Đã gửi trace %s", trace.run_id)
