"""lark_read — lớp đọc Lark tối giản cho AG-ASSISTANT-CHAN. CHỈ ĐỌC, không có hàm ghi.

Viết riêng cho agent này, chỉ gồm đúng phần đang dùng:
  • ``bitable_records()`` — đọc hết record một bảng Base, có phân trang
  • ``bitable_tables()``  — liệt kê bảng trong Base
  • ``wiki_nodes()``      — liệt kê tài liệu trong wiki space (cho giai đoạn tri thức)

Không dùng ``libs/lsr_lark``: đó là core (cần maintainer duyệt) và hiện chỉ lo GỬI tin,
chưa có phần đọc Base. Khi nào platform đưa phần đọc vào lib chung thì xoá file này.

**Phân trang là bắt buộc, không phải tối ưu.** Bài học thật khi khảo sát Base PMO:
đọc thiếu trang làm mất đúng các bản ghi MỚI NHẤT — 176 record thật bị đọc thành 143,
báo cáo mới nhất bị nhìn thành 30/07 thay vì 19/08, dẫn tới kết luận sai là "báo cáo trễ
21 ngày". Số liệu thiếu trang nguy hiểm hơn không có số, vì nó trông vẫn hợp lý.

Không dùng thư viện ngoài — chỉ ``urllib`` của stdlib, để agent chạy được cả khi image
chưa cài ``requests``.

Scope Lark cần cho app: ``bitable:app:read`` · ``wiki:node:read`` · ``wiki:space:read``
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

_LE_HAN = 60.0          # làm mới token trước khi hết hạn 60s
_TRANG = 500            # page_size tối đa Lark cho phép với bitable records


class LarkReadError(RuntimeError):
    """Lỗi đọc Lark. Cố ý KHÔNG no-op êm: agent trả số sai còn tệ hơn agent báo lỗi."""


class LarkRead:
    """Đọc Lark bằng tenant token.

    >>> lark = LarkRead()                       # lấy app_id/secret từ env
    >>> for rec in lark.bitable_records(app_token, table_id):
    ...     print(rec["fields"]["Project Name"])
    """

    def __init__(self, *, app_id: str | None = None, app_secret: str | None = None,
                 domain: str | None = None, timeout: int = 20) -> None:
        self.app_id = app_id or os.environ.get("LARK_APP_ID", "")
        self.app_secret = app_secret or os.environ.get("LARK_APP_SECRET", "")
        self.domain = (domain or os.environ.get(
            "LARK_DOMAIN", "https://open.larksuite.com")).rstrip("/")
        self.timeout = timeout
        self._token = ""
        self._het_han = 0.0
        if not (self.app_id and self.app_secret):
            raise LarkReadError(
                "thiếu LARK_APP_ID / LARK_APP_SECRET — không đọc được Lark. "
                "Đặt trong .env local (đã gitignore), KHÔNG commit vào git."
            )

    # ── hạ tầng ────────────────────────────────────────────────────────────────────

    def _goi(self, path: str, *, method: str = "GET", params: dict | None = None,
             body: dict | None = None, kem_token: bool = True) -> dict:
        url = self.domain + path
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items()
                                                 if v not in (None, "")})
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if kem_token:
            headers["Authorization"] = f"Bearer {self._tenant_token()}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                d = json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            raise LarkReadError(f"{method} {path} lỗi HTTP {e.code}: "
                                f"{e.read().decode()[:200]}") from e
        except urllib.error.URLError as e:
            raise LarkReadError(f"{method} {path} lỗi mạng: {e.reason}") from e
        if d.get("code") not in (0, None):
            raise LarkReadError(f"{method} {path} lỗi Lark {d.get('code')}: {d.get('msg')}")
        return d

    def _tenant_token(self) -> str:
        if self._token and time.time() < self._het_han - _LE_HAN:
            return self._token
        d = self._goi("/open-apis/auth/v3/tenant_access_token/internal",
                      method="POST", kem_token=False,
                      body={"app_id": self.app_id, "app_secret": self.app_secret})
        tok = d.get("tenant_access_token")
        if not tok:
            raise LarkReadError(f"không lấy được tenant token: {d.get('msg')}")
        self._token = tok
        self._het_han = time.time() + int(d.get("expire", 7200))
        return tok

    def _het_trang(self, path: str, params: dict, *, khoa: str = "items") -> list[dict]:
        """Duyệt HẾT trang. Có chặn vòng lặp vô hạn nếu API trả page_token không đổi."""
        ra: list[dict] = []
        token = ""
        da_thay: set[str] = set()
        while True:
            p = dict(params)
            p["page_size"] = params.get("page_size", _TRANG)
            if token:
                p["page_token"] = token
            d = self._goi(path, params=p).get("data") or {}
            ra.extend(d.get(khoa) or [])
            token = d.get("page_token") or ""
            if not d.get("has_more") or not token or token in da_thay:
                break
            da_thay.add(token)
        return ra

    # ── Base (Bitable) ─────────────────────────────────────────────────────────────

    def bitable_tables(self, app_token: str) -> list[dict]:
        return self._het_trang(f"/open-apis/bitable/v1/apps/{app_token}/tables", {})

    def bitable_records(self, app_token: str, table_id: str) -> list[dict]:
        """Trả list record dạng ``{"record_id": ..., "fields": {...}}`` — ĐỦ MỌI TRANG."""
        return self._het_trang(
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records", {})

    @staticmethod
    def bitable_url(app_token: str, table_id: str, record_id: str = "",
                    host: str | None = None) -> str:
        """Link người đọc bấm được — để agent trích dẫn nguồn thay vì nói suông."""
        h = (host or os.environ.get("LARK_DOC_HOST", "https://larksuite.com")).rstrip("/")
        u = f"{h}/base/{app_token}?table={table_id}"
        return f"{u}&record={record_id}" if record_id else u

    # ── Wiki ───────────────────────────────────────────────────────────────────────

    def wiki_nodes(self, space_id: str) -> list[dict]:
        """Liệt kê node cấp gốc của wiki space."""
        return self._het_trang(f"/open-apis/wiki/v2/spaces/{space_id}/nodes", {})
