"""Mock platform server — cấp job cho agent test end-to-end (không cần real platform)."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

# Queue job (consumer sẽ poll)
_jobs = []
_job_counter = 0
_lock = threading.Lock()


def _new_job(text: str, user_email: str = "") -> dict:
    """Tạo job giả từ Lark message."""
    global _job_counter
    with _lock:
        _job_counter += 1
        job = {
            "id": _job_counter,
            "payload": {
                "text": text,
                "sender_email": user_email or "user@hapas.vn",
                "sender_open_id": "ou_fake123",
            },
            "session_id": f"test-{_job_counter}",
            "channel": "lark",
        }
        _jobs.append(job)
    return job


class MockPlatformHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        print(f"GET {path}")

        # GET /v1/self/jobs?wait=25&max=1
        if path == "/v1/self/jobs":
            with _lock:
                jobs = _jobs[:1] if _jobs else []
                if jobs:
                    _jobs.pop(0)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(jobs).encode())
            return

        # GET /v1/self/context?session_id=...&user_ref=...&q=...
        if path == "/v1/self/context":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            ctx = {
                "model": "claude-opus-5",
                "instruction_block": "Trợ lý PMO dự án LamsonRetail",
                "rolling_summary": "",
                "user_facts": [],
                "knowledge": [],
                "recent_turns": [],
            }
            self.wfile.write(json.dumps(ctx).encode())
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode() if content_len else ""

        # POST /v1/self/jobs/{jid}/reply
        if "/v1/self/jobs/" in path and path.endswith("/reply"):
            try:
                payload = json.loads(body) if body else {}
                print(f"✅ Agent replied: {payload.get('text', '')[:100]}")
            except Exception:
                pass
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return

        # POST /v1/self/jobs/{jid}/complete
        if "/v1/self/jobs/" in path and path.endswith("/complete"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return

        # POST /v1/self/context
        if path == "/v1/self/context":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            ctx = {
                "model": "claude-opus-5",
                "instruction_block": "Trợ lý PMO dự án LamsonRetail",
                "rolling_summary": "",
                "user_facts": [],
                "knowledge": [],
                "recent_turns": [],
            }
            self.wfile.write(json.dumps(ctx).encode())
            return

        # POST /v1/self/session/turn
        if path == "/v1/self/session/turn":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress logs


def start_mock_platform(port=8000):
    """Start mock platform server in background."""
    server = HTTPServer(("localhost", port), MockPlatformHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"✅ Mock platform running on http://localhost:{port}")
    return server, thread


if __name__ == "__main__":
    # Test: start mock, create job, test consumer
    server, _ = start_mock_platform(8000)

    print("\n📝 Fake job queued — consumer will pick it up")
    job = _new_job("BST T5 Travel bag đang thế nào?", "trangdq@hapas.vn")
    print(f"   Job #{job['id']}: {job['payload']['text']}")

    print("\n⏳ Waiting for consumer response... (30s)")
    time.sleep(30)

    print("\n✅ Test complete")
