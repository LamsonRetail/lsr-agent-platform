"""lsr_lark (bản single-file, remote-only) — drop-in cho agent.

Tải về:  curl -O https://platform.34-126-154-135.sslip.io/bootstrap/lsr_lark.py
Dùng:
    from lsr_lark import Lark
    lark = Lark()                      # đọc env LSR_PLATFORM_URL + LSR_AGENT_TOKEN
    lark.send("thint@hapas.vn", "Xong ✅")

Bản đầy đủ (kèm chế độ 'direct' giữ app_secret) ở libs/lsr_lark. File này chỉ cần
stdlib, gọi qua broker platform_api /v1/lark/* nên KHÔNG cầm app_secret.
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error


class LarkError(RuntimeError):
    pass


class RemoteLark:
    def __init__(self, *, platform_url=None, agent_token=None, timeout=10,
                 raise_on_error=False):
        self.platform_url = (platform_url or os.environ.get("LSR_PLATFORM_URL", "")).rstrip("/")
        self.agent_token = (agent_token or os.environ.get("LSR_AGENT_TOKEN")
                            or os.environ.get("LSR_TELEMETRY_API_KEY", ""))
        self.timeout = timeout
        self.raise_on_error = raise_on_error
        self._configured = bool(self.platform_url and self.agent_token)

    def _call(self, method, path, payload=None):
        if not self._configured:
            if self.raise_on_error:
                raise LarkError("chưa cấu hình LSR_PLATFORM_URL/LSR_AGENT_TOKEN")
            return {}
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(self.platform_url + path, data=data, method=method,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.agent_token}"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                b = r.read().decode()
                return json.loads(b) if b else {}
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = json.loads(e.read().decode()).get("detail", "")
            except Exception:
                pass
            if self.raise_on_error:
                raise LarkError(f"broker {e.code}: {detail}")
            return {"ok": False, "error": e.code, "detail": detail}
        except Exception as e:
            if self.raise_on_error:
                raise LarkError(str(e))
            return {"ok": False, "error": "network", "detail": str(e)}

    def send(self, to, text="", *, markdown="", to_type="email"):
        return self._call("POST", "/v1/lark/send",
                          {"to": to, "to_type": to_type, "text": text, "markdown": markdown})

    def send_markdown(self, to, markdown, *, to_type="email"):
        return self.send(to, markdown=markdown, to_type=to_type)

    def resolve(self, email):
        return (self._call("POST", "/v1/lark/resolve", {"email": email}) or {}).get("open_id")

    def chats(self):
        return (self._call("GET", "/v1/lark/chats") or {}).get("chats", [])


def Lark(**kwargs):
    return RemoteLark(**kwargs)
