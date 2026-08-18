"""Bộ nhớ theo từng người cho LYLY — fact bền, lưu ở DB của platform.

Fact **không nằm trong prompt**. Chúng nằm trong Postgres của platform (schema
``agent_ag_kd_mate_made``, bảng ``user_facts``), ghi bằng ``POST /v1/self/facts`` và được
``/v1/self/context`` tự trả về theo đúng ``user_ref`` ở mỗi lượt hỏi. Nhờ vậy:

  • đổi prompt không mất trí nhớ, và trí nhớ không làm phình prompt;
  • mỗi người chỉ thấy fact của chính mình — không rò sang người khác;
  • xoá được (đây là dữ liệu về nhân viên, phải xoá được khi họ yêu cầu).

**Chỉ ghi FACT CÔNG VIỆC**, không ghi nội dung hội thoại: người này thuộc nhóm nào, phụ
trách SKU/campaign nào, hay hỏi chỉ số gì. Đủ để lần sau trả lời đúng trọng tâm mà không
biến DB thành kho lưu câu chữ của nhân viên.

**Chỉ ghi khi lặp lại ≥2 lần.** Hỏi một lần về một SKU không có nghĩa là phụ trách nó. Ghi
vội thì DB đầy nhiễu, ngữ cảnh loãng, và LYLY trả lời lệch trọng tâm — tệ hơn là không nhớ
gì.

Đếm bằng bộ đếm trong tiến trình, **không** đếm bằng ``recent_turns``: mỗi lần gọi Chat API
platform mở một session mới (``web-<random>``), nên ``recent_turns`` luôn rỗng và bộ đếm
theo session sẽ không bao giờ đạt ngưỡng. Một người lặp lại chủ đề là chuyện xảy ra **qua
nhiều session**, không phải trong một session.

Đánh đổi: restart agent thì bộ đếm về 0 — người dùng phải hỏi lại vài lần mới được nhớ.
Chấp nhận được, vì fact đã ghi thì nằm trong DB và không mất. Không đưa bộ đếm vào DB để
tránh biến bảng fact thành nơi chứa nửa-fact chưa đủ căn cứ.
"""

from __future__ import annotations

import re

# Trần số fact mỗi người. Vượt trần thì thôi, không ghi thêm — ngữ cảnh có hạn, và một
# người thật cũng chỉ có vài đặc điểm công việc đáng nhớ.
MAX_FACTS_PER_USER = 12

# Nhóm chuyên môn, suy từ chỉ số người ta hỏi. Đây là fact hữu ích nhất: biết người hỏi
# thuộc nhóm nào thì lần sau trả lời đúng thứ họ cần trước.
_TEAMS = (
    (r"\broas\b|\bcpc\b|\bcpm\b|ngân sách|budget|campaign|chiến dịch|quảng cáo|\bads\b",
     "thường hỏi về quảng cáo — nhiều khả năng thuộc nhóm ADS"),
    (r"\bkoc\b|\bkol\b|affiliate|\baff\b|hoa hồng|booking|người bán hàng",
     "thường hỏi về affiliate — nhiều khả năng thuộc nhóm AFF"),
    (r"tồn kho|\bsku\b|tỷ lệ (hủy|hoàn)|đơn hủy|đơn hoàn|sức khỏe shop|vận hành|đăng ký campaign",
     "thường hỏi về vận hành sàn — nhiều khả năng thuộc nhóm Vận hành"),
)

# Chỉ số cụ thể hay hỏi — nhớ để lần sau đưa lên đầu câu trả lời.
_METRICS = (
    (r"\broas\b", "ROAS"), (r"\bcpc\b", "CPC"), (r"\bcpm\b", "CPM"),
    (r"tồn kho", "tồn kho"), (r"tỷ lệ hoàn|đơn hoàn", "tỷ lệ hoàn"),
    (r"tỷ lệ hủy|đơn hủy", "tỷ lệ hủy"), (r"hoa hồng", "hoa hồng affiliate"),
    (r"ngân sách|budget", "ngân sách"), (r"doanh thu|\bgmv\b", "doanh thu/GMV"),
)

# Tên riêng của SKU / campaign / KOC. Bắt cụm sau các từ dẫn, tránh bắt bừa cả câu.
_ENTITY = re.compile(
    r"\b(sku|campaign|chiến dịch|sản phẩm|mã|koc|kol)\s+"
    r"([A-Za-zÀ-ỹ0-9][\wÀ-ỹ.\-]{1,24}(?:\s+[A-ZÀ-Ỹ][\wÀ-ỹ.\-]{1,24}){0,2})",
    re.IGNORECASE)

# Từ đứng sau từ dẫn nhưng không phải tên riêng — lọc ra kẻo nhớ "sku nào", "campaign này".
_NOT_A_NAME = {"nào", "này", "đó", "kia", "gì", "mới", "cũ", "khác", "hiện", "đang",
               "bao", "còn", "của", "trên", "trong", "có", "không"}


def _topics(text: str) -> set[str]:
    """Chủ đề rút từ MỘT câu — dùng để đếm lặp giữa các lượt."""
    low = (text or "").lower()
    found = {label for pattern, label in _TEAMS if re.search(pattern, low)}
    found |= {name for pattern, name in _METRICS if re.search(pattern, low)}
    for m in _ENTITY.finditer(text or ""):
        ent = (m.group(2) or "").strip()
        if ent and ent.split()[0].lower() not in _NOT_A_NAME:
            found.add(f"{m.group(1).lower()}:{ent}")
    return found


def _as_fact(topic: str) -> str:
    """Đổi chủ đề thành câu fact đọc được cho người."""
    if topic.startswith(("sku:", "campaign:", "chiến dịch:", "sản phẩm:", "mã:",
                         "koc:", "kol:")):
        kind, _, name = topic.partition(":")
        return f"Hay hỏi về {kind} {name} — nhiều khả năng đang phụ trách"
    if topic.startswith("thường hỏi"):
        return topic[0].upper() + topic[1:]
    return f"Hay hỏi chỉ số {topic}"


# Bộ đếm (người, chủ đề) → số lần đã hỏi. Chỉ sống trong tiến trình — xem docstring đầu file.
_seen: dict[tuple[str, str], int] = {}


def candidate_facts(question: str, ctx: dict, user_ref: str = "",
                    min_hits: int = 2) -> list[str]:
    """Fact đáng ghi sau lượt này. Rỗng = chưa đủ căn cứ, đừng ghi.

    Mỗi lần gọi cộng 1 cho từng chủ đề trong câu hỏi. Chủ đề nào chạm ``min_hits`` thì
    thành fact. Fact đã có trong ngữ cảnh thì bỏ qua (khỏi ghi trùng).
    """
    known = {f.lower() for f in (ctx.get("user_facts") or [])}
    out = []
    for topic in _topics(question):
        key = (user_ref, topic)
        _seen[key] = _seen.get(key, 0) + 1
        if _seen[key] < min_hits:
            continue
        fact = _as_fact(topic)
        if fact.lower() not in known:
            out.append(fact)
    return out


def remember(api, user_ref: str, question: str, ctx: dict) -> list[str]:
    """Ghi fact mới về người hỏi. Trả list fact đã ghi (rỗng là bình thường).

    Không ném lỗi ra ngoài: ghi nhớ hỏng thì cùng lắm là LYLY quên, **không được** làm
    hỏng câu trả lời mà người dùng đang chờ.
    """
    if not user_ref:
        return []                      # không biết là ai thì không ghi gì
    if len(ctx.get("user_facts") or []) >= MAX_FACTS_PER_USER:
        return []

    written = []
    for fact in candidate_facts(question, ctx, user_ref):
        try:
            api("POST", "/v1/self/facts",
                {"user_ref": user_ref, "fact": fact, "source": "auto:lyly"})
            written.append(fact)
        except Exception as exc:       # noqa: BLE001 — xem docstring
            print(f"[memory] ghi fact lỗi (bỏ qua): {exc}")
            break
    return written
