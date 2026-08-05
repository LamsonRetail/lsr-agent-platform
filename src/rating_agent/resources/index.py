"""Index + tra cứu tài nguyên được share.

- ``ResourceIndex``: index trong bộ nhớ (test/offline) với search theo từ khoá.
- ``ResourceIndexClient``: gửi/tra cứu qua collector (Postgres full-text) khi chạy thật.
"""

from __future__ import annotations

import logging

import requests

from .models import SharedResource

logger = logging.getLogger(__name__)


class ResourceIndex:
    """Index đơn giản trong bộ nhớ; search AND theo từ khoá + lọc agent/folder."""

    def __init__(self) -> None:
        self._items: list[SharedResource] = []

    def add(self, resource: SharedResource) -> None:
        # Ghi đè nếu trùng resource_id (idempotent).
        self._items = [r for r in self._items if r.resource_id != resource.resource_id]
        self._items.append(resource)

    def search(
        self,
        query: str = "",
        *,
        agent_id: str | None = None,
        folder: str | None = None,
        limit: int = 20,
    ) -> list[SharedResource]:
        terms = [t.lower() for t in query.split() if t.strip()]

        def match(r: SharedResource) -> bool:
            if agent_id is not None and r.agent_id != agent_id:
                return False
            if folder is not None and r.folder != folder:
                return False
            if not terms:
                return True
            hay = r.haystack()
            return all(t in hay for t in terms)

        results = [r for r in self._items if match(r)]
        # Mới nhất trước.
        results.sort(key=lambda r: r.shared_at, reverse=True)
        return results[:limit]

    def __len__(self) -> int:
        return len(self._items)


class ResourceIndexClient:
    """Gửi/tra cứu tài nguyên qua collector (`/v1/resources`).

    ``api_key`` = telemetry/ingest key. Endpoint = URL collector.
    """

    def __init__(self, endpoint: str, api_key: str, *, timeout: int = 10) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

    def index(self, resource: SharedResource) -> None:
        resp = requests.post(
            f"{self._endpoint}/v1/resources",
            json=resource.model_dump(),
            headers=self._headers(),
            timeout=self._timeout,
        )
        resp.raise_for_status()

    def search(
        self,
        query: str = "",
        *,
        agent_id: str | None = None,
        folder: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        params: dict[str, str | int] = {"q": query, "limit": limit}
        if agent_id:
            params["agent_id"] = agent_id
        if folder:
            params["folder"] = folder
        resp = requests.get(
            f"{self._endpoint}/v1/resources/search",
            params=params,
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return resp.json()
