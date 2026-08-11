"""RemoteLark — client mỏng gọi qua broker platform_api /v1/lark/*.

Chỉ dùng stdlib (urllib) để agent không phải thêm dependency. Best-effort:
mặc định lỗi mạng KHÔNG raise (``raise_on_error=False``) để telemetry/thông báo
không làm hỏng phiên agent; đặt True nếu muốn bắt lỗi.
"""

from __future__ import annotations

import json
import os
import urllib.request

from .errors import LarkError


class RemoteLark:
    def __init__(self, *, platform_url: str | None = None, agent_token: str | None = None,
                 timeout: int = 10, raise_on_error: bool = False) -> None:
        self.platform_url = (platform_url or os.environ.get("LSR_PLATFORM_URL", "")).rstrip("/")
        self.agent_token = agent_token or os.environ.get("LSR_AGENT_TOKEN") \
            or os.environ.get("LSR_TELEMETRY_API_KEY", "")
        self.timeout = timeout
        self.raise_on_error = raise_on_error
        if not self.platform_url or not self.agent_token:
            # Không raise ngay: cho phép no-op êm nếu chưa cấu hình.
            self._configured = False
        else:
            self._configured = True

    # -- HTTP nội bộ --------------------------------------------------
    def _call(self, method: str, path: str, payload: dict | None = None) -> dict:
        if not self._configured:
            if self.raise_on_error:
                raise LarkError("lsr_lark chưa cấu hình (LSR_PLATFORM_URL/LSR_AGENT_TOKEN)")
            return {}
        url = self.platform_url + path
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.agent_token}",
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                body = r.read().decode()
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = json.loads(e.read().decode()).get("detail", "")
            except Exception:
                pass
            if self.raise_on_error:
                raise LarkError(f"Lark broker {e.code}", status=e.code, detail=str(detail))
            return {"ok": False, "error": e.code, "detail": detail}
        except Exception as e:  # mạng/timeout
            if self.raise_on_error:
                raise LarkError(str(e))
            return {"ok": False, "error": "network", "detail": str(e)}

    # -- API công khai ------------------------------------------------
    def send(self, to: str, text: str = "", *, markdown: str = "",
             to_type: str = "email") -> dict:
        """Gửi tin tới email | open_id | chat_id. Trả dict kết quả broker."""

        return self._call("POST", "/v1/lark/send", {
            "to": to, "to_type": to_type, "text": text, "markdown": markdown,
        })

    def send_markdown(self, to: str, markdown: str, *, to_type: str = "email") -> dict:
        return self.send(to, markdown=markdown, to_type=to_type)

    def resolve(self, email: str) -> str | None:
        """email → open_id (dùng cache danh tính chung của platform)."""

        return (self._call("POST", "/v1/lark/resolve", {"email": email}) or {}).get("open_id")

    def chats(self) -> list[dict]:
        """Danh sách nhóm bot platform đang tham gia (chat_id + name)."""

        return (self._call("GET", "/v1/lark/chats") or {}).get("chats", [])
