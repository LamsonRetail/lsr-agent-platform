"""Lấy trang web từ nguồn công khai — header browser + giãn cách theo từng host.

Ba adapter (`tvpl`, `chinhphu`, `luatvietnam`) đều cần đúng hai thứ này, nên để một chỗ:

* **Header browser là bắt buộc.** Header mặc định của urllib bị 403 ở cả tvpl và
  luatvietnam. Đây là lọc theo header, không phải JS challenge/CAPTCHA — không có chuyện
  lách bot-detection.
* **Giãn cách theo host, không phải toàn cục.** Ba nguồn khác nhau thì không có lý gì
  phải chờ nhau; nhưng hai lời gọi vào CÙNG một nguồn thì phải cách nhau. Làm nguồn quá
  tải là cách nhanh nhất để mất quyền truy cập, mà S4 chạy mỗi tuần một lần nên chẳng
  cần nhanh.
"""
import html as html_mod
import os
import re
import time
import urllib.parse
import urllib.request

DEFAULT_GAP = float(os.environ.get("WEB_GAP_SECONDS", "2"))
TIMEOUT = int(os.environ.get("WEB_TIMEOUT", "40"))

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
}

_last = {}


def _host(url):
    return urllib.parse.urlsplit(url).netloc.lower()


def _wait(url, gap):
    h = _host(url)
    left = (gap if gap is not None else DEFAULT_GAP) - (time.time() - _last.get(h, 0.0))
    if left > 0:
        time.sleep(left)
    _last[h] = time.time()


def _open(url, cookie=None, timeout=None, gap=None, referer=None):
    _wait(url, gap)
    h = dict(HEADERS)
    if referer:
        h["Referer"] = referer
        h["Sec-Fetch-Site"] = "same-origin" if _host(referer) == _host(url) else "cross-site"
    if cookie:
        h["Cookie"] = cookie
    return urllib.request.urlopen(urllib.request.Request(url, headers=h),
                                  timeout=timeout or TIMEOUT)


def get(url, cookie=None, timeout=None, gap=None, referer=None):
    with _open(url, cookie, timeout, gap, referer) as r:
        return r.read().decode("utf-8", "replace")


def get_bytes(url, cookie=None, timeout=None, gap=None, referer=None):
    with _open(url, cookie, timeout or TIMEOUT * 3, gap, referer) as r:
        return r.read()


def clean(s):
    """Đoạn HTML → một dòng chữ sạch (dùng cho tiêu đề, số hiệu)."""
    return re.sub(r"\s+", " ", html_mod.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def to_text(fragment, drop=()):
    """Khối HTML → văn bản nhiều dòng.

    `drop` là các dòng nút bấm của giao diện lẫn trong nội dung (ví dụ luatvietnam chèn
    "Đang theo dõi" sau **mỗi khoản**). Không bỏ thì bản lưu đầy rác và người đọc sau
    tưởng là nội dung văn bản.
    """
    txt = html_mod.unescape(re.sub(r"<[^>]+>", "\n", fragment or ""))
    txt = re.sub(r"[ \t\xa0]+", " ", txt)
    if drop:
        skip = {d.strip().lower() for d in drop}
        txt = "\n".join(l for l in txt.split("\n") if l.strip().lower() not in skip)
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", txt).strip()
