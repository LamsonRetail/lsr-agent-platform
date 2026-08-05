"""Client cho Whisper Transcription Server (Lark) — dùng cho bước transcript của Minh Anh.

Server nhận file audio/video → hàng đợi → trả job_id; poll `/result/{job_id}` tới
khi `status=done` để lấy `transcript`. Có thể để server tự callback về Lark bằng
các tham số callback_*.

Base URL mặc định lấy từ tài liệu; override bằng env ``LSR_TRANSCRIBE_URL``.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable

import requests

DEFAULT_BASE_URL = "https://slashingly-unexistent-hue.ngrok-free.dev"


class TranscribeError(RuntimeError):
    pass


class TranscribeClient:
    """Gửi job transcript và lấy kết quả."""

    def __init__(self, base_url: str | None = None, *, timeout: int = 60) -> None:
        self.base_url = (base_url or os.environ.get("LSR_TRANSCRIBE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self._timeout = timeout
        # ngrok free hiện trang cảnh báo nếu thiếu header này.
        self._headers = {"ngrok-skip-browser-warning": "true"}

    def health(self) -> dict:
        r = requests.get(f"{self.base_url}/health", headers=self._headers, timeout=self._timeout)
        r.raise_for_status()
        return r.json()

    def submit(
        self,
        *,
        file_path: str | Path | None = None,
        file_bytes: bytes | None = None,
        filename: str | None = None,
        language: str | None = None,
        task: str = "transcribe",
        meeting_title: str | None = None,
        callback_receive_id: str | None = None,
        callback_receive_type: str | None = None,
        callback_app_id: str | None = None,
        callback_app_secret: str | None = None,
        callback_domain: str | None = None,
    ) -> dict:
        """Gửi file lên server → trả về dict job (có ``job_id``)."""

        if file_path is not None:
            p = Path(file_path)
            data = p.read_bytes()
            fname = filename or p.name
        elif file_bytes is not None:
            data = file_bytes
            fname = filename or "audio"
        else:
            raise ValueError("Cần file_path hoặc file_bytes")

        params: dict[str, str] = {"task": task}
        if language:
            params["language"] = language

        form: dict[str, str] = {}
        for key, val in {
            "meeting_title": meeting_title,
            "callback_receive_id": callback_receive_id,
            "callback_receive_type": callback_receive_type,
            "callback_app_id": callback_app_id,
            "callback_app_secret": callback_app_secret,
            "callback_domain": callback_domain,
        }.items():
            if val is not None:
                form[key] = val

        resp = requests.post(
            f"{self.base_url}/transcribe",
            params=params,
            data=form,
            files={"file": (fname, data)},
            headers=self._headers,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def result(self, job_id: str) -> dict:
        r = requests.get(
            f"{self.base_url}/result/{job_id}", headers=self._headers, timeout=self._timeout
        )
        r.raise_for_status()
        return r.json()

    def wait(
        self,
        job_id: str,
        *,
        poll_interval: float = 10.0,
        max_wait: float = 1800.0,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.monotonic,
    ) -> dict:
        """Poll tới khi ``status=done`` (hoặc lỗi/hết giờ). Trả về job cuối."""

        start = now()
        while True:
            res = self.result(job_id)
            status = res.get("status")
            if status == "done":
                return res
            if status == "error" or res.get("error"):
                raise TranscribeError(res.get("error") or "transcribe error")
            if now() - start > max_wait:
                raise TranscribeError(f"Hết thời gian chờ job {job_id}")
            sleep(poll_interval)

    def transcribe_and_wait(self, **kwargs) -> str:
        """Tiện ích: submit + wait, trả về text transcript."""

        job = self.submit(**kwargs)
        done = self.wait(job["job_id"])
        return done.get("transcript", "")
