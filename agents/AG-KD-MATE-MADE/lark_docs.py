"""Đọc dữ liệu Lark (Wiki · Docx · Base · Drive) — module riêng của AG-KD-MATE-MADE.

Cố ý **không** sửa ``libs/lsr_lark`` (core, cần maintainer duyệt): agent tự mang theo
phần đọc dữ liệu của mình. Nếu sau này platform đưa chức năng này vào lib chung thì xoá
file này và gọi lib.

Chỉ-đọc. Module này không có hàm ghi — agent không được sửa dữ liệu gốc trên Lark.

Điểm quan trọng: ``docx_sections()`` trả **block_id** của từng mục, nhờ đó tri thức lưu
vào brain có ``source_url`` trỏ thẳng đúng đoạn (``https://<host>/docx/<token>#<block_id>``)
— điều kiện để agent trích dẫn chính xác thay vì chỉ link tới đầu tài liệu.

Scope Lark cần cấp cho app đọc:
  wiki:node:read · wiki:space:read · docx:document:readonly · docs:document.content:read
  bitable:app:read · drive:drive:readonly
"""

from __future__ import annotations

import os
import time

import requests

_MARGIN = 120  # làm mới token trước hạn 2 phút

# Block chứa văn bản dùng được (bỏ ảnh, chia cột, iframe…). Theo docx v1 block_type.
_TEXT_BLOCK_TYPES = {2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17, 19, 20, 22}

# block_type của heading1..heading9 → dùng để cắt tài liệu thành mục.
_HEADING_TYPES = {3: 1, 4: 2, 5: 3, 6: 4, 7: 5, 8: 6, 9: 7, 10: 8, 11: 9}


class LarkDocsError(RuntimeError):
    """Lỗi khi gọi Lark."""


class LarkDocs:
    """Client chỉ-đọc Wiki / Docx / Bitable / Drive.

    Ví dụ::

        docs = LarkDocs()                       # đọc env LARK_APP_ID/SECRET
        for rec in docs.bitable_records(app_token, table_id):
            print(rec["fields"])
    """

    def __init__(self, *, app_id: str | None = None, app_secret: str | None = None,
                 domain: str | None = None, doc_host: str | None = None,
                 timeout: int = 20) -> None:
        self.app_id = app_id or os.environ.get("LARK_APP_ID", "")
        self.app_secret = app_secret or os.environ.get("LARK_APP_SECRET", "")
        self.domain = (domain or os.environ.get("LARK_DOMAIN",
                       "https://open.larksuite.com")).rstrip("/")
        # Host dựng link người đọc bấm được (khác domain API).
        self.doc_host = (doc_host or os.environ.get("LARK_DOC_HOST", "")).rstrip("/")
        self.timeout = timeout
        self._token = ""
        self._token_exp = 0.0
        if not (self.app_id and self.app_secret):
            raise LarkDocsError("cần LARK_APP_ID + LARK_APP_SECRET")

    # ----------------------------- hạ tầng -----------------------------

    def _tenant_token(self) -> str:
        if self._token and time.time() < self._token_exp - _MARGIN:
            return self._token
        r = requests.post(
            f"{self.domain}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=self.timeout)
        data = r.json()
        if data.get("code") != 0:
            raise LarkDocsError(f"lấy tenant token lỗi: {data.get('msg')}")
        self._token = data["tenant_access_token"]
        self._token_exp = time.time() + int(data.get("expire", 7200))
        return self._token

    def _get(self, path: str, params: dict | None = None) -> dict:
        r = requests.get(f"{self.domain}{path}", params=params or {},
                         headers={"Authorization": f"Bearer {self._tenant_token()}"},
                         timeout=self.timeout)
        data = r.json()
        if data.get("code") != 0:
            raise LarkDocsError(f"GET {path} lỗi {data.get('code')}: {data.get('msg')}")
        return data.get("data") or {}

    def _paged(self, path: str, params: dict, key: str = "items") -> list[dict]:
        """Gom hết trang. Lark trả ``page_token`` rỗng khi hết."""
        out: list[dict] = []
        token = ""
        while True:
            p = dict(params, page_size=params.get("page_size", 100))
            if token:
                p["page_token"] = token
            data = self._get(path, p)
            out.extend(data.get(key) or [])
            token = data.get("page_token") or ""
            if not data.get("has_more") or not token:
                return out

    # ----------------------------- Wiki + Docx -----------------------------

    def wiki_nodes(self, space_id: str) -> list[dict]:
        """Toàn bộ node trong một wiki space (duyệt cả node con).

        Mỗi node có thêm ``path`` = đường dẫn tiêu đề từ gốc, để phân loại nhạy cảm
        theo nhánh chứ không chỉ theo tên node.
        """
        out: list[dict] = []

        def walk(parent: str, prefix: str) -> None:
            params = {"space_id": space_id}
            if parent:
                params["parent_node_token"] = parent
            for n in self._paged(f"/open-apis/wiki/v2/spaces/{space_id}/nodes", params):
                title = n.get("title") or ""
                n["path"] = f"{prefix}/{title}" if prefix else title
                out.append(n)
                if n.get("has_child"):
                    walk(n.get("node_token") or "", n["path"])

        walk("", "")
        return out

    def wiki_node(self, node_token: str) -> dict:
        """Giải một wiki node token → ``{obj_token, obj_type, title}``.

        Cần vì token thấy trên URL wiki (``/wiki/RTSpww...``) **không phải** token của
        tài liệu bên dưới. Gọi API docx/bitable bằng token wiki sẽ trả "param invalid".
        """
        data = self._get("/open-apis/wiki/v2/spaces/get_node",
                         {"token": node_token, "obj_type": "wiki"})
        node = data.get("node") or {}
        return {"obj_token": node.get("obj_token") or "",
                "obj_type": node.get("obj_type") or "",
                "title": node.get("title") or ""}

    def resolve(self, token: str) -> dict:
        """Nhận token bất kỳ (wiki node hoặc token tài liệu) → tài liệu thật.

        Thử giải wiki trước; không phải wiki thì trả lại chính token đó.
        """
        try:
            node = self.wiki_node(token)
            if node["obj_token"]:
                return node
        except LarkDocsError:
            pass
        return {"obj_token": token, "obj_type": "", "title": ""}

    def docx_sections(self, doc_token: str, *, doc_title: str = "",
                      max_chars: int = 1800) -> list[dict]:
        """Cắt tài liệu docx thành mục theo heading.

        Trả list ``{title, content, block_id, heading_path, source_url}``. ``block_id`` là
        block heading mở đầu mục → link trích dẫn trỏ đúng đoạn.
        """
        blocks = self._paged(f"/open-apis/docx/v1/documents/{doc_token}/blocks",
                             {"document_revision_id": -1})
        sections: list[dict] = []
        cur = {"title": doc_title, "block_id": "", "heading_path": doc_title, "buf": []}
        trail: dict[int, str] = {}

        def flush() -> None:
            body = " ".join(x for x in cur["buf"] if x).strip()
            if not body:
                return
            # Mục dài thì cắt nhỏ — chunk quá to làm loãng kết quả RAG.
            for i in range(0, len(body), max_chars):
                part = body[i:i + max_chars]
                sections.append({
                    "title": cur["title"] or doc_title,
                    "content": part,
                    "block_id": cur["block_id"],
                    "heading_path": cur["heading_path"],
                    "source_url": self._docx_url(doc_token, cur["block_id"]),
                })

        for b in blocks:
            btype = b.get("block_type")
            if btype not in _TEXT_BLOCK_TYPES:
                continue
            text = self._block_text(b)
            level = _HEADING_TYPES.get(btype)
            if level:
                flush()
                trail[level] = text
                for deeper in [k for k in trail if k > level]:
                    trail.pop(deeper, None)
                cur = {
                    "title": text,
                    "block_id": b.get("block_id") or "",
                    "heading_path": " › ".join(
                        [doc_title] + [trail[k] for k in sorted(trail)]),
                    "buf": [],
                }
            else:
                cur["buf"].append(text)
        flush()
        return sections

    def _docx_url(self, doc_token: str, block_id: str = "") -> str:
        if not self.doc_host:
            return ""
        url = f"{self.doc_host}/docx/{doc_token}"
        return f"{url}#{block_id}" if block_id else url

    @staticmethod
    def _block_text(block: dict) -> str:
        """Gom text của một block (docx v1 để text trong key theo tên loại block)."""
        for value in block.values():
            if isinstance(value, dict) and "elements" in value:
                return "".join(
                    (e.get("text_run") or {}).get("content", "")
                    for e in value.get("elements") or []
                ).strip()
        return ""

    # ----------------------------- Bitable (Lark Base) -----------------------------

    def bitable_tables(self, app_token: str) -> list[dict]:
        """Danh sách bảng trong một Base."""
        return self._paged(f"/open-apis/bitable/v1/apps/{app_token}/tables", {})

    def bitable_records(self, app_token: str, table_id: str) -> list[dict]:
        """Toàn bộ record của một bảng. Mỗi record: ``{record_id, fields}``."""
        return self._paged(
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records", {})

    def bitable_url(self, app_token: str, table_id: str, record_id: str = "") -> str:
        if not self.doc_host:
            return ""
        url = f"{self.doc_host}/base/{app_token}?table={table_id}"
        return f"{url}&record={record_id}" if record_id else url

    # ----------------------------- Sheets -----------------------------

    def sheet_list(self, spreadsheet_token: str) -> list[dict]:
        """Các sheet trong một bảng tính. Mỗi sheet: ``{sheet_id, title}``."""
        data = self._get(
            f"/open-apis/sheets/v3/spreadsheets/{spreadsheet_token}/sheets/query")
        return [{"sheet_id": s.get("sheet_id"), "title": s.get("title") or ""}
                for s in (data.get("sheets") or [])]

    def sheet_rows(self, spreadsheet_token: str, sheet_id: str, *,
                   max_rows: int = 200, max_cols: str = "Z") -> list[list]:
        """Đọc ô của một sheet, trả list dòng.

        Giới hạn mặc định 200 dòng: sheet báo cáo thường có vài nghìn dòng, nạp hết vào
        kho tri thức là làm loãng RAG và ngập hàng chờ duyệt. Cần nhiều hơn thì chỉnh
        ``KD_SHEET_ROWS``.
        """
        rng = f"{sheet_id}!A1:{max_cols}{max_rows}"
        data = self._get(f"/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/values/{rng}")
        return (data.get("valueRange") or {}).get("values") or []

    def sheet_url(self, spreadsheet_token: str, sheet_id: str = "") -> str:
        if not self.doc_host:
            return ""
        url = f"{self.doc_host}/sheets/{spreadsheet_token}"
        return f"{url}?sheet={sheet_id}" if sheet_id else url

    # ----------------------------- Drive -----------------------------

    def drive_files(self, folder_token: str) -> list[dict]:
        """File trong một folder Drive. Mỗi file: ``{token, name, type, url}``."""
        return self._paged("/open-apis/drive/v1/files",
                           {"folder_token": folder_token}, key="files")
