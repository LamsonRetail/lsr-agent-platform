"""Data model cho Resource Index — tài nguyên (file/link) được share cho agent.

Nguyên tắc: **KHÔNG nhồi vào memory/context của agent** (tránh long-memory). Khi
agent được share file/link, nó gọi index để lưu **metadata + nội dung tóm tắt** ra
kho ngoài (collector/Postgres), rồi truy xuất lại bằng **search** khi cần.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SharedResource(BaseModel):
    """Một tài nguyên được share cho agent và đã index."""

    resource_id: str
    agent_id: str
    kind: str = "link"  # "file" | "link"
    title: str = ""
    uri: str = ""  # URL link, hoặc path/drive-id của file
    mime: str = ""
    folder: str = ""  # thư mục logic, ví dụ "meeting-notes"
    tags: list[str] = Field(default_factory=list)
    summary: str = ""  # tóm tắt nội dung để search (không lưu full text vào memory)
    shared_by: str = ""
    shared_at: str = ""  # ISO datetime

    def haystack(self) -> str:
        return " ".join(
            [self.title, self.summary, " ".join(self.tags), self.uri]
        ).lower()
