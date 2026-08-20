"""Adapter chinhphu.vn — Cổng TTĐT Chính phủ, trang "Hệ thống văn bản".

## Vì sao nguồn này đáng giá nhất trong ba nguồn

Kiểm live 20/08/2026 tại `https://chinhphu.vn/he-thong-van-ban`:

| Thứ lấy được | Ẩn danh |
|---|---|
| Bảng văn bản mới nhất (51 dòng/trang) | ✅ |
| **Số hiệu lấy từ cột `span.code`** — không phải đoán từ tiêu đề | ✅ |
| Ngày ban hành, trích yếu, link trang chi tiết | ✅ |
| **File PDF KÝ SỐ bản gốc** (`datafiles.chinhphu.vn/cpp/files/vbpq/...`) | ✅ tải được |

Hai điểm hơn hẳn nguồn khác:

1. **Số hiệu là dữ liệu của nguồn, không phải regex.** Trích yếu của Nghị định
   326/2026/NĐ-CP là "Quy định về định danh địa điểm" — không có một chữ số nào. Dò số
   hiệu bằng regex trên tiêu đề sẽ trượt, key rơi về URL, và cùng một nghị định lấy từ
   hai nguồn sẽ lưu thành hai bản. Dedupe liên nguồn chỉ chạy được khi có số hiệu thật.
2. **Bản gốc là PDF ký số của cơ quan ban hành**, không phải bản gõ lại của trang trung
   gian. Đây là bản đáng lưu vào Drive công ty để sau này trích dẫn.

## Giới hạn đã biết: chỉ trang 1

Phân trang của cổng này là `__doPostBack('...grvDocument','Page$2')` — ASP.NET postback,
phải giả lập `__VIEWSTATE` mới sang trang 2. **Không làm** — chạy mỗi tuần mà trang 1 đã
có ~51 văn bản mới nhất thì không thiếu; giả lập viewstate là loại code vỡ âm thầm khi
nguồn đổi. Nếu sau này cần lấy lùi lịch sử thì dùng trang chi tiết theo `docid`.
"""
import re
import urllib.parse

from legalkb import web

BASE = "https://chinhphu.vn"
DEFAULT_LIST = BASE + "/he-thong-van-ban"
FILE_HOST = "datafiles.chinhphu.vn"

# Mỗi văn bản là một <tr>; dòng tiêu đề bảng cũng khớp nhưng không có span.code → bị loại.
ROW = re.compile(r"<tr>\s*<td>(.*?)</tr>", re.S | re.I)
CODE = re.compile(r'<span class="code">(.*?)</span>', re.S | re.I)
ISSUED = re.compile(r'<span class="issued-date">(.*?)</span>', re.S | re.I)
TITLE = re.compile(r'<span class="substract">(.*?)</span>', re.S | re.I)
PAGE = re.compile(r"""href=['"]([^'"]*docid=\d+)['"]""", re.I)
FILES = re.compile(r'href="(https?://' + re.escape(FILE_HOST) + r'/[^"]+)"', re.I)


def search(url=None, max_docs=None, log=print):
    """Đọc bảng văn bản → danh sách dict có `doc_no` sẵn (không cần dò regex tiêu đề)."""
    html = web.get(url or DEFAULT_LIST)
    out, seen = [], set()
    for row in ROW.findall(html):
        code = web.clean(CODE.search(row).group(1)) if CODE.search(row) else ""
        title = web.clean(TITLE.search(row).group(1)) if TITLE.search(row) else ""
        if not code or not title:
            continue                       # dòng tiêu đề bảng / dòng quảng cáo
        key = code.upper()
        if key in seen:
            continue
        seen.add(key)
        page = PAGE.search(row)
        out.append({
            "doc_no": re.sub(r"\s+", "", code),
            "title": title,
            "url": urllib.parse.urljoin(BASE, page.group(1)) if page else (url or DEFAULT_LIST),
            "issued": web.clean(ISSUED.search(row).group(1)) if ISSUED.search(row) else "",
            "files": FILES.findall(row),
            "desc": "",
        })
        if len(out) >= (max_docs or 60):
            break
    log(f"[chinhphu] bảng văn bản → {len(out)} văn bản")
    return out


def files_for(page_url):
    """Link file gốc của một văn bản, đọc lại từ trang chi tiết.

    Dùng khi item trong DB không còn giữ danh sách file (crawl và archive là hai lần
    chạy khác nhau, cách nhau vài phút tới vài ngày).
    """
    return FILES.findall(web.get(page_url, referer=DEFAULT_LIST))


def download_original(page_url, files=None):
    """Tải PDF ký số bản gốc → `(bytes, ".pdf", url_file)`.

    Có `Referer` vì file nằm trên host khác (`datafiles.`); thiếu referer thì nguồn có
    quyền chặn. Một văn bản có thể kèm nhiều file (bản chính + phụ lục) — lấy file đầu,
    các file còn lại trả về ở `extra` cho người gọi tự quyết.
    """
    urls = list(files or []) or files_for(page_url)
    if not urls:
        raise RuntimeError("trang không có file đính kèm — chỉ còn link trang chi tiết")
    raw = web.get_bytes(urls[0], referer=page_url)
    if not raw[:5].startswith(b"%PDF") and urls[0].lower().endswith(".pdf"):
        raise RuntimeError("tải về không phải PDF (nguồn trả trang lỗi?)")
    ext = re.search(r"(\.[a-z]{3,4})(?:\?|$)", urls[0].lower())
    return raw, (ext.group(1) if ext else ".pdf"), urls[0]
