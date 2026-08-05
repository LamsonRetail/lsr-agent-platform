"""Logic của Meeting Agent "Minh Anh".

Hai hành vi chính:
1. Khi có agent mới register → Minh Anh **share "từ điển" thư mục meeting-notes**
   cho agent đó (một mục trong resource index để agent mới tra cứu biên bản cũ).
2. Khi được add vào cuộc họp → **viết biên bản** (transcript + nội dung chính),
   **xin meeting owner confirm**, rồi **tạo task**.

Phần transcript/tạo task thật chạy qua Lark MCP lúc runtime; ở đây định nghĩa
data model + các bước + hàm share dictionary (đã nối được với resource index).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..resources import SharedResource

MEETING_NOTES_FOLDER = "meeting-notes"
MINH_ANH_ID = "AG-MINH-ANH"


# ---------------- Hành vi 1: share "từ điển" meeting-notes ----------------

def build_dictionary_resource(
    new_agent_id: str,
    *,
    uri: str = "lark://drive/folder/meeting-notes",
    shared_at: str = "",
) -> SharedResource:
    """Tạo mục 'từ điển' thư mục meeting-notes để share cho một agent mới."""

    return SharedResource(
        resource_id=f"dict-meeting-notes::{new_agent_id}",
        agent_id=new_agent_id,
        kind="folder",
        title="Meeting Notes Dictionary",
        uri=uri,
        folder=MEETING_NOTES_FOLDER,
        tags=["meeting-notes", "dictionary", "index"],
        summary=(
            "Danh mục/thư mục biên bản họp do Minh Anh quản lý. Tra cứu biên bản "
            "cũ, quyết định và task của các cuộc họp tại đây (qua resource index)."
        ),
        shared_by="Minh Anh",
        shared_at=shared_at,
    )


def share_dictionary_to(index, new_agent_id: str, **kwargs) -> SharedResource:
    """Share từ điển meeting-notes vào một resource index.

    ``index`` chấp nhận cả ``ResourceIndex`` (có ``.add``) lẫn
    ``ResourceIndexClient`` (có ``.index``).
    """

    resource = build_dictionary_resource(new_agent_id, **kwargs)
    if hasattr(index, "add"):
        index.add(resource)
    elif hasattr(index, "index"):
        index.index(resource)
    else:  # pragma: no cover
        raise TypeError("index phải có .add hoặc .index")
    return resource


# ---------------- Hành vi 2: viết biên bản họp ----------------

class MinutesStatus:
    DRAFT = "draft"
    AWAITING_CONFIRM = "awaiting_confirm"
    CONFIRMED = "confirmed"


@dataclass
class MeetingTask:
    """Một task rút ra từ cuộc họp."""

    title: str
    assignee: str = ""
    due: str = ""


@dataclass
class MeetingMinutes:
    """Biên bản họp do Minh Anh soạn."""

    meeting_id: str
    title: str = ""
    owner: str = ""  # meeting owner (người confirm)
    transcript: str = ""
    key_points: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    tasks: list[MeetingTask] = field(default_factory=list)
    status: str = MinutesStatus.DRAFT

    def request_confirm(self) -> None:
        self.status = MinutesStatus.AWAITING_CONFIRM

    def confirm(self) -> None:
        self.status = MinutesStatus.CONFIRMED

    def as_resource(self, *, uri: str = "", shared_at: str = "") -> SharedResource:
        """Đưa biên bản đã confirm vào resource index (folder meeting-notes)."""

        return SharedResource(
            resource_id=f"minutes::{self.meeting_id}",
            agent_id=MINH_ANH_ID,
            kind="link",
            title=self.title or f"Biên bản họp {self.meeting_id}",
            uri=uri,
            folder=MEETING_NOTES_FOLDER,
            tags=["meeting-notes", "minutes"],
            summary=" • ".join(self.key_points[:5]),
            shared_by="Minh Anh",
            shared_at=shared_at,
        )


# Các bước workflow (dùng cho tài liệu + orchestration runtime qua Lark MCP).
MEETING_WORKFLOW_STEPS = (
    "1. Lấy transcript cuộc họp (Lark minutes).",
    "2. Trích nội dung chính: key_points, decisions.",
    "3. Soạn biên bản (draft) và tạo task đề xuất.",
    "4. Gửi meeting owner xin CONFIRM biên bản.",
    "5. Sau khi confirm: tạo task trên Lark Task + lưu biên bản vào meeting-notes (index).",
)
