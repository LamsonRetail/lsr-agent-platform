"""Biên bản họp — dựng nháp từ transcript, giữ gate xác nhận của chủ trì.

Vòng đời:  draft → awaiting_confirm → (chủ trì "chốt") → confirmed
**Không** tạo task / không lưu kho khi chưa confirmed (TESTCASES 3.4).

Nháp KHÔNG giữ trong tiến trình: nó nằm trong lượt hội thoại do platform lưu
(`/v1/self/session/turn`), nên restart/đổi máy vẫn chốt được — tìm lại bằng
``find_draft(ctx)``.

Chủ file: **Hương** (xem TEAM.md). Chỉ stdlib.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

DRAFT = "draft"
AWAITING_CONFIRM = "awaiting_confirm"
CONFIRMED = "confirmed"

HEADER = "BIÊN BẢN —"

CONFIRM_WORDS = ("chốt", "chot", "duyệt", "duyet", "confirm", "ok biên bản")
DECISION_WORDS = ("quyết định", "chốt là", "thống nhất", "đồng ý", "kết luận")
TASK_WORDS = ("giao cho", "phụ trách", "deadline", "hạn", "trước ngày", "cần làm")
_NAME = r"[A-ZĐÀ-Ỹ][\wÀ-ỹ]*(?:\s+[A-ZĐÀ-Ỹ][\wÀ-ỹ]*)?"
_ASSIGNEE = re.compile(rf"(?:giao cho|nhờ)\s+({_NAME})", re.IGNORECASE)
_ASSIGNEE_PRE = re.compile(rf"({_NAME})\s+phụ trách", re.IGNORECASE)
_DUE = re.compile(r"(?:hạn|trước ngày|deadline)\s*:?\s*([0-9]{1,2}[/-][0-9]{1,2}(?:[/-][0-9]{2,4})?)",
                  re.IGNORECASE)


@dataclass
class Task:
    what: str
    who: str = "chưa rõ"
    due: str = "chưa rõ"


@dataclass
class Minutes:
    title: str
    context: str = ""
    key_points: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    status: str = DRAFT

    def render(self) -> str:
        lines = [f"{HEADER} {self.title}"]
        if self.context:
            lines.append(f"Bối cảnh: {self.context}")
        lines.append("Nội dung chính:")
        lines += [f"  - {p}" for p in self.key_points] or ["  - (chưa trích được ý chính)"]
        lines.append("Quyết định:")
        lines += [f"  - {d}" for d in self.decisions] or ["  - (không có quyết định nào được nêu rõ)"]
        lines.append("Đầu việc:")
        lines += [f"  - {t.what} — {t.who} — hạn {t.due}" for t in self.tasks] or ["  - (chưa có)"]
        lines.append(f"Trạng thái: {_status_vi(self.status)}")
        return "\n".join(lines)


def _status_vi(status: str) -> str:
    return {DRAFT: "nháp", AWAITING_CONFIRM: "chờ xác nhận", CONFIRMED: "đã chốt"}.get(status, status)


def _sentences(transcript: str) -> list[str]:
    parts = re.split(r"[.\n?!]+", transcript)
    return [s.strip() for s in parts if len(s.strip()) > 12]


def build_draft(transcript: str, title: str) -> Minutes:
    """Dựng biên bản nháp từ transcript.

    Bản nền dùng luật (chạy được ngay, test được). Khi nối model: giữ nguyên chữ ký hàm,
    thay ruột bằng lời gọi model với ``prompt_for(transcript, title)`` rồi parse về Minutes.
    """
    sents = _sentences(transcript)
    m = Minutes(title=title, context=sents[0][:200] if sents else "")

    for s in sents:
        low = s.lower()
        if any(w in low for w in DECISION_WORDS):
            m.decisions.append(s[:200])
        elif any(w in low for w in TASK_WORDS):
            who = _ASSIGNEE.search(s) or _ASSIGNEE_PRE.search(s)
            due = _DUE.search(s)
            m.tasks.append(Task(what=s[:200],
                                who=who.group(1) if who else "chưa rõ",
                                due=due.group(1) if due else "chưa rõ"))
        elif len(m.key_points) < 8:
            m.key_points.append(s[:200])

    m.status = AWAITING_CONFIRM
    return m


def prompt_for(transcript: str, title: str) -> str:
    """Prompt dùng khi thay build_draft bằng lời gọi model (Claude Agent SDK)."""
    return (
        f"Dựng biên bản cuộc họp \"{title}\" của squad Thái Lan từ transcript dưới đây.\n"
        "Trả về đúng các mục: Bối cảnh · Nội dung chính · Quyết định · Đầu việc "
        "(việc — ai — hạn). Chỉ ghi điều CÓ trong transcript, không suy diễn. "
        "Không rõ ai/hạn thì ghi 'chưa rõ'.\n\n"
        f"--- TRANSCRIPT ---\n{transcript}"
    )


def is_confirm(text: str) -> bool:
    return any(w in text.lower().strip() for w in CONFIRM_WORDS)


def find_draft(ctx: dict) -> str | None:
    """Tìm biên bản nháp gần nhất trong lượt hội thoại platform trả về."""
    for turn in reversed(ctx.get("recent_turns") or []):
        if turn.get("role") == "assistant" and HEADER in (turn.get("text") or ""):
            return turn["text"]
    return None


def confirm(draft_text: str) -> str:
    """Đổi nháp đã có sang trạng thái đã chốt (giữ nguyên nội dung)."""
    return draft_text.replace(f"Trạng thái: {_status_vi(AWAITING_CONFIRM)}",
                              f"Trạng thái: {_status_vi(CONFIRMED)}")


def task_lines(draft_text: str) -> list[str]:
    """Trích các dòng đầu việc từ biên bản để ĐỀ XUẤT task (không tự tạo)."""
    out, inside = [], False
    for line in draft_text.splitlines():
        if line.startswith("Đầu việc:"):
            inside = True
            continue
        if inside:
            if line.startswith("Trạng thái:"):
                break
            item = line.strip().lstrip("- ").strip()
            if item and not item.startswith("("):
                out.append(item)
    return out
