"""Sinh bài test tự động từ tài liệu training / skill.

- Có LLM: truyền callable ``llm(prompt) -> str`` (JSON câu hỏi) → parse.
- Không LLM (offline/test): fallback heuristic tạo câu hỏi thô từ tài liệu.

Bài sinh ra LUÔN ở trạng thái DRAFT (source=auto) → phải người review mới active.
"""

from __future__ import annotations

import json
import re

from .grader import new_auto_draft
from .models import Question, Test


def _build_prompt(material_md: str, skill: str, n: int) -> str:
    return (
        f"Bạn là người ra đề. Từ tài liệu training dưới đây, hãy tạo {n} câu hỏi "
        f"kiểm tra kiến thức (skill: {skill or 'chung'}).\n"
        "Trả về DUY NHẤT một mảng JSON, mỗi phần tử: "
        '{"prompt": "...", "expected": "...", "assertion_type": "contains"}.\n\n'
        f"--- TÀI LIỆU ---\n{material_md}\n--- HẾT ---"
    )


def _extract_json_array(text: str) -> list:
    """Lấy mảng JSON đầu tiên trong chuỗi trả về của LLM."""

    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("Không tìm thấy mảng JSON trong output LLM")
    return json.loads(text[start : end + 1])


def parse_llm_questions(text: str, *, skill: str = "") -> list[Question]:
    """Parse output JSON của LLM thành list Question."""

    items = _extract_json_array(text)
    questions: list[Question] = []
    for i, it in enumerate(items):
        questions.append(
            Question(
                question_id=f"q{i + 1}",
                prompt=str(it.get("prompt", "")).strip(),
                expected=str(it.get("expected", "")).strip(),
                assertion_type=str(it.get("assertion_type", "contains")),
                skill_id=skill,
                tags=[skill] if skill else [],
            )
        )
    return [q for q in questions if q.prompt and q.expected]


def _salient(line: str) -> str:
    tokens = re.findall(r"[0-9A-Za-zÀ-ỹ_]+", line)
    return max(tokens, key=len) if tokens else ""


def heuristic_questions(material_md: str, *, skill: str = "", n: int = 3) -> list[Question]:
    """Fallback không LLM: tạo câu hỏi 'khớp từ khoá' từ các dòng nội dung.

    Chỉ là placeholder cho demo/offline — chất lượng thật cần LLM.
    """

    lines = [
        l.strip() for l in material_md.splitlines()
        if l.strip() and not l.strip().startswith("#")
    ]
    questions: list[Question] = []
    for i, line in enumerate(lines[:n]):
        key = _salient(line)
        if not key:
            continue
        questions.append(
            Question(
                question_id=f"q{i + 1}",
                prompt=f"Theo tài liệu, nội dung sau đề cập tới điều gì: “{line}”?",
                expected=key,
                assertion_type="contains",
                skill_id=skill,
                tags=[skill] if skill else [],
            )
        )
    return questions


def generate_questions(material_md: str, *, skill: str = "", n: int = 3, llm=None) -> list[Question]:
    if llm is not None:
        return parse_llm_questions(llm(_build_prompt(material_md, skill, n)), skill=skill)
    return heuristic_questions(material_md, skill=skill, n=n)


def build_draft_test(
    test_id: str, title: str, material_md: str, *, skill: str = "", n: int = 3, llm=None
) -> Test:
    """Sinh bài test DRAFT (auto) từ tài liệu — chờ người review."""

    questions = generate_questions(material_md, skill=skill, n=n, llm=llm)
    return new_auto_draft(test_id, title, questions, created_by="llm-generator")
