"""Kho dữ liệu chung của squad — đưa tài liệu vào brain (chờ duyệt) & tra cứu có nguồn.

Nguyên tắc (USECASE luồng 1):
  • Vào kho phải có ``source_url`` (link Lark đối chứng) — không có thì hỏi lại.
  • Nội dung nhạy cảm → từ chối, không đề xuất.
  • Trả lời chỉ dựa trên tri thức ĐÃ DUYỆT và luôn trích dẫn nguồn; không có thì nói
    "chưa có", không đoán.
  • Chỉ index/đề xuất — việc duyệt do reviewer làm trên console.

Chủ file: **Thái** (xem TEAM.md). Chỉ stdlib.
"""

from __future__ import annotations

import re

SAVE_WORDS = ("lưu", "luu", "ghi vào kho", "vào kho", "cất", "index", "thêm vào kho")
SENSITIVE_WORDS = ("lương", "luong", "bảng lương", "giá vốn", "gia von", "cmnd", "cccd",
                   "căn cước", "số điện thoại khách", "sdt khách", "thông tin cá nhân",
                   "tài khoản ngân hàng", "mật khẩu", "password")
_URL = re.compile(r"https?://\S+")

# Vinh 19/08: không biết thì nói ngắn, KHÔNG bôi thêm menu/trích giá trị công ty.
NO_DATA = ("Cái này em chưa có trong kho nên em không đoán. Anh/chị gửi link Lark thì em "
           "nạp vào, lần sau em trả lời được ạ.")


def is_save_request(text: str) -> bool:
    low = text.lower()
    return any(w in low for w in SAVE_WORDS)


def is_sensitive(text: str) -> bool:
    """Dùng cho luồng LƯU vào kho — giữ nguyên chặt (kể cả giá vốn)."""
    low = text.lower()
    return any(w in low for w in SENSITIVE_WORDS)


# Vinh 19/08: Ploy phải trả lời được chi phí/giá vốn NVL (hộp, ruy băng, packaging) vì đó là
# thông tin vận hành của team cung ứng. Chỉ chặn lương/PII và giá vốn theo SKU/sản phẩm.
_QUERY_BLOCK = ("lương", "luong", "bảng lương", "thu nhập", "thưởng cá nhân", "cmnd", "cccd",
                "căn cước", "số điện thoại khách", "sdt khách", "thông tin cá nhân",
                "tài khoản ngân hàng", "mật khẩu", "password", "giá vốn sản phẩm",
                "giá vốn sku", "giá vốn từng mã", "giá vốn mã")


def is_sensitive_query(text: str) -> bool:
    """Dùng cho luồng TRẢ LỜI câu hỏi — hẹp hơn is_sensitive."""
    low = text.lower()
    return any(w in low for w in _QUERY_BLOCK)


def extract_source_url(text: str) -> str | None:
    m = _URL.search(text)
    return m.group(0).rstrip(").,;") if m else None


def title_from(text: str, source_url: str | None) -> str:
    body = text
    for w in SAVE_WORDS:
        body = re.sub(w, "", body, flags=re.IGNORECASE)
    if source_url:
        body = body.replace(source_url, "")
    body = body.strip(" :—-·\t")
    return (body[:120] or "Tài liệu squad Thái Lan").strip()


def save(api, text: str) -> str:
    """Đề xuất một mục tri thức vào brain của agent. `api` = hàm gọi API của consumer."""
    if is_sensitive(text):
        return ("Nội dung này thuộc nhóm **nhạy cảm** (lương/giá vốn/thông tin cá nhân) nên "
                "tôi không đưa vào kho chung. Nếu cần, anh/chị gửi qua kênh có kiểm soát "
                "quyền truy cập.")

    source_url = extract_source_url(text)
    if not source_url:
        return ("Cần **nguồn đối chứng** trước đã: anh/chị gửi kèm link Lark (doc/sheet/tin "
                "nhắn) của thông tin này. Không có link thì tôi không đưa vào kho — để tránh "
                "tri thức không kiểm chứng được.")

    title = title_from(text, source_url)
    api("POST", "/v1/self/brain/items", {
        "title": title,
        "content": text[:4000],
        "source_url": source_url,
        "tags": ["squad-thailand"],
        "status": "pending_review",
    })
    return (f"Đã đưa vào kho squad Thái Lan: **{title}**\nNguồn: {source_url}\n"
            "Trạng thái: **chờ duyệt** — reviewer chuyên môn duyệt xong thì cả squad tra được.")


def save_minutes(api, title: str, body: str, source_url: str = "") -> None:
    """Lưu biên bản ĐÃ CHỐT vào kho (gọi sau khi chủ trì confirm)."""
    api("POST", "/v1/self/brain/items", {
        "title": title,
        "content": body[:8000],
        "source_url": source_url,
        "tags": ["squad-thailand", "meeting-notes"],
        "status": "pending_review",
    })


# Từ chức năng, không mang nội dung — bỏ khi so khớp độ liên quan.
_STOP = {"em", "anh", "chị", "chi", "ơi", "oi", "có", "co", "biết", "biet", "không", "khong",
         "là", "la", "gì", "gi", "của", "cua", "cho", "với", "voi", "và", "va", "thế", "the",
         "nào", "nao", "tôi", "toi", "bạn", "ban", "ạ", "nhé", "nhe", "mình", "minh", "được",
         "duoc", "về", "ve", "này", "nay", "đó", "do", "cái", "cai", "làm", "lam", "tại", "tai",
         "một", "mot", "các", "cac", "thì", "thi", "nữa", "nua", "hỏi", "hoi", "giúp", "giup"}
_WORD = re.compile(r"[^0-9a-zA-ZÀ-ỹ]+")


def _tokens(s: str) -> set[str]:
    return {w for w in _WORD.split((s or "").lower()) if len(w) >= 3 and w not in _STOP}


# Từ xuất hiện trong tiêu đề của gần như mọi tài liệu → một mình nó không đủ để kết luận
# "mục này liên quan câu hỏi".
_TU_CHUNG = {"quy", "trình", "quytrinh", "định", "nghĩa", "báo", "cáo", "tài", "liệu",
             "thông", "tin", "hướng", "dẫn", "danh", "sách", "tổng", "hợp", "kế", "hoạch"}
# Mục seed/DEMO của platform: link giả, không phải tài liệu thật của công ty.
_NGUON_GIA = ("/demo-", "demo-k", "/DEMO", "example.com", "placeholder", "test-doc")


def _la_demo(h: dict) -> bool:
    """Mục tri thức seed/DEMO của platform → không được dùng để trả lời người thật."""
    src = (h.get("source_url") or "").lower()
    tit = (h.get("title") or "").lower()
    return (any(k.lower() in src for k in _NGUON_GIA)
            or src.startswith("demo") or tit.startswith("[demo")
            or "demo" in src.split("/")[-1])


def answer_from_knowledge(ctx: dict, q: str = "") -> str | None:
    """Trả lời từ tri thức đã duyệt — luôn kèm nguồn, và CHỈ khi thật sự liên quan.

    Platform trả về mục tri thức gần nhất theo RAG, nhưng "gần nhất" không có nghĩa là
    "liên quan". Hai lần đã sai thật:
      1. câu hỏi văn hoá công ty bị gán một mục DEMO của platform;
      2. "có những quy trình gì" (19/08) bị gán mục seed DEMO "Quy trình xử lý đổi trả"
         — quy trình cửa hàng bán lẻ, không liên quan TMĐT Thái Lan.

    Nên có 3 lớp chặn: bỏ mục nguồn DEMO/placeholder · bỏ mục điểm thấp · và đòi trùng
    ≥2 từ khoá, hoặc 1 từ khoá trong tiêu đề nhưng từ đó phải đặc trưng (không phải
    "quy trình", "báo cáo"... vốn xuất hiện ở mọi tài liệu). Không đạt → None để lớp sau
    (tool/model) xử lý.
    """
    hits = ctx.get("knowledge") or []
    if not hits:
        return None
    qt = _tokens(q)
    for h in hits:
        if _la_demo(h):
            continue
        score = h.get("score", h.get("similarity"))
        if isinstance(score, (int, float)) and score < 0.5:
            continue
        if qt:
            title_t = _tokens(h.get("title"))
            body_t = _tokens((h.get("content") or "")[:800])
            overlap = qt & (title_t | body_t)
            manh = {t for t in (overlap & title_t) if len(t) >= 4 and t not in _TU_CHUNG}
            if not (len(overlap) >= 2 or manh):
                continue
        src = h.get("source_url") or "kho tri thức nội bộ (chưa có link đối chứng)"
        return f"{h.get('title')}: {(h.get('content') or '')[:400]}\n\n(nguồn: {src})"
    return None
