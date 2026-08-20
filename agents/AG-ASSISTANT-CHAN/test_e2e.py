#!/usr/bin/env python3
"""End-to-end test: mock platform + consumer + agent."""

import os
import sys
import time
import threading

# Add current dir to path
sys.path.insert(0, os.path.dirname(__file__))

from mock_platform import start_mock_platform, _new_job

def test():
    # Start mock platform
    server, thread = start_mock_platform(8000)
    time.sleep(1)

    # Create fake job
    print("\n📝 Creating fake job...")
    job = _new_job("BST T5 Travel bag đang thế nào?", "trangdq@hapas.vn")
    print(f"   Job #{job['id']}: {job['payload']['text']}")

    # Start consumer in background
    print("\n🚀 Starting consumer...")
    from consumer import main
    consumer_thread = threading.Thread(target=main, daemon=True)
    consumer_thread.start()

    # Wait for consumer to process
    print("\n⏳ Waiting 15s for consumer to process job...")
    time.sleep(15)

    print("\n✅ Test done")
    server.shutdown()

def _load_env_local():
    """Nạp credential từ .env.local (gitignored) — KHÔNG hardcode secret vào mã."""
    path = os.path.join(os.path.dirname(__file__), ".env.local")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


if __name__ == "__main__":
    _load_env_local()
    os.environ.setdefault("LSR_PLATFORM_URL", "http://localhost:8000")
    os.environ.setdefault("LSR_AGENT_TOKEN", "test_token")

    test()
