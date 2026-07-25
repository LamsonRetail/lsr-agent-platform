"""Khung kết nối Lark: client xác thực + wrapper chat/document/task.

Bản MVP cung cấp interface rõ ràng. Các phương thức gọi API thật đã có chữ ký
và ví dụ endpoint nhưng đánh dấu là khung — cần credential thật để chạy.
"""

from .client import LarkClient
from .chat import LarkChatService
from .docs import LarkDocService
from .task import LarkTaskService

__all__ = [
    "LarkClient",
    "LarkChatService",
    "LarkDocService",
    "LarkTaskService",
]
