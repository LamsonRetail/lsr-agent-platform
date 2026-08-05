"""Runtime Lark bot cho Minh Anh — gửi tin nhắn, tạo task, orchestrate workflow.

Tái dùng :class:`LarkClient` (tenant_access_token). Ghép với ``TranscribeClient``
và resource index để chạy trọn hành vi B:
  transcript → biên bản nháp → xin owner confirm → (confirm) tạo task + lưu biên bản.

Sự kiện Lark (được add vào họp / tin nhắn confirm) đến từ Event Subscription; ở đây
xử lý logic + gọi API. Phần nhận sự kiện: webhook (cần HTTPS công khai) hoặc
long-connection SDK — xem WORKFLOW.
"""

from __future__ import annotations

import json
from typing import Any

from ..lark import LarkClient
from .minh_anh import MeetingMinutes, MinutesStatus


class MinhAnhBot:
    """Bọc LarkClient cho các thao tác của Minh Anh."""

    def __init__(self, client: LarkClient, *, transcribe=None, index=None) -> None:
        self.client = client
        self.transcribe = transcribe
        self.index = index

    # -------- Lark IM --------
    def send_text(self, receive_id: str, text: str, *, receive_id_type: str = "chat_id") -> dict:
        return self.client.post(
            f"/im/v1/messages?receive_id_type={receive_id_type}",
            json_body={
                "receive_id": receive_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        )

    def list_chats(self) -> list[dict]:
        return self.client.get("/im/v1/chats").get("items", [])

    # -------- Lark Task --------
    def create_task(self, summary: str, *, due_ms: str | None = None) -> dict:
        body: dict[str, Any] = {"summary": summary}
        if due_ms:
            body["due"] = {"timestamp": due_ms, "is_all_day": False}
        return self.client.post("/task/v2/tasks", json_body=body)

    # -------- Biên bản --------
    @staticmethod
    def format_minutes(m: MeetingMinutes) -> str:
        lines = [f"📝 Biên bản: {m.title or m.meeting_id}"]
        if m.key_points:
            lines.append("Nội dung chính:")
            lines += [f"  • {p}" for p in m.key_points]
        if m.decisions:
            lines.append("Quyết định:")
            lines += [f"  • {d}" for d in m.decisions]
        if m.tasks:
            lines.append("Task đề xuất:")
            lines += [f"  • {t.title}" + (f" (→ {t.assignee})" if t.assignee else "") for t in m.tasks]
        return "\n".join(lines)

    def ask_confirm(self, owner_receive_id: str, minutes: MeetingMinutes,
                    *, receive_id_type: str = "open_id") -> dict:
        """Gửi biên bản nháp cho owner và xin confirm (đặt trạng thái awaiting_confirm)."""

        minutes.request_confirm()
        text = self.format_minutes(minutes) + (
            "\n\n👉 Trả lời 'confirm' để chốt biên bản và tạo task, hoặc góp ý để sửa."
        )
        return self.send_text(owner_receive_id, text, receive_id_type=receive_id_type)

    def on_confirm(self, minutes: MeetingMinutes, *, minutes_uri: str = "") -> list[dict]:
        """Owner đã confirm → tạo task + lưu biên bản vào meeting-notes index."""

        if minutes.status != MinutesStatus.AWAITING_CONFIRM:
            raise RuntimeError("Chỉ tạo task sau khi đã xin confirm (awaiting_confirm).")
        minutes.confirm()
        created = [self.create_task(t.title, due_ms=t.due or None) for t in minutes.tasks]
        if self.index is not None:
            res = minutes.as_resource(uri=minutes_uri)
            (self.index.add if hasattr(self.index, "add") else self.index.index)(res)
        return created

    def transcribe_recording(self, **kwargs) -> str:
        if self.transcribe is None:
            raise RuntimeError("Chưa cấu hình TranscribeClient")
        kwargs.setdefault("language", "vi")
        return self.transcribe.transcribe_and_wait(**kwargs)

    # -------- Event handling --------
    @staticmethod
    def handle_event(body: dict) -> dict | None:
        """Xử lý payload event của Lark.

        - URL verification: trả về {'challenge': ...}.
        - Event thật: trả về dict mô tả hành động cần làm (để orchestrator xử lý),
          hoặc None nếu bỏ qua.
        """

        if body.get("type") == "url_verification":
            return {"challenge": body.get("challenge", "")}
        header = body.get("header", {})
        event_type = header.get("event_type", "")
        if event_type == "im.message.receive_v1":
            msg = body.get("event", {}).get("message", {})
            content = msg.get("content", "")
            text = ""
            try:
                text = json.loads(content).get("text", "")
            except Exception:
                text = content
            return {"action": "message", "text": text.strip(), "message": msg}
        return {"action": "ignore", "event_type": event_type}
