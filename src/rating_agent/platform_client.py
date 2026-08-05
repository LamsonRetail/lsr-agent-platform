"""Client gọi Platform API + Collector — cho dashboard live và thao tác thật.

- ``PlatformClient``: registry agent, Test & Learn (đọc + thao tác Duyệt/Giao bài/
  tạo test/import training).
- ``CollectorClient``: thống kê token + trace.

Cấu hình qua env: LSR_PLATFORM_URL, PLATFORM_ADMIN_TOKEN, LSR_COLLECTOR,
COLLECTOR_INGEST_TOKEN.
"""

from __future__ import annotations

import os

import requests


class PlatformClient:
    def __init__(self, base_url: str | None = None, admin_token: str | None = None,
                 *, timeout: int = 15) -> None:
        self.base = (base_url or os.environ.get("LSR_PLATFORM_URL", "http://localhost:8090")).rstrip("/")
        self._admin = admin_token if admin_token is not None else os.environ.get("PLATFORM_ADMIN_TOKEN", "")
        self._timeout = timeout

    def _admin_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._admin}", "Content-Type": "application/json"}

    def _get(self, path: str, params: dict | None = None):
        r = requests.get(f"{self.base}{path}", params=params, timeout=self._timeout)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict, *, admin: bool = False):
        headers = self._admin_headers() if admin else {"Content-Type": "application/json"}
        r = requests.post(f"{self.base}{path}", json=body, headers=headers, timeout=self._timeout)
        r.raise_for_status()
        return r.json()

    # -- reads --
    def list_agents(self) -> list[dict]:
        return self._get("/v1/agents")

    def list_tests(self) -> list[dict]:
        return self._get("/v1/tests")

    def get_test(self, test_id: str) -> dict:
        return self._get(f"/v1/tests/{test_id}")

    def list_attempts(self, *, taker_id: str | None = None, test_id: str | None = None) -> list[dict]:
        params = {}
        if taker_id:
            params["taker_id"] = taker_id
        if test_id:
            params["test_id"] = test_id
        return self._get("/v1/attempts", params or None)

    def list_training(self) -> list[dict]:
        return self._get("/v1/training")

    # -- actions (nối các nút) --
    def register_agent(self, agent: dict) -> dict:
        return self._post("/v1/agents/register", agent, admin=True)

    def set_agent_status(self, agent_id: str, status: str) -> dict:
        return self._post(f"/v1/agents/{agent_id}/status", {"status": status}, admin=True)

    def create_test(self, test: dict) -> dict:
        return self._post("/v1/tests", test, admin=True)

    def review_test(self, test_id: str, reviewed_by: str) -> dict:  # nút "Duyệt"
        return self._post(f"/v1/tests/{test_id}/review", {"reviewed_by": reviewed_by}, admin=True)

    def assign_test(self, test_id: str, assignees: list[dict]) -> dict:  # nút "Giao bài"
        return self._post(f"/v1/tests/{test_id}/assign", {"assignees": assignees}, admin=True)

    def add_training(self, material: dict) -> dict:  # nút "Import"
        return self._post("/v1/training", material, admin=True)

    def submit_attempt(self, body: dict) -> dict:
        return self._post("/v1/attempts", body)


class CollectorClient:
    def __init__(self, base_url: str | None = None, *, timeout: int = 15) -> None:
        self.base = (base_url or os.environ.get("LSR_COLLECTOR", "http://localhost:8081")).rstrip("/")
        self._timeout = timeout

    def token_stats(self) -> list[dict]:
        r = requests.get(f"{self.base}/v1/stats", timeout=self._timeout)
        r.raise_for_status()
        return r.json()

    def list_traces(self, *, agent_id: str | None = None, limit: int = 20) -> list[dict]:
        params: dict = {"limit": limit}
        if agent_id:
            params["agent_id"] = agent_id
        r = requests.get(f"{self.base}/v1/traces", params=params, timeout=self._timeout)
        r.raise_for_status()
        return r.json()
