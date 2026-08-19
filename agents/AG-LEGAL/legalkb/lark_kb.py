"""Đọc Lark Wiki + Drive bằng tenant token — chỉ stdlib.

⚠️ NGOẠI LỆ CÓ CHỦ Ý so với chuẩn "mọi tương tác Lark qua platform" (PLAN §2.3):
broker của platform hiện chỉ có nhóm `im` (send/resolve/chats/resource) — CHƯA có
endpoint đọc Wiki/Drive. Vì vậy riêng phần nạp KB còn dùng tenant token trực tiếp.
Đã mở yêu cầu core **C1** (`/v1/lark/wiki/*`, `/v1/lark/drive/*`); khi có thì thay
`LarkKB` bằng lời gọi broker và bỏ hẳn app_secret khỏi agent.

Mọi việc GỬI/NHẬN tin Lark đi qua `legalkb/platform.py`. Ngoại lệ DUY NHẤT ở cuối file:
`im_send_markdown()` — chỉ chạy khi broker trả `sent:false` (app của AG-LEGAL chưa có
trong `LARK_EXTRA_APPS` của core → yêu cầu **C9**). Không thêm hàm `im` nào khác.

Cần các scope (admin duyệt trên Lark Developer Console):
  wiki:wiki:readonly · drive:drive:readonly · docx:document:readonly
Và bot phải là member (Read) của wiki space pháp chế.
"""
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request


class LarkError(RuntimeError):
    def __init__(self, code, msg, http=None):
        super().__init__(f"lark code={code}: {msg}")
        self.code = code
        self.http = http


# Lỗi quyền wiki hay gặp — kèm hướng dẫn để worker báo rõ ràng (test case #12)
PERMISSION_CODES = {131006, 99991672, 1069902}
PERMISSION_HINT = (
    "Bot chưa có quyền đọc wiki space. Admin mở Wiki space → Settings → Members "
    "→ thêm bot app với quyền Read, và kiểm tra app đã có scope wiki:wiki:readonly."
)


class LarkKB:
    """Chỉ đọc Wiki/Drive để nạp KB. Không gửi tin, không thao tác chat."""

    def __init__(self, app_id, app_secret,
                 base="https://open.larksuite.com",
                 tenant_domain="o4pvcegwn6b.sg.larksuite.com"):
        self.app_id = app_id
        self.app_secret = app_secret
        self.base = base.rstrip("/")
        self.tenant_domain = tenant_domain
        self._token = None
        self._token_exp = 0.0

    # ---------- HTTP ----------

    def _request(self, method, path, payload=None, raw=False, auth=True, timeout=60):
        url = path if path.startswith("http") else self.base + path
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"}
        if auth:
            headers["Authorization"] = f"Bearer {self.tenant_token()}"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
        except urllib.error.HTTPError as e:
            body = e.read()
            try:
                j = json.loads(body.decode())
                raise LarkError(j.get("code", e.code), j.get("msg", str(e)), http=e.code)
            except (ValueError, KeyError):
                raise LarkError(e.code, body[:200].decode(errors="replace"), http=e.code)
        if raw:
            return body
        j = json.loads(body.decode())
        if j.get("code", 0) != 0:
            raise LarkError(j["code"], j.get("msg", ""))
        return j.get("data", {})

    def tenant_token(self):
        if self._token and time.time() < self._token_exp - 300:
            return self._token
        req = urllib.request.Request(
            self.base + "/open-apis/auth/v3/tenant_access_token/internal",
            data=json.dumps({"app_id": self.app_id, "app_secret": self.app_secret}).encode(),
            method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            j = json.loads(r.read().decode())
        if j.get("code", 0) != 0:
            raise LarkError(j["code"], j.get("msg", "tenant_access_token failed"))
        self._token = j["tenant_access_token"]
        self._token_exp = time.time() + int(j.get("expire", 3600))
        return self._token

    def _paged(self, path, params, item_key):
        """GET có phân trang chuẩn Lark (page_token/has_more)."""
        token = ""
        while True:
            q = dict(params)
            if token:
                q["page_token"] = token
            data = self._request("GET", f"{path}?{urllib.parse.urlencode(q)}")
            for it in data.get(item_key) or []:
                yield it
            if not data.get("has_more"):
                return
            token = data.get("page_token", "")

    # ---------- Wiki ----------

    def wiki_nodes(self, space_id, parent_node_token=None):
        """Duyệt đệ quy toàn bộ node trong một wiki space."""
        params = {"page_size": 50}
        if parent_node_token:
            params["parent_node_token"] = parent_node_token
        try:
            nodes = list(self._paged(f"/open-apis/wiki/v2/spaces/{space_id}/nodes",
                                     params, "items"))
        except LarkError as e:
            if e.code in PERMISSION_CODES:
                raise LarkError(e.code, f"{e.args[0] if e.args else e}. {PERMISSION_HINT}")
            raise
        out = []
        for n in nodes:
            out.append(n)
            if n.get("has_child"):
                out.extend(self.wiki_nodes(space_id, n["node_token"]))
        return out

    def docx_raw_content(self, document_id):
        data = self._request(
            "GET", f"/open-apis/docx/v1/documents/{document_id}/raw_content?lang=0")
        return data.get("content", "")

    def wiki_node_url(self, node_token):
        return f"https://{self.tenant_domain}/wiki/{node_token}"

    # ---------- Drive ----------

    def drive_files(self, folder_token):
        return list(self._paged("/open-apis/drive/v1/files",
                                {"folder_token": folder_token, "page_size": 200},
                                "files"))

    def drive_download(self, file_token):
        return self._request(
            "GET", f"/open-apis/drive/v1/files/{file_token}/download", raw=True,
            timeout=300)

    def drive_file_url(self, file_token, file_type="file"):
        return f"https://{self.tenant_domain}/{file_type}/{file_token}"

    # ---------- NGOẠI LỆ C9: gửi tin khi broker không gửi được ----------

    def im_send_markdown(self, chat_id, markdown):
        """Gửi card markdown trực tiếp — CHỈ làm fallback khi broker thất bại.

        ⚠️ Ngoại lệ có chủ ý so với chuẩn "mọi tương tác Lark qua platform": broker chỉ
        nạp được app có tên trong danh sách CỨNG `LARK_EXTRA_APPS`
        (infra/docker-compose.yml), AG-LEGAL không có trong đó → `/v1/lark/send` trả
        `sent:false`. Bỏ fallback này thì agent IM LẶNG trên đúng kênh người dùng đang
        dùng — tệ hơn là giữ một ngoại lệ có tài liệu.

        ĐIỀU KIỆN XOÁ: khi core thêm `LEGAL_LARK_APP_ID/SECRET` vào `LARK_EXTRA_APPS`
        (C9) → đặt `LARK_BOT_APP_ID` trong .env, rồi xoá hàm này và đường fallback trong
        `legalkb/platform.py`.
        """
        data = self._request(
            "POST", "/open-apis/im/v1/messages?receive_id_type=chat_id",
            {"receive_id": chat_id, "msg_type": "interactive",
             "content": json.dumps({"config": {"wide_screen_mode": True},
                                    "elements": [{"tag": "markdown",
                                                  "content": markdown}]},
                                   ensure_ascii=False)})
        return data.get("message_id")

    def drive_upload(self, folder_token, file_name, data):
        """Upload file vào Drive folder → trả file_token.

        Dùng cho S2 (bản thảo hợp đồng) và S4 (văn bản luật crawl về). Gửi file cho người
        dùng bằng LINK DRIVE chứ không đính kèm qua Lark IM: broker platform chỉ gửi
        text/markdown, không gửi file (gap C7) — mà link Drive lại đúng hơn về quản trị
        (quyền do Lark quản, legal team thấy được ở folder).
        Cần scope `drive:file:upload`.
        """
        boundary = "----lsrlegal" + hashlib.md5(file_name.encode()).hexdigest()[:12]
        parts = []

        def field(name, value):
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; "
                         f'name="{name}"\r\n\r\n{value}\r\n'.encode())

        field("file_name", file_name)
        field("parent_type", "explorer")
        field("parent_node", folder_token)
        field("size", str(len(data)))
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                     f'filename="{file_name}"\r\n'
                     f"Content-Type: application/octet-stream\r\n\r\n".encode())
        parts.append(data)
        parts.append(f"\r\n--{boundary}--\r\n".encode())
        body = b"".join(parts)

        req = urllib.request.Request(
            self.base + "/open-apis/drive/v1/files/upload_all", data=body, method="POST",
            headers={"Authorization": f"Bearer {self.tenant_token()}",
                     "Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                j = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            raise LarkError(e.code, e.read()[:200].decode(errors="replace"), http=e.code)
        if j.get("code", 0) != 0:
            raise LarkError(j["code"], j.get("msg", "upload thất bại"))
        return (j.get("data") or {}).get("file_token")

