"""Resource Index — lưu & tra cứu file/link được share (ngoài memory)."""

from .index import ResourceIndex, ResourceIndexClient
from .models import SharedResource

__all__ = ["SharedResource", "ResourceIndex", "ResourceIndexClient"]
