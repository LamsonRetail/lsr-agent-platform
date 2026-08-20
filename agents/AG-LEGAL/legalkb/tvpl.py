"""Adapter thuvienphapluat.vn — tìm và lấy TOÀN VĂN văn bản qua HTML.

## Vì sao không cần đăng nhập

Kiểm live 19/08/2026:

| Việc | Ẩn danh | Cần login |
|---|---|---|
| Trang tìm kiếm → danh sách văn bản (`lawid`, tiêu đề, URL) | ✅ | |
| Trang văn bản → **toàn văn** (`div#divContentDoc`) | ✅ 27.416 ký tự, đủ từ đầu tới hết phụ lục | |
| Tải file .doc/.pdf gốc | ❌ ("Bạn Chưa Đăng Nhập" ×7) | ✅ |

Toàn văn có sẵn ẩn danh nên **không lưu mật khẩu của ai** và không tải hàng loạt tài sản
có thu phí. Ta lưu **text** đã trích + link về trang gốc — đủ cho việc index và tra cứu.
Muốn bản .doc gốc thì đặt `TVPL_COOKIE` (cookie phiên do người dùng tự lấy từ browser,
KHÔNG phải mật khẩu) — xem `download_original()`.

## Header browser + giãn cách: xem `legalkb/web.py`

Nguồn này 403 với header mặc định của urllib. Header và giãn cách theo host để ở `web.py`
vì cả ba adapter cần y như nhau — hai bản copy sẽ trôi lệch nhau.
"""
import os
import re
import urllib.parse

from legalkb import web

BASE = "https://thuvienphapluat.vn"
# URL tìm kiếm mặc định (owner cung cấp 19/08). `type` = loại văn bản, `area` = lĩnh vực —
# đổi/thêm nguồn với tham số khác làm trên console, không sửa code.
DEFAULT_SEARCH = (BASE + "/page/tim-van-ban.aspx?keyword=&type=3&match=True&area=0")

REQUEST_GAP = float(os.environ.get("TVPL_GAP_SECONDS", "2"))
MAX_DOCS = int(os.environ.get("TVPL_MAX_DOCS", "25"))
TIMEOUT = int(os.environ.get("TVPL_TIMEOUT", "40"))

# <p class="nqTitle" lawid='720746'> <a ... href="https://.../...-720746.aspx">Tiêu đề</a>
ROW = re.compile(
    r'<p\s+class="nqTitle"[^>]*lawid=[\'"](\d+)[\'"][^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    re.S | re.I)
# Toàn văn: div#divContentDoc, hoặc fallback class cldivContentDocVn
DOC_BODY = re.compile(r'<div[^>]+id="divContentDoc"[^>]*>(.*?)</div>\s*(?:<div[^>]+id="|<script)',
                      re.S | re.I)
DOC_BODY_ALT = re.compile(r'class="cldivContentDocVn"[^>]*>(.*?)$', re.S | re.I)


def get(url, cookie=None, timeout=None):
    return web.get(url, cookie=cookie if cookie is not None else os.environ.get("TVPL_COOKIE", ""),
                   timeout=timeout or TIMEOUT, gap=REQUEST_GAP, referer=BASE + "/")


def search(url=None, cookie=None, max_docs=None, log=print):
    """Đọc trang tìm kiếm → danh sách văn bản.

    Bỏ các link hướng dẫn (`v=tvpl-hdsd…&step=`) — chúng cũng nằm dưới /van-ban/ nên nếu
    lọc theo đường dẫn thì lẫn vào, thành ra "tìm được văn bản" mà thực chất là trang trợ giúp.
    """
    html = get(url or DEFAULT_SEARCH, cookie=cookie)
    out, seen = [], set()
    for lawid, href, title in ROW.findall(html):
        if "tvpl-hdsd" in href or "&step=" in href:
            continue
        if lawid in seen:
            continue
        seen.add(lawid)
        out.append({"lawid": lawid,
                    "url": urllib.parse.urljoin(BASE, href.split("?")[0]),
                    "title": web.clean(title)})
        if len(out) >= (max_docs or MAX_DOCS):
            break
    log(f"[tvpl] trang tìm kiếm → {len(out)} văn bản")
    return out


def fetch_text(url, cookie=None):
    """Toàn văn của một văn bản. Trả "" nếu không tìm thấy khối nội dung."""
    html = get(url, cookie=cookie)
    m = DOC_BODY.search(html) or DOC_BODY_ALT.search(html)
    if not m:
        return ""
    return web.to_text(m.group(1)[:600_000])


def download_original(url, cookie=None):
    """Tải file gốc (.doc/.pdf) — CHỈ chạy khi có `TVPL_COOKIE` của người dùng.

    Cố tình KHÔNG nhận email/mật khẩu: agent không nên giữ mật khẩu của ai, và toàn văn
    đã lấy được không cần login nên đây chỉ là tuỳ chọn. Người dùng tự lấy cookie phiên
    từ browser (giống cách làm với NotebookLM `storage_state.json`).
    """
    cookie = cookie if cookie is not None else os.environ.get("TVPL_COOKIE", "")
    if not cookie:
        raise RuntimeError("cần TVPL_COOKIE để tải file gốc; không có thì dùng fetch_text()")
    html = get(url, cookie=cookie)
    m = re.search(r'href="([^"]+\.(?:doc|docx|pdf))"', html, re.I)
    if not m:
        raise RuntimeError("không thấy link tải trong trang (cookie hết hạn hoặc gói không "
                           "cho tải?)")
    file_url = urllib.parse.urljoin(BASE, m.group(1))
    return web.get_bytes(file_url, cookie=cookie, gap=REQUEST_GAP, referer=url), file_url
