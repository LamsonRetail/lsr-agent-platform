"""Client duy nhất nói chuyện với LSR Agent Platform.

Vì sao gom vào một chỗ: chuẩn platform yêu cầu agent KHÔNG tự tích hợp Lark và
KHÔNG giữ ngữ cảnh trong tiến trình/model. Mọi thứ đi qua đây:

  Bộ nhớ    GET  /v1/self/context          → instruction + summary + turns + facts + RAG
            POST /v1/self/session/turn      → ghi lượt
            POST /v1/self/session/summary   → nén lượt cũ
            POST /v1/self/facts             → fact bền về người dùng
  Việc      GET  /v1/self/jobs · reply · event · complete · fail
  Lark      POST /v1/lark/send · /v1/lark/resolve · GET /v1/lark/chats
            GET  /v1/lark/resource/{message_id}/{file_key}   (tải file user gửi)

KHÔNG có app_secret ở đây — token/danh bạ Lark do platform giữ và cache chung.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_URL = "https://platform.34-126-154-135.sslip.io"


class PlatformError(RuntimeError):
    def __init__(self, status, detail):
        super().__init__(f"platform {status}: {detail}")
        self.status = status
        self.detail = detail


class Platform:
    def __init__(self, url=None, token=None):
        self.url = (url or os.environ.get("LSR_PLATFORM_URL", DEFAULT_URL)).rstrip("/")
        # Runtime chính thức (POST /v1/self/deploy) truyền token bằng tên
        # LSR_TELEMETRY_API_KEY; chạy tay thì LSR_AGENT_TOKEN. Nhận cả hai.
        self.token = (token or os.environ.get("LSR_AGENT_TOKEN")
                      or os.environ.get("LSR_TELEMETRY_API_KEY") or "")

    # ---------- HTTP ----------

    def call(self, method, path, payload=None, timeout=40, raw=False):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            self.url + path, data=data, method=method,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.token}"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
        except urllib.error.HTTPError as e:
            detail = e.read()[:300].decode(errors="replace")
            raise PlatformError(e.code, detail)
        if raw:
            return body
        txt = body.decode()
        return json.loads(txt) if txt else {}

    def _quiet(self, method, path, payload=None, what=""):
        """Gọi mà lỗi KHÔNG được làm chết luồng chính (ghi log, telemetry phụ)."""
        try:
            return self.call(method, path, payload)
        except Exception as exc:
            print(f"[platform] {what or path} lỗi (bỏ qua): {exc}",
                  file=sys.stderr, flush=True)
            return None

    # ---------- Bộ nhớ: platform giữ state, agent dựng prompt stateless ----------

    def context(self, session_id, user_ref="", q="", env=None, k=0):
        """Toàn bộ ngữ cảnh cho một lượt. Lỗi → dict rỗng (agent phải degrade, không bịa)."""
        env = env or os.environ.get("LSR_ENV", "prod")
        qs = urllib.parse.urlencode(
            {"session_id": session_id, "user_ref": user_ref or "",
             "q": (q or "")[:200], "env": env, "k": k or 0})
        return self._quiet("GET", f"/v1/self/context?{qs}", what="context") or {}

    def add_turn(self, session_id, role, text, user_ref=None, channel=None):
        return self._quiet("POST", "/v1/self/session/turn", {
            "session_id": session_id, "role": role, "text": text,
            "user_ref": user_ref, "channel": channel}, what="session/turn") or {}

    def set_summary(self, session_id, summary):
        return self._quiet("POST", "/v1/self/session/summary",
                           {"session_id": session_id, "summary": summary},
                           what="session/summary")

    def add_fact(self, user_ref, fact, source=None):
        return self._quiet("POST", "/v1/self/facts",
                           {"user_ref": user_ref, "fact": fact, "source": source},
                           what="facts")

    def facts(self, user_ref):
        r = self._quiet("GET", f"/v1/self/facts?user_ref={urllib.parse.quote(user_ref)}",
                        what="facts") or {}
        return r.get("facts", r if isinstance(r, list) else [])

    def add_brain_item(self, title, content, status="approved", source_url=None):
        return self._quiet("POST", "/v1/self/brain/items",
                           {"title": title, "content": content, "status": status,
                            "source_url": source_url}, what="brain/items")

    # ---------- Việc ----------

    def poll(self, wait=25, n=5):
        return self.call("GET", f"/v1/self/jobs?wait={wait}&max={n}",
                         timeout=wait + 20) or []

    def reply(self, job_id, text):
        return self.call("POST", f"/v1/self/jobs/{job_id}/reply", {"text": text})

    def event(self, job_id, kind, data=None):
        """Báo tiến trình để console/SSE thấy — thay cho việc tự gửi tin 'đang gõ'."""
        return self._quiet("POST", f"/v1/self/jobs/{job_id}/event",
                           {"kind": kind, "data": data or {}}, what="job/event")

    def complete(self, job_id, result=None):
        try:
            return self.call("POST", f"/v1/self/jobs/{job_id}/complete",
                             {"result": result or {"ok": True}})
        except PlatformError as e:
            if e.status != 409:      # 409 = job đã bị thu hồi vì chạy lâu
                raise
            print(f"  (job#{job_id} hết hạn khoá — đã trả lời xong)", flush=True)
            return {}

    def fail(self, job_id, error):
        return self._quiet("POST", f"/v1/self/jobs/{job_id}/fail",
                           {"error": str(error)[:400]}, what="job/fail")

    # ---------- Lark: CHỈ qua broker của platform ----------

    def lark_send(self, to, text=None, markdown=None, to_type="chat_id"):
        body = {"to": to, "to_type": to_type}
        if markdown:
            body["markdown"] = markdown
        else:
            body["text"] = text or ""
        r = self._quiet("POST", "/v1/lark/send", body, what="lark/send")
        return bool(r and r.get("sent", True))

    def lark_resolve(self, email):
        r = self._quiet("POST", "/v1/lark/resolve", {"email": email}, what="lark/resolve")
        return (r or {}).get("open_id")

    def lark_chats(self, app_id=""):
        qs = f"?app_id={urllib.parse.quote(app_id)}" if app_id else ""
        r = self._quiet("GET", f"/v1/lark/chats{qs}", what="lark/chats") or {}
        return r.get("chats", r if isinstance(r, list) else [])

    def lark_resource(self, message_id, file_key, kind="file", app_id=""):
        """Tải file/ảnh người dùng gửi kèm — KHÔNG cần app_secret."""
        qs = urllib.parse.urlencode({"type": kind, "app_id": app_id or ""})
        return self.call("GET", f"/v1/lark/resource/{message_id}/{file_key}?{qs}",
                         timeout=180, raw=True)
