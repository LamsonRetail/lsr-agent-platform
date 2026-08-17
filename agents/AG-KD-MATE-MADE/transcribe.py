"""Client Whisper Transcription Server — module riêng của AG-KD-MATE-MADE.

Server nhận file audio/video → hàng đợi → trả ``job_id``; poll ``/result/{job_id}`` tới
khi ``status=done`` để lấy ``transcript``.

**Không hardcode URL server.** Bản trong core (`src/rating_agent/meeting/transcribe.py`)
mặc định trỏ một địa chỉ ngrok free — loại URL đổi mỗi lần restart và không có SLA. Ở đây
``LSR_TRANSCRIBE_URL`` là **bắt buộc**: thà fail rõ ràng lúc khởi động còn hơn im lặng gửi
recording cuộc họp tới một địa chỉ đã đổi chủ.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import requests


class TranscribeError(RuntimeError):
    """Lỗi khi gọi transcription server."""


class TranscribeClient:
    """Gửi job transcript và lấy kết quả."""

    def __init__(self, base_url: str | None = None, *, timeout: int = 60) -> None:
        url = (base_url or os.environ.get("LSR_TRANSCRIBE_URL", "")).rstrip("/")
        if not url:
            raise TranscribeError(
                "cần LSR_TRANSCRIBE_URL — hỏi admin địa chỉ transcription server")
        self.base_url = url
        self._timeout = timeout
        # ngrok free hiện trang cảnh báo nếu thiếu header này.
        self._headers = {"ngrok-skip-browser-warning": "true"}

    def health(self) -> dict:
        r = requests.get(f"{self.base_url}/health", headers=self._headers,
                         timeout=self._timeout)
        r.raise_for_status()
        return r.json()

    def submit(self, path: str | Path, *, language: str = "vi") -> str:
        """Gửi file, trả ``job_id``."""
        p = Path(path)
        if not p.exists():
            raise TranscribeError(f"không thấy file {p}")
        with p.open("rb") as fh:
            r = requests.post(f"{self.base_url}/transcribe",
                              files={"file": (p.name, fh)},
                              data={"language": language},
                              headers=self._headers, timeout=self._timeout)
        if not r.ok:
            raise TranscribeError(f"submit lỗi {r.status_code}: {r.text[:200]}")
        job_id = (r.json() or {}).get("job_id")
        if not job_id:
            raise TranscribeError(f"server không trả job_id: {r.text[:200]}")
        return job_id

    def result(self, job_id: str) -> dict:
        r = requests.get(f"{self.base_url}/result/{job_id}", headers=self._headers,
                         timeout=self._timeout)
        if not r.ok:
            raise TranscribeError(f"result lỗi {r.status_code}: {r.text[:200]}")
        return r.json() or {}

    def wait(self, job_id: str, *, max_wait: int = 1800, interval: int = 10) -> str:
        """Chờ tới khi có transcript. Trả nội dung transcript.

        ``max_wait`` mặc định 30 phút — họp dài thì transcript lâu. Quá hạn thì raise để
        job vào DLQ và replay được từ console, thay vì trả biên bản rỗng.
        """
        deadline = time.time() + max_wait
        while time.time() < deadline:
            data = self.result(job_id)
            status = (data.get("status") or "").lower()
            if status == "done":
                text = data.get("transcript") or ""
                if not text.strip():
                    raise TranscribeError(f"job {job_id} xong nhưng transcript rỗng")
                return text
            if status in ("error", "failed"):
                raise TranscribeError(f"job {job_id} lỗi: {data.get('error')}")
            time.sleep(interval)
        raise TranscribeError(f"job {job_id} quá {max_wait}s chưa xong")
