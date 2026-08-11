"""DirectLark — gọi thẳng Lark Open Platform (cho dịch vụ giữ app_secret).

Gói gọn 3 việc hay bị copy-paste ở mỗi agent: (1) lấy & cache tenant_access_token,
(2) resolve email→open_id kèm fallback enterprise_email + duyệt phòng ban, (3) gửi tin.
Cache đi qua ``store`` — dùng PostgresStore để CHIA SẺ giữa các agent.
"""

from __future__ import annotations

import json
import os
import time

import requests

from .errors import LarkError
from .store import CacheStore, MemoryStore

_MARGIN = 120  # làm mới token trước hạn 2 phút


class DirectLark:
    def __init__(self, *, app_id: str | None = None, app_secret: str | None = None,
                 domain: str | None = None, store: CacheStore | None = None,
                 notify_chat_id: str | None = None, timeout: int = 10) -> None:
        self.app_id = app_id or os.environ.get("LARK_APP_ID", "")
        self.app_secret = app_secret or os.environ.get("LARK_APP_SECRET", "")
        self.domain = (domain or os.environ.get("LARK_DOMAIN",
                       "https://open.larksuite.com")).rstrip("/")
        self.notify_chat_id = notify_chat_id or os.environ.get("LARK_NOTIFY_CHAT_ID", "")
        self.store: CacheStore = store or MemoryStore()
        self.timeout = timeout
        if not (self.app_id and self.app_secret):
            raise LarkError("DirectLark cần LARK_APP_ID + LARK_APP_SECRET")

    # -- token --------------------------------------------------------
    def token(self) -> str:
        cached = self.store.get_token(self.app_id)
        if cached:
            return cached[0]
        r = requests.post(f"{self.domain}/open-apis/auth/v3/tenant_access_token/internal",
                          json={"app_id": self.app_id, "app_secret": self.app_secret},
                          timeout=self.timeout)
        d = r.json()
        if d.get("code") != 0:
            raise LarkError("không lấy được tenant_access_token", detail=str(d.get("msg")))
        tok = d["tenant_access_token"]
        self.store.set_token(self.app_id, tok, time.time() + int(d.get("expire", 7200)) - _MARGIN)
        return tok

    # -- resolve ------------------------------------------------------
    def resolve(self, email: str) -> str | None:
        hit = self.store.get_identity(email)
        if hit:
            return hit
        token = self.token()
        r = requests.post(
            f"{self.domain}/open-apis/contact/v3/users/batch_get_id?user_id_type=open_id",
            headers={"Authorization": f"Bearer {token}"}, json={"emails": [email]},
            timeout=self.timeout)
        try:
            for u in (r.json().get("data") or {}).get("user_list") or []:
                if u.get("user_id"):
                    self.store.set_identity(email, u["user_id"])
                    return u["user_id"]
        except Exception:
            pass
        return self._resolve_by_enterprise(email, token)

    def _resolve_by_enterprise(self, email: str, token: str) -> str | None:
        key = (email or "").lower()
        h = {"Authorization": f"Bearer {token}"}
        dept_ids, page = ["0"], ""
        for _ in range(30):
            url = (f"{self.domain}/open-apis/contact/v3/departments?parent_department_id=0"
                   f"&fetch_child=true&page_size=50" + (f"&page_token={page}" if page else ""))
            try:
                d = (requests.get(url, headers=h, timeout=15).json().get("data") or {})
            except Exception:
                break
            dept_ids += [x.get("department_id") for x in (d.get("items") or []) if x.get("department_id")]
            if not d.get("has_more"):
                break
            page = d.get("page_token") or ""
        for did in dict.fromkeys(dept_ids):
            page = ""
            for _ in range(20):
                url = (f"{self.domain}/open-apis/contact/v3/users?department_id={did}"
                       f"&page_size=50" + (f"&page_token={page}" if page else ""))
                try:
                    d = (requests.get(url, headers=h, timeout=15).json().get("data") or {})
                except Exception:
                    break
                for u in d.get("items") or []:
                    for f in ("enterprise_email", "email"):
                        em = (u.get(f) or "").lower()
                        if em and u.get("open_id"):
                            self.store.set_identity(em, u["open_id"])
                hit = self.store.get_identity(key)
                if hit:
                    return hit
                if not d.get("has_more"):
                    break
                page = d.get("page_token") or ""
        return None

    # -- send ---------------------------------------------------------
    def send(self, to: str, text: str = "", *, markdown: str = "",
             to_type: str = "email") -> dict:
        if to_type == "email":
            open_id = self.resolve(to)
            if open_id:
                receive_id, id_type = open_id, "open_id"
            elif self.notify_chat_id:
                receive_id, id_type = self.notify_chat_id, "chat_id"
                if text:
                    text = f"@{to}: {text}"
                if markdown:
                    markdown = f"**@{to}**\n{markdown}"
            else:
                raise LarkError("không resolve được email và không có nhóm fallback")
        else:
            receive_id, id_type = to, to_type

        token = self.token()
        if markdown:
            msg_type = "interactive"
            content = json.dumps({"config": {"wide_screen_mode": True},
                                  "elements": [{"tag": "markdown", "content": markdown}]},
                                 ensure_ascii=False)
        else:
            msg_type, content = "text", json.dumps({"text": text}, ensure_ascii=False)
        r = requests.post(
            f"{self.domain}/open-apis/im/v1/messages?receive_id_type={id_type}",
            headers={"Authorization": f"Bearer {token}"},
            json={"receive_id": receive_id, "msg_type": msg_type, "content": content},
            timeout=self.timeout)
        d = r.json()
        if d.get("code") != 0:
            raise LarkError("Lark từ chối gửi", detail=str(d.get("msg")))
        return {"ok": True, "receive_id_type": id_type}

    def send_markdown(self, to: str, markdown: str, *, to_type: str = "email") -> dict:
        return self.send(to, markdown=markdown, to_type=to_type)
