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
    def __init__(self, url=None, token=None, app_id=None, fallback=None):
        self.url = (url or os.environ.get("LSR_PLATFORM_URL", DEFAULT_URL)).rstrip("/")
        # Runtime chính thức (POST /v1/self/deploy) truyền token bằng tên
        # LSR_TELEMETRY_API_KEY; chạy tay thì LSR_AGENT_TOKEN. Nhận cả hai.
        self.token = (token or os.environ.get("LSR_AGENT_TOKEN")
                      or os.environ.get("LSR_TELEMETRY_API_KEY") or "")
        # Broker hỗ trợ đa app Lark: phải gửi bằng ĐÚNG app đang là member của group.
        #
        # ⚠️ KHÔNG dùng LARK_APP_ID ở đây. Biến đó là app riêng của AG-LEGAL, chỉ để đọc
        # Wiki/Drive (lark_kb.py). Broker chỉ nạp được app có tên trong danh sách CỨNG
        # `LARK_EXTRA_APPS` của infra/docker-compose.yml (SAWADEE|SOURCING|DATA|HARRY|LYLY
        # + app Admin) — AG-LEGAL không có trong đó, nên truyền app_id đó vào sẽ nhận
        # 503 "chưa có secret trên VM" và MẤT toàn bộ thông báo/phê duyệt.
        # Mặc định để RỖNG = dùng app Admin dùng chung của platform (đúng với
        # `lark.bot.app: platform-shared` trong lsr-agent.yaml). Muốn bot riêng thì nhờ
        # core thêm LEGAL vào LARK_EXTRA_APPS rồi set LARK_BOT_APP_ID.
        self.app_id = (app_id if app_id is not None
                       else os.environ.get("LARK_BOT_APP_ID", ""))
        # Ngoại lệ C9: callable(chat_id, markdown) chạy khi broker không gửi được.
        # Gán ở consumer.build(); None = không có đường dự phòng.
        self.fallback = fallback

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

    def lark_send(self, to, text=None, markdown=None, to_type="chat_id", app_id=None):
        body = {"to": to, "to_type": to_type}
        aid = self.app_id if app_id is None else app_id
        if aid:
            body["app_id"] = aid
        if markdown:
            body["markdown"] = markdown
        else:
            body["text"] = text or ""
        r = self._quiet("POST", "/v1/lark/send", body, what="lark/send")
        if r and r.get("sent", True):
            return True
        # Broker không gửi được — thường vì app chưa có trong LARK_EXTRA_APPS (C9).
        # Im lặng ở đây = mất thông báo & mất luôn đường phê duyệt, nên thử dự phòng.
        if self.fallback and to_type == "chat_id":
            try:
                self.fallback(to, markdown or text or "")
                print(f"[lark] broker không gửi được → gửi trực tiếp (ngoại lệ C9) tới {to}",
                      file=sys.stderr, flush=True)
                return True
            except Exception as exc:
                print(f"[lark] fallback cũng lỗi: {exc}", file=sys.stderr, flush=True)
        return False

    def lark_resolve(self, email):
        r = self._quiet("POST", "/v1/lark/resolve", {"email": email}, what="lark/resolve")
        return (r or {}).get("open_id")

    def lark_chats(self, app_id=None):
        app_id = self.app_id if app_id is None else app_id
        qs = f"?app_id={urllib.parse.quote(app_id)}" if app_id else ""
        r = self._quiet("GET", f"/v1/lark/chats{qs}", what="lark/chats") or {}
        return r.get("chats", r if isinstance(r, list) else [])

    def lark_resource(self, message_id, file_key, kind="file", app_id=None):
        """Tải file/ảnh người dùng gửi kèm — KHÔNG cần app_secret.

        app_id phải là app ĐÃ NHẬN tin (lấy từ reply_to.app_id của job) để broker dùng
        đúng tenant token; rỗng thì broker dùng app mặc định.
        """
        app_id = self.app_id if app_id is None else app_id
        qs = urllib.parse.urlencode({"type": kind, "app_id": app_id or ""})
        return self.call("GET", f"/v1/lark/resource/{message_id}/{file_key}?{qs}",
                         timeout=180, raw=True)
