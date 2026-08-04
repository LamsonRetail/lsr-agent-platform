"""Data model cho telemetry của agent: trace một lần chạy + nhãn task.

Trace là dữ liệu gốc để tính token, log, kết quả, và các chỉ số hành vi tool
(TSR/CTUR/RIR/OFR/UTR/CTRL-Acc). Agent trên VPS ghi lại trace này (qua SDK) và
gửi về collector; hoặc test runner sinh ra trace khi chạy bộ test có nhãn.

Các trường do "judge" điền (``result_used``, ``fabricated``, ``answer_correct``,
``used_in_output``) cần bước đánh giá ngữ nghĩa — giai đoạn sau dùng LLM judge;
hiện có thể điền bằng heuristic hoặc nhãn tay.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LLMCall(BaseModel):
    """Một lời gọi mô hình (để đếm token)."""

    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class ToolCall(BaseModel):
    """Một lời gọi tool trong lượt chạy."""

    name: str
    arguments: dict = Field(default_factory=dict)
    ok: bool = True  # thực thi không lỗi
    has_result: bool = True  # trả về kết quả không rỗng
    # Judge: kết quả tool này có được dùng trong output cuối không.
    used_in_output: bool | None = None


class AgentRunTrace(BaseModel):
    """Toàn bộ dấu vết một lượt chạy agent."""

    run_id: str
    agent_id: str
    task_id: str = ""  # liên kết test case (khi source='test') hoặc phiên production
    source: str = "production"  # "test" | "production"
    llm_calls: list[LLMCall] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    final_output: str = ""
    # --- Judge-populated ---
    result_used: bool | None = None  # output có dùng kết quả tool không (mức lượt)
    fabricated: bool | None = None  # output có bịa thông tin ngoài kết quả tool
    answer_correct: bool | None = None  # đáp án đúng (dùng cho CTRL-Acc)
    started_at: str = ""
    finished_at: str = ""

    # -- Token --
    @property
    def input_tokens(self) -> int:
        return sum(c.input_tokens for c in self.llm_calls)

    @property
    def output_tokens(self) -> int:
        return sum(c.output_tokens for c in self.llm_calls)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    # -- Tool --
    @property
    def called_tool_names(self) -> set[str]:
        return {t.name for t in self.tool_calls}

    @property
    def used_any_tool(self) -> bool:
        return len(self.tool_calls) > 0

    @property
    def has_any_result(self) -> bool:
        return any(t.ok and t.has_result for t in self.tool_calls)


class TaskLabel(BaseModel):
    """Nhãn ground-truth cho một task trong bộ đánh giá.

    ``needs_tool`` phân tách Required set (cần tool) và Control set (không cần).
    ``expected_tool`` là tool đúng cần dùng (nếu có).
    """

    task_id: str
    needs_tool: bool
    expected_tool: str | None = None
    answer_correct: bool | None = None  # nhãn đúng/sai đáp án (nếu chấm sẵn)
