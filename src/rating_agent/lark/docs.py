"""Khung dịch vụ Lark Document — theo dõi đóng góp tài liệu.

Endpoint tham khảo:
- Docx:  GET /docx/v1/documents/<document_id>
- Wiki:  GET /wiki/v2/spaces/<space_id>/nodes

Trích tín hiệu: số tài liệu tạo/đồng tác giả, comment hữu ích, tài liệu học tập.
"""

from __future__ import annotations

from dataclasses import dataclass

from .client import LarkClient


@dataclass
class DocSignal:
    """Tín hiệu đóng góp tài liệu, quy về một nhân viên."""

    lark_user_id: str
    docs_authored: int = 0
    docs_coauthored: int = 0
    comments_made: int = 0
    learning_docs: int = 0


class LarkDocService:
    """Trích tín hiệu collaboration/grow từ document."""

    def __init__(self, client: LarkClient) -> None:
        self._client = client

    def get_document(self, document_id: str) -> dict:
        """Lấy metadata một tài liệu (khung)."""

        return self._client.get(f"/docx/v1/documents/{document_id}")

    def list_wiki_nodes(self, space_id: str) -> list[dict]:
        """Liệt kê node trong một wiki space (khung)."""

        data = self._client.get(f"/wiki/v2/spaces/{space_id}/nodes")
        return data.get("items", [])

    def collect_signals(self, document_ids: list[str]) -> dict[str, DocSignal]:
        """Tổng hợp tín hiệu tài liệu theo nhân viên (khung).

        TODO(giai đoạn 2): đọc lịch sử chỉnh sửa/tác giả để tính đóng góp thật.
        """

        signals: dict[str, DocSignal] = {}
        for doc_id in document_ids:
            _ = self.get_document(doc_id)
            # Điểm cắm: map tác giả/collaborator → cập nhật DocSignal.
        return signals
