"""Lấy transcript từ recording. Phase 3, Thái.

CHƯA IMPLEMENT. Đang chờ xác nhận Whisper server của platform có bật hay không.

Env cần: LSR_TRANSCRIBE_URL (server Whisper large-v3 của platform).

Có sẵn để tham khảo: src/rating_agent/meeting/transcribe.py trong core làm đúng việc này
(POST /transcribe rồi poll /result/{job_id}). ĐỌC để học cách gọi, nhưng KHÔNG import từ đó
và KHÔNG sửa file đó — nằm ngoài phạm vi agent, sẽ bị scope-guard chặn. Copy phần cần dùng
vào đây.

Việc cần làm:
  D8 — server chết hoặc timeout: raise TranscribeError, KHÔNG mất recording, cho thử lại
  Phase 3 làm đường text trước (dán transcript thô), audio sau — rẻ hơn và không phụ thuộc
  vào việc Whisper server có sẵn sàng
"""

from __future__ import annotations


class TranscribeError(RuntimeError):
    """Không lấy được transcript. Recording vẫn còn, cho phép thử lại."""


def transcribe_file(file_ref: str, *, timeout_s: int = 900) -> str:
    """Gửi recording tới Whisper server, chờ xong, trả transcript."""
    raise NotImplementedError("Phase 3 — xem docstring module")
