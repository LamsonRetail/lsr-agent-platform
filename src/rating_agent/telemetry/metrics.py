"""Tính các chỉ số hành vi tool + thống kê token từ trace.

Sáu chỉ số (theo bảng đề bài) — tất cả là tỉ lệ 0..1:

Required set (task CẦN tool):
  - TSR  (Tool-Skip Rate)        : bỏ qua tool đáng lẽ phải dùng.        ↓ tốt
  - CTUR (Clean Tool-Use Rate)   : dùng tool "sạch" (đúng tool, không lỗi). ↑ tốt
  - RIR  (Result-Ignore Rate)    : gọi tool có kết quả nhưng output phớt lờ. ↓ tốt
  - OFR  (Output-Fabrication Rate): output bịa thông tin ngoài kết quả tool. ↓ tốt

Control set (task KHÔNG cần tool):
  - UTR      (Unnecessary-Tool-Use Rate): vẫn gọi tool dù không cần.     ↓ tốt
  - CTRL-Acc (Control Accuracy)          : trả lời đúng khi không cần tool. ↑ tốt

Đây là *thao tác hoá* (operationalization) rõ ràng, có thể chỉnh cho khớp định
nghĩa gốc của bài báo qua tham số. Trả về ``None`` khi mẫu số = 0 (không xác định).
"""

from __future__ import annotations

from dataclasses import dataclass

from .trace import AgentRunTrace, TaskLabel


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator  # giữ đủ độ chính xác; làm tròn khi hiển thị


def is_clean_tool_use(trace: AgentRunTrace, label: TaskLabel) -> bool:
    """Lượt dùng tool 'sạch': có gọi tool, gọi đúng tool kỳ vọng, mọi call OK.

    Không xét việc output có dùng kết quả hay không (đó là RIR). Có thể siết thêm
    'không gọi thừa tool' bằng cách bật ``strict`` ở phiên bản sau.
    """

    if not trace.used_any_tool:
        return False
    if not all(t.ok for t in trace.tool_calls):
        return False
    if label.expected_tool and label.expected_tool not in trace.called_tool_names:
        return False
    return True


@dataclass
class BehaviorMetrics:
    """Kết quả 6 chỉ số + số lượng mẫu. Giá trị rate là 0..1 hoặc None."""

    tsr: float | None
    ctur: float | None
    rir: float | None
    ofr: float | None
    utr: float | None
    ctrl_acc: float | None
    n_required: int
    n_control: int

    def as_percent(self) -> dict[str, float | None]:
        def pct(v: float | None) -> float | None:
            return None if v is None else round(v * 100, 2)

        return {
            "TSR": pct(self.tsr),
            "CTUR": pct(self.ctur),
            "RIR": pct(self.rir),
            "OFR": pct(self.ofr),
            "UTR": pct(self.utr),
            "CTRL-Acc": pct(self.ctrl_acc),
        }


def compute_behavior_metrics(
    traces: list[AgentRunTrace],
    labels: dict[str, TaskLabel],
) -> BehaviorMetrics:
    """Tính 6 chỉ số từ danh sách trace (đã gắn task_id) và nhãn task."""

    required = [t for t in traces if labels.get(t.task_id) and labels[t.task_id].needs_tool]
    control = [t for t in traces if labels.get(t.task_id) and not labels[t.task_id].needs_tool]

    # ----- Required -----
    n_req = len(required)
    skipped = sum(1 for t in required if not t.used_any_tool)
    clean = sum(1 for t in required if is_clean_tool_use(t, labels[t.task_id]))
    fabricated = sum(1 for t in required if t.fabricated is True)

    # RIR: chỉ tính trên các lượt có gọi tool và có kết quả dùng được.
    with_result = [t for t in required if t.has_any_result]
    ignored = sum(1 for t in with_result if t.result_used is False)

    tsr = _rate(skipped, n_req)
    ctur = _rate(clean, n_req)
    rir = _rate(ignored, len(with_result))
    ofr = _rate(fabricated, n_req)

    # ----- Control -----
    n_ctrl = len(control)
    unnecessary = sum(1 for t in control if t.used_any_tool)
    correct = sum(1 for t in control if _answer_correct(t, labels[t.task_id]))

    utr = _rate(unnecessary, n_ctrl)
    ctrl_acc = _rate(correct, n_ctrl)

    return BehaviorMetrics(
        tsr=tsr, ctur=ctur, rir=rir, ofr=ofr, utr=utr, ctrl_acc=ctrl_acc,
        n_required=n_req, n_control=n_ctrl,
    )


def _answer_correct(trace: AgentRunTrace, label: TaskLabel) -> bool:
    """Ưu tiên nhãn trên trace; nếu không có thì lấy nhãn task."""

    if trace.answer_correct is not None:
        return trace.answer_correct
    return bool(label.answer_correct)


# ----------------------------- Token -----------------------------


@dataclass
class TokenStats:
    """Thống kê token theo một tập trace (ví dụ 1 agent trong 1 kỳ)."""

    runs: int
    input_tokens: int
    output_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def avg_tokens_per_run(self) -> float:
        return round(self.total_tokens / self.runs, 1) if self.runs else 0.0


def compute_token_stats(traces: list[AgentRunTrace]) -> TokenStats:
    return TokenStats(
        runs=len(traces),
        input_tokens=sum(t.input_tokens for t in traces),
        output_tokens=sum(t.output_tokens for t in traces),
    )
