"""Client Whisper transcript — chỉ stdlib (container agent không cài thêm gì).

Server: POST /transcribe (multipart) → {job_id} → poll GET /result/{job_id} tới khi
status=done. Base URL lấy từ env ``LSR_TRANSCRIBE_URL``.

Chủ file: **Hương** (xem TEAM.md). Sửa file này không ảnh hưởng knowledge.py / consumer.py.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://slashingly-unexistent-hue.ngrok-free.dev"
_HEADERS = {"ngrok-skip-browser-warning": "true"}


class TranscribeError(RuntimeError):
    """Transcript thất bại — caller phải fail job để vào DLQ, KHÔNG trả biên bản rỗng."""


def _base_url() -> str:
    return os.environ.get("LSR_TRANSCRIBE_URL", DEFAULT_BASE_URL).rstrip("/")


def _multipart(fields: dict[str, str], filename: str, blob: bytes) -> tuple[bytes, str]:
    """Đóng gói multipart/form-data bằng stdlib."""
    boundary = "----lsr-sq-thailand-boundary"
    out = bytearray()
    for key, val in fields.items():
        out += (f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n{val}\r\n').encode()
    out += (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n").encode()
    out += blob + f"\r\n--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def submit(blob: bytes, *, filename: str = "meeting.m4a", language: str = "vi",
           meeting_title: str = "") -> str:
    """Gửi file lên server → trả job_id."""
    fields = {"task": "transcribe", "language": language}
    if meeting_title:
        fields["meeting_title"] = meeting_title
    body, content_type = _multipart(fields, filename, blob)
    req = urllib.request.Request(f"{_base_url()}/transcribe", data=body, method="POST",
                                 headers={**_HEADERS, "Content-Type": content_type})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode() or "{}")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise TranscribeError(f"submit thất bại: {exc}") from exc
    job_id = data.get("job_id")
    if not job_id:
        raise TranscribeError(f"server không trả job_id: {data}")
    return str(job_id)


def wait(job_id: str, *, timeout: int = 900, interval: int = 10) -> str:
    """Poll tới khi có transcript. Quá hạn/lỗi → TranscribeError (job vào DLQ)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        req = urllib.request.Request(f"{_base_url()}/result/{job_id}", headers=_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode() or "{}")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise TranscribeError(f"poll thất bại: {exc}") from exc
        status = (data.get("status") or "").lower()
        if status == "done":
            text = (data.get("transcript") or "").strip()
            if not text:
                raise TranscribeError("transcript rỗng")
            return text
        if status in ("error", "failed"):
            raise TranscribeError(f"server báo lỗi: {data.get('error') or status}")
        time.sleep(interval)
    raise TranscribeError(f"quá hạn {timeout}s chờ transcript")


def health() -> dict:
    req = urllib.request.Request(f"{_base_url()}/health", headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode() or "{}")
