"""Khung dịch vụ Lark Chat — tham gia/theo dõi nhóm chat và trích tín hiệu phối hợp.

Endpoint tham khảo:
- Danh sách nhóm bot tham gia:  GET /im/v1/chats
- Tin nhắn trong nhóm:          GET /im/v1/messages?container_id_type=chat&container_id=<chat_id>

Bản MVP: chữ ký hàm + luồng phân trang. Trả về cấu trúc dữ liệu chuẩn để lớp
đánh giá tiêu thụ; phần gọi API thật cần credential.
"""

from __future__ import annotations

from dataclasses import dataclass

from .client import LarkClient


@dataclass
class ChatSignal:
    """Tín hiệu phối hợp trích từ chat, quy về một nhân viên."""

    lark_user_id: str
    messages_sent: int = 0
    mentions_received: int = 0
    mentions_responded: int = 0
    avg_response_seconds: float | None = None

    @property
    def response_rate(self) -> float:
        if self.mentions_received == 0:
            return 0.0
        return self.mentions_responded / self.mentions_received


class LarkChatService:
    """Trích tín hiệu collaboration từ các nhóm chat."""

    def __init__(self, client: LarkClient) -> None:
        self._client = client

    def list_chats(self, page_size: int = 50) -> list[dict]:
        """Liệt kê các nhóm chat mà bot đang tham gia.

        Khung: hiện gọi trực tiếp API; cần token hợp lệ để chạy thật.
        """

        data = self._client.get("/im/v1/chats", params={"page_size": page_size})
        return data.get("items", [])

    def iter_messages(self, chat_id: str, page_size: int = 50) -> list[dict]:
        """Lấy tin nhắn của một nhóm (khung, chưa xử lý phân trang đầy đủ)."""

        data = self._client.get(
            "/im/v1/messages",
            params={
                "container_id_type": "chat",
                "container_id": chat_id,
                "page_size": page_size,
            },
        )
        return data.get("items", [])

    def collect_signals(self, chat_ids: list[str]) -> dict[str, ChatSignal]:
        """Tổng hợp tín hiệu chat theo nhân viên.

        TODO(giai đoạn 2): tính mentions/response-time thật từ nội dung message.
        Hiện trả về khung rỗng để pipeline chạy end-to-end với dữ liệu mẫu.
        """

        signals: dict[str, ChatSignal] = {}
        for chat_id in chat_ids:
            for _msg in self.iter_messages(chat_id):
                # Điểm cắm để phân tích message → cập nhật ChatSignal.
                pass
        return signals
