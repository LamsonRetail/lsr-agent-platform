"""Adapter luatvietnam.vn — **tra cứu theo tên** (cách pháp chế đang làm tay).

Chị pháp chế mô tả cách tìm: gõ tên văn bản vào thanh TÌM KIẾM trên luatvietnam, hoặc
search Google rồi bấm vào link luatvietnam. Module này làm đúng cách 1 bằng chính endpoint
của form tìm kiếm trên trang, nên không phải đi qua Google (Google chặn scrape, mà nhờ
Google chỉ để tới cùng một trang thì thêm một điểm vỡ mà không thêm gì).

Kiểm live 20/08/2026:

| Việc | Ẩn danh |
|---|---|
| `van-ban/tim-kiem.html?Keywords=…` → danh sách văn bản | ✅ |
| Trang văn bản → toàn văn (`div.the-document-body`) | ✅ Bộ luật Lao động: 218 điều, ~258 nghìn ký tự |
| Bản hợp nhất / song ngữ / so sánh văn bản | ❌ cần tài khoản trả phí |

## Hai cái bẫy đã gặp thật

1. **72/123 kết quả là DỰ THẢO.** URL kết thúc `-d10.html` là dự thảo, `-d1.html` là văn
   bản đã ban hành. Trên trang tìm kiếm dự thảo còn nhiều hơn văn bản thật. Trích dẫn dự
   thảo như thể đang có hiệu lực là sai nghiêm trọng với việc pháp chế, nên `search()`
   **mặc định loại dự thảo** và mục nào là dự thảo thì gắn cờ `is_draft` rõ ràng.
2. **"Đang theo dõi" chèn sau mỗi khoản.** Đó là nút bấm của giao diện, không phải nội
   dung văn bản (148/218 điều bị chèn). Không lọc thì bản lưu đầy rác.
"""
import re
import urllib.parse

from legalkb import web

BASE = "https://luatvietnam.vn"
# Chính là `action` của form tìm kiếm trên trang chủ (name=Keywords).
SEARCH = BASE + "/van-ban/tim-kiem.html"

# .../<lĩnh vực>/<slug>-<id>-d<loại>.html   — d1 = đã ban hành, d10 = dự thảo
DOC_LINK = re.compile(
    r'href="?(' + re.escape(BASE) + r'/[a-z0-9\-]+/[^"\s>]*?-(\d+)-d(\d+)\.html)"?[^>]*>(.*?)</a>',
    re.S | re.I)
DRAFT_TYPE = "10"
BODY = re.compile(r'<div[^>]*class="the-document-body"[^>]*>(.*)$', re.S | re.I)
# Khối toàn văn không có thẻ đóng riêng biệt (trang lồng div rất sâu) → cắt ở mốc chân trang.
BODY_END = ('<div class="the-document-foot', 'id="tab-luoc-do"', '<footer')
UI_NOISE = ("Đang theo dõi", "In", "Chia sẻ:", "Báo lỗi", "So sánh VB", "VB song ngữ",
            "Nội dung hợp nhất", "Gửi liên kết tới Email")


def search(keyword, include_drafts=False, max_docs=20, log=print):
    """Tra cứu theo tên/từ khoá. Trả list dict `{title, url, lvn_id, is_draft}`."""
    url = SEARCH + "?" + urllib.parse.urlencode({"Keywords": keyword})
    html = web.get(url, referer=BASE + "/")
    out, seen = [], set()
    drafts = 0
    for full, doc_id, dtype, label in DOC_LINK.findall(html):
        title = web.clean(label)
        if not title or doc_id in seen:
            continue
        seen.add(doc_id)
        is_draft = dtype == DRAFT_TYPE
        drafts += is_draft
        if is_draft and not include_drafts:
            continue
        out.append({"title": title, "url": full, "lvn_id": doc_id,
                    "is_draft": is_draft, "desc": ""})
        if len(out) >= max_docs:
            break
    log(f"[luatvietnam] '{keyword}' → {len(out)} văn bản"
        + (f" (bỏ {drafts} dự thảo)" if drafts and not include_drafts else ""))
    return out


def fetch_text(url):
    """Toàn văn một văn bản. Trả "" nếu không thấy khối nội dung (nguồn đổi layout).

    Không tự ý cắt ngắn: văn bản luật bị cắt giữa mà vẫn trông hoàn chỉnh là loại lỗi tệ
    nhất ở đây — người đọc tưởng đã đọc hết điều khoản.
    """
    m = BODY.search(web.get(url, referer=SEARCH))
    if not m:
        return ""
    body = m.group(1)
    for stop in BODY_END:
        i = body.find(stop)
        if i > 0:
            body = body[:i]
            break
    return web.to_text(body, drop=UI_NOISE)
