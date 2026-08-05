"""Test cho TranscribeClient (mock HTTP) + wait/poll loop."""

from __future__ import annotations

import pytest

from rating_agent.meeting import TranscribeClient, TranscribeError
from rating_agent.meeting import transcribe as tr


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


def test_submit_builds_params_and_files(tmp_path, monkeypatch):
    captured = {}

    def fake_post(url, params=None, data=None, files=None, headers=None, timeout=None):
        captured.update(url=url, params=params, data=data,
                        fname=files["file"][0], headers=headers)
        return _Resp({"job_id": "J1", "status": "queued"})

    monkeypatch.setattr(tr.requests, "post", fake_post)
    f = tmp_path / "hop.mp3"
    f.write_bytes(b"audio")
    job = TranscribeClient("https://x").submit(
        file_path=f, language="vi", meeting_title="Họp Sprint",
        callback_receive_id="oc_1", callback_app_id="cli_1", callback_app_secret="s",
    )
    assert job["job_id"] == "J1"
    assert captured["url"].endswith("/transcribe")
    assert captured["params"] == {"task": "transcribe", "language": "vi"}
    assert captured["data"]["meeting_title"] == "Họp Sprint"
    assert captured["data"]["callback_app_id"] == "cli_1"
    assert captured["fname"] == "hop.mp3"
    assert captured["headers"].get("ngrok-skip-browser-warning") == "true"


def test_wait_polls_until_done(monkeypatch):
    seq = iter([
        {"status": "processing", "progress_pct": 30},
        {"status": "processing", "progress_pct": 80},
        {"status": "done", "transcript": "[00:00] xin chao", "progress_pct": 100},
    ])
    c = TranscribeClient("https://x")
    monkeypatch.setattr(c, "result", lambda job_id: next(seq))
    done = c.wait("J1", poll_interval=0, sleep=lambda _s: None)
    assert done["status"] == "done"
    assert "xin chao" in done["transcript"]


def test_wait_raises_on_error(monkeypatch):
    c = TranscribeClient("https://x")
    monkeypatch.setattr(c, "result", lambda job_id: {"status": "error", "error": "boom"})
    with pytest.raises(TranscribeError):
        c.wait("J1", poll_interval=0, sleep=lambda _s: None)


def test_wait_times_out(monkeypatch):
    c = TranscribeClient("https://x")
    monkeypatch.setattr(c, "result", lambda job_id: {"status": "processing"})
    t = iter([0, 0, 100, 100, 200])
    with pytest.raises(TranscribeError):
        c.wait("J1", poll_interval=0, max_wait=50, sleep=lambda _s: None, now=lambda: next(t))
