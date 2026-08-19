"""Ghép prompt và gọi model.

Prompt là stateless: platform giữ lịch sử hội thoại, agent dựng lại ngữ cảnh mỗi lượt từ
`/v1/self/context`. Không giữ state trong bộ nhớ process — restart hay đổi máy vẫn liền mạch.
"""

from __future__ import annotations


def build_prompt(ctx: dict, question: str) -> str:
    """Ghép ngữ cảnh từ platform thành prompt."""
    parts: list[str] = []
    if ctx.get("instruction_block"):
        parts.append(ctx["instruction_block"])
    if ctx.get("rolling_summary"):
        parts.append("Tóm tắt hội thoại trước:\n" + ctx["rolling_summary"])
    if ctx.get("user_facts"):
        parts.append("Đã biết về người dùng:\n- " + "\n- ".join(ctx["user_facts"]))
    if ctx.get("knowledge"):
        parts.append(
            "Tri thức đã được duyệt (TRÍCH DẪN nguồn khi dùng, không dùng kiến thức ngoài "
            "danh sách này để trả lời câu hỏi quy định nội bộ):\n"
            + "\n".join(
                f"- {h['title']}: {h['content'][:300]} (nguồn: {h.get('source_url') or 'nội bộ'})"
                for h in ctx["knowledge"]
            )
        )
    for turn in ctx.get("recent_turns", []):
        parts.append(f"{turn['role']}: {turn['text']}")
    parts.append(f"user: {question}")
    return "\n\n".join(parts)


def complete(prompt: str) -> str:
    """Gọi model qua Claude Agent SDK với credential lease từ platform.

    CHƯA IMPLEMENT. Cần: subscription của owner (`claude setup-token`) và luồng lease
    credential `/v1/self/model-auth/lease`. Xem AGENT_INTEGRATION.md ở gốc repo.
    """
    raise NotImplementedError("Phase 1 — xem docstring")
