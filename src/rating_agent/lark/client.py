"""Lark API client — quản lý xác thực và gọi HTTP.

Xác thực theo cơ chế Custom App của Lark Open Platform:
1. Gọi ``/auth/v3/tenant_access_token/internal`` với app_id + app_secret.
2. Nhận ``tenant_access_token`` (có thời hạn ~2 giờ) và cache lại.
3. Đính token vào header ``Authorization: Bearer <token>`` cho các request sau.

Tham khảo: https://open.larksuite.com/document/server-docs/authentication-management/access-token/tenant_access_token_internal
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from ..config import LarkConfig

logger = logging.getLogger(__name__)

# Đệm thời gian (giây) làm mới token trước khi hết hạn.
_TOKEN_REFRESH_MARGIN = 120


class LarkAuthError(RuntimeError):
    """Lỗi xác thực hoặc gọi API Lark."""


class LarkClient:
    """HTTP client mỏng cho Lark Open Platform.

    Ví dụ::

        client = LarkClient(config)
        data = client.get("/im/v1/chats", params={"page_size": 50})
    """

    def __init__(self, config: LarkConfig, *, timeout: int = 30) -> None:
        self._config = config
        self._timeout = timeout
        self._session = requests.Session()
        self._token: str | None = None
        self._token_expire_at: float = 0.0

    # -- Xác thực -------------------------------------------------------
    def _fetch_tenant_access_token(self) -> None:
        """Gọi Lark để lấy tenant_access_token mới."""

        if not self._config.is_configured:
            raise LarkAuthError(
                "Thiếu LARK_APP_ID/LARK_APP_SECRET — hãy cấu hình trong .env"
            )

        url = f"{self._config.domain}/open-apis/auth/v3/tenant_access_token/internal"
        resp = self._session.post(
            url,
            json={
                "app_id": self._config.app_id,
                "app_secret": self._config.app_secret,
            },
            timeout=self._timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 0:
            raise LarkAuthError(f"Lấy token thất bại: {payload}")

        self._token = payload["tenant_access_token"]
        expire_in = int(payload.get("expire", 7200))
        self._token_expire_at = time.monotonic() + expire_in - _TOKEN_REFRESH_MARGIN
        logger.debug("Đã lấy tenant_access_token mới, hết hạn sau %ss", expire_in)

    def _ensure_token(self) -> str:
        if self._token is None or time.monotonic() >= self._token_expire_at:
            self._fetch_tenant_access_token()
        assert self._token is not None
        return self._token

    # -- Gọi API --------------------------------------------------------
    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Gọi một endpoint Lark, trả về phần ``data`` trong response.

        ``path`` là đường dẫn tương đối, ví dụ ``/im/v1/messages``.
        """

        token = self._ensure_token()
        url = f"{self._config.domain}/open-apis{path}"
        resp = self._session.request(
            method,
            url,
            params=params,
            json=json_body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") not in (0, None):
            raise LarkAuthError(f"Lỗi API Lark {path}: {payload}")
        return payload.get("data", payload)

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request("GET", path, params=params)

    def post(self, path: str, *, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request("POST", path, json_body=json_body)
