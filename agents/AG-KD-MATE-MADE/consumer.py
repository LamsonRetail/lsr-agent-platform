"""LYLY (AG-KD-MATE-MADE) — trợ lý team Kinh doanh MATE MADE.

Người dùng là **nhân viên sale nội bộ**, không phải khách hàng cuối. LYLY tra giá và chính
sách, soạn tin trả lời khách, gợi ý cách xử lý khách khó, và dựng biên bản họp của team.

Khung chung (poll job → lấy ngữ cảnh → trả lời → ghi lượt) theo khuôn agent mẫu
AG-MINH-ANH. Phần riêng nằm ở ``answer()`` và các hàm nhận diện ý định phía trên nó.

Bốn ràng buộc ép ngay trong code, không chỉ nhắc trong prompt — vì sale copy nguyên câu
trả lời của LYLY gửi thẳng cho khách:

  1. **Không có tri thức đã duyệt → không đưa số** (chống bịa, đo bằng OFR).
  2. **Dữ liệu hạn chế (giá vốn/chiết khấu riêng/danh sách khách) → chặn TRƯỚC khi tra tri
     thức**, chỉ người trong ``KD_CONFIDENTIAL_VIEWERS`` mới được trả lời.
  3. **Không tự duyệt chiết khấu vượt khung / công nợ / thời gian giao** — luôn đẩy về quản
     lý kinh doanh, kể cả khi sale hỏi gấp.
  4. **Mọi câu trả lời số liệu có trích dẫn nguồn + kỳ dữ liệu.**

Giá và chính sách KHÔNG nằm trong prompt — chúng nằm trong kho tri thức đã duyệt và được
platform đưa vào ngữ cảnh mỗi lượt (xem ``kd_sync.py``). Đổi giá = sửa file gốc trên Lark,
không phải sửa prompt.

Chạy:  LSR_AGENT_TOKEN=... python3 consumer.py
Docker: docker compose up   (xem docker-compose.yml cùng thư mục)
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import meeting_note

PLATFORM = os.environ.get("LSR_PLATFORM_URL", "https://platform.34-126-154-135.sslip.io").rstrip("/")
TOKEN = os.environ.get("LSR_AGENT_TOKEN", "")
AGENT_ID = os.environ.get("LSR_AGENT_ID", "AG-KD-MATE-MADE")
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"

# Ai được xem dữ liệu hạn chế (giá vốn, chiết khấu, danh sách khách hàng).
# Danh sách email/open_id, phân tách bằng dấu phẩy. Trưởng nhóm KD chốt trước golive.
# RỖNG = không ai được xem — cố ý fail-closed: thà không trả lời còn hơn lộ giá vốn.
CONFIDENTIAL_VIEWERS = {
    v.strip().lower()
    for v in os.environ.get("KD_CONFIDENTIAL_VIEWERS", "").split(",")
    if v.strip()
}

DISCLAIMER = ("_Số liệu tra từ kho nội bộ đã duyệt — anh/chị check lại link nguồn trước "
              "khi báo khách nhé._")

# Câu từ chối chuẩn khi không có dữ liệu. Cố định một câu để sale quen và nhận ra ngay
# rằng LYLY KHÔNG biết, thay vì đọc lướt một đoạn dài rồi tưởng là có.
NO_DATA = "Cái này em chưa có, anh/chị hỏi lại quản lý nhé."

# Chủ đề dữ liệu hạn chế. Dùng regex vì tiếng Việt cùng một thứ có nhiều cách gọi
# ("giá vốn" / "giá nhập" / "cost"), mà lọt ở đây nghĩa là lộ giá vốn ra ngoài team.
RESTRICTED = (
    (r"giá vốn|gia von|giá nhập|giá gốc|cost price|\bcogs\b|giá mua vào",
     "giá vốn"),
    (r"biên lợi nhuận|lợi nhuận gộp|tỷ suất lợi nhuận|\bmargin\b|\bgross profit\b",
     "biên lợi nhuận"),
    # Cố ý KHÔNG chặn "chính sách chiết khấu" chung — đó là chính sách đã ban hành, ai
    # cũng cần tra. Chỉ chặn con số áp cho một khách/đại lý CỤ THỂ.
    (r"chiết khấu riêng|chiết khấu đặc biệt|bảng chiết khấu|giá riêng cho khách|"
     r"chiết khấu thực tế (của|cho)|% chiết khấu (của|cho) (khách|đại lý)",
     "chiết khấu theo khách"),
    (r"danh sách khách|list khách|toàn bộ khách hàng|dữ liệu khách hàng|thông tin liên hệ khách",
     "danh sách khách hàng"),
    (r"công nợ|hạn mức tín dụng|dư nợ (của|khách)",
     "công nợ khách hàng"),
)

# Câu hỏi chạm các từ này = việc ngoài phạm vi agent Kinh Doanh.
OUT_OF_SCOPE = (
    r"đặt vé|book vé|vé máy bay|đặt phòng|khách sạn",
    r"cài (win|máy|phần mềm)|lỗi máy tính|reset mật khẩu|quên mật khẩu|wifi",
    r"đơn xin nghỉ|bảng lương|lương tháng|bảo hiểm xã hội|hợp đồng lao động của tôi",
)

# Người khác (không phải chủ trì) bảo chốt biên bản — trả về hướng dẫn, không tự chốt.
CONFIRM_WORDS = r"^\s*(chốt|duyệt|confirm|ok chốt)\b"

# Sale xin giảm thêm / xin duyệt ngoại lệ. LYLY KHÔNG bao giờ tự phán "được" —
# đây là tiền thật và là thẩm quyền của quản lý, không phải của trợ lý.
ASK_APPROVAL = (
    r"giảm (thêm|nữa|được không|cho khách)|bớt (thêm|nữa|chút)|"
    r"(cho|được) (giảm|bớt) \d|deal riêng|giá đặc biệt|ưu đãi riêng",
    r"cho (nợ|công nợ)|thanh toán sau|trả sau|gối đầu",
    r"giao (sớm|gấp|trong ngày|nhanh hơn)|kịp (mai|hôm nay)|ship gấp",
)

# Sale nhờ soạn tin nhắn gửi khách.
DRAFT_MSG = r"soạn (giúp|hộ|cho)?\s*(em|mình|tôi)?\s*(1|một)?\s*(tin|đoạn|câu|message|mess)|" \
            r"viết (giúp|hộ|cho)?\s*(em|mình|tôi)?\s*(tin|đoạn|câu)|nhắn gì cho khách|" \
            r"trả lời khách (thế nào|sao|kiểu gì)"

# Sale hỏi cách xử lý khách chê đắt / lưỡng lự / so sánh đối thủ.
OBJECTION = (
    (r"chê đắt|kêu đắt|nói đắt|đắt quá|mắc quá|giá cao quá", "đắt"),
    (r"suy nghĩ thêm|để em nghĩ|cân nhắc đã|hỏi lại đã|im luôn|không phản hồi", "lưỡng lự"),
    (r"so sánh với|bên kia rẻ hơn|đối thủ|shop khác|chỗ khác rẻ", "so sánh"),
)


def api(method: str, path: str, payload=None, timeout: int = 40):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(PLATFORM + path, data=data, method=method, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read().decode()
        return json.loads(b) if b else {}


# ----------------------------- phần riêng của AG-KD-MATE-MADE -----------------------------

def restricted_topics(q: str) -> list[str]:
    """Chủ đề dữ liệu hạn chế trong câu hỏi (rỗng = câu hỏi bình thường)."""
    low = (q or "").lower()
    return sorted({label for pattern, label in RESTRICTED if re.search(pattern, low)})


def may_see_confidential(user_ref: str) -> bool:
    """Người hỏi có được xem dữ liệu hạn chế không.

    Fail-closed: chưa cấu hình ``KD_CONFIDENTIAL_VIEWERS`` thì KHÔNG ai được xem.
    """
    return bool(user_ref) and user_ref.strip().lower() in CONFIDENTIAL_VIEWERS


def out_of_scope(q: str) -> bool:
    low = (q or "").lower()
    return any(re.search(p, low) for p in OUT_OF_SCOPE)


def asks_approval(q: str) -> bool:
    """Sale đang xin ngoại lệ (giảm thêm / công nợ / giao gấp)."""
    low = (q or "").lower()
    return any(re.search(p, low) for p in ASK_APPROVAL)


def objection_kind(q: str) -> str:
    """Loại tình huống khách từ chối mà sale đang hỏi cách xử lý. Rỗng = không phải."""
    low = (q or "").lower()
    for pattern, kind in OBJECTION:
        if re.search(pattern, low):
            return kind
    return ""


# Hướng xử lý + câu nói mẫu. Câu mẫu cố ý CHỪA CHỖ TRỐNG ở chỗ cần số/đặc điểm sản phẩm —
# sale điền từ dữ liệu thật, LYLY không tự bịa vào miệng khách.
_OBJECTION_PLAYBOOK = {
    "đắt": (
        "**Đừng giảm giá ngay.** Hỏi để biết khách đang so với cái gì, rồi kéo về giá trị "
        "(chất lượng, bảo hành, chi phí dùng lâu dài). Chỉ nhắc mức chiết khấu **có trong "
        "chính sách**, không tự chế.",
        "Dạ em hiểu ạ. Anh/chị đang so với sản phẩm nào ạ, để em nói rõ hơn phần khác biệt? "
        "Bên em [điểm mạnh] nên dùng lâu dài thường tiết kiệm hơn. Với số lượng anh/chị lấy "
        "thì đang có mức [chiết khấu theo chính sách] ạ.",
    ),
    "lưỡng lự": (
        "**Đừng thúc.** Chốt lại đúng điều khách còn băn khoăn và hẹn một mốc cụ thể — "
        "không để cuộc trò chuyện trôi.",
        "Dạ anh/chị cứ cân nhắc ạ. Em hỏi thật là mình còn phân vân ở giá hay ở [điểm khác] "
        "ạ? Để em gửi thêm thông tin đúng chỗ đó. Chiều mai em nhắn lại anh/chị nhé?",
    ),
    "so sánh": (
        "**Tuyệt đối không nói xấu đối thủ** — không bình luận giá hay chất lượng bên kia. "
        "Chỉ nhấn điểm khác biệt của MATE MADE và để khách tự so.",
        "Dạ bên đó cũng là lựa chọn tốt ạ. Bên em khác ở chỗ [điểm khác biệt], nên hợp với "
        "nhu cầu [...] của anh/chị hơn. Anh/chị thử so hai bên ở điểm đó xem ạ.",
    ),
}


def needs_knowledge(q: str, user_ref: str = "") -> bool:
    """Câu này có cần tra kho tri thức không.

    Các nhánh xử lý bằng luật (xã giao, xin duyệt ngoại lệ, chốt biên bản, ngoài phạm vi,
    xử lý từ chối, dữ liệu hạn chế của người ngoài phạm vi) **không** dùng tới tri thức.
    Gọi ``/v1/self/context`` cho chúng vừa tốn một round-trip, vừa bị chấm là **dùng tool
    thừa (UTR)** — bộ test đã gắn nhãn ``needs_tool: false`` cho đúng những câu này.

    Riêng nhánh dữ liệu hạn chế còn một lý do nặng hơn: không tra = không kéo nội dung mật
    vào ngữ cảnh, thì không có gì để lỡ miệng.
    """
    low = (q or "").lower()
    if re.fullmatch(r"\s*(chào|hi|hello|xin chào)\b.{0,20}", low):
        return False
    if asks_approval(q) or out_of_scope(q) or objection_kind(q):
        return False
    if re.search(CONFIRM_WORDS, q or "", re.IGNORECASE):
        return False
    if restricted_topics(q) and not may_see_confidential(user_ref):
        return False
    return True


def data_period(hits: list[dict]) -> str:
    """Kỳ dữ liệu của các mục tri thức dùng để trả lời.

    Người đọc cần biết số này của kỳ nào — số đúng của quý trước vẫn là số sai cho hôm nay.
    """
    periods = []
    for h in hits:
        p = h.get("source_ref") or h.get("updated_at") or h.get("created_at") or ""
        if p and p not in periods:
            periods.append(str(p))
    return " · ".join(periods[:3]) if periods else "không ghi rõ trong nguồn"


def cite(hits: list[dict], limit: int = 3) -> str:
    """Phần 'Trả lời + trích dẫn' — mỗi ý kèm link tới đúng đoạn tài liệu."""
    lines = []
    for h in hits[:limit]:
        src = h.get("source_url") or "kho tri thức nội bộ"
        body = (h.get("content") or "").strip().replace("\n", " ")
        lines.append(f"• **{h.get('title')}**: {body[:400]}\n  (nguồn: {src})")
    return "\n".join(lines)


def answer(q: str, ctx: dict, user_ref: str = "") -> str:
    """Sinh câu trả lời.

    Bản này dùng luật để chạy được ngay và test được. Khi nối model thật (Claude Agent
    SDK), truyền ``build_prompt(ctx, q)`` vào model — các nhánh chặn dưới đây vẫn giữ
    nguyên vì chúng là hàng rào an toàn, không phải phần sinh văn.
    """
    # (0) Xã giao — trả lời ngắn, KHÔNG tra tri thức (câu này nằm trong control set đo UTR).
    if re.fullmatch(r"\s*(chào|hi|hello|xin chào)\b.{0,20}", (q or "").lower()):
        return ("Dạ em chào anh/chị 👋 Em là **LYLY**, trợ lý team **Kinh doanh** MATE MADE. "
                "Anh/chị hỏi em giá, chính sách, hoặc nhờ em soạn tin trả lời khách nhé. "
                "Gửi recording cuộc họp thì em dựng biên bản luôn ạ.")

    # (1) Sale xin ngoại lệ (giảm thêm / công nợ / giao gấp).
    # Đặt TRƯỚC mọi nhánh khác: đây là tiền thật và là thẩm quyền của quản lý. LYLY tuyệt
    # đối không phán "được" — kể cả khi kho tri thức có sẵn bảng chiết khấu.
    if asks_approval(q):
        return ("Cái này **em không tự quyết được** ạ — chiết khấu ngoài khung, công nợ và "
                "thời gian giao ngoài chính sách đều phải **quản lý kinh doanh duyệt**.\n\n"
                "Anh/chị nhắn quản lý kèm: sản phẩm, số lượng, mức khách đang xin, và lý do "
                "(khách quen / đơn lớn / cạnh tranh) — có đủ 4 ý này thường duyệt nhanh hơn.\n\n"
                "Trong lúc chờ, anh/chị **đừng hứa trước với khách** giúp em nhé.")

    # (2) Ai đó bảo "chốt" trong luồng hỏi đáp → biên bản chỉ chủ trì mới chốt được.
    if re.search(CONFIRM_WORDS, q or "", re.IGNORECASE):
        return ("Biên bản chỉ được chốt bởi **chủ trì cuộc họp** ạ. Nhờ chủ trì trả lời "
                "'chốt' ngay dưới bản nháp trong nhóm — lúc đó em mới tạo Lark Docs và "
                "task. Nếu anh/chị là chủ trì thì trả lời ở đúng luồng bản nháp giúp em ạ.")

    # (3) Ngoài phạm vi → từ chối lịch sự, chỉ đúng kênh.
    if out_of_scope(q):
        return ("Việc này **ngoài phạm vi** của em ạ — em chỉ lo giá, chính sách bán hàng "
                "và biên bản họp của team Kinh doanh MATE MADE. Anh/chị liên hệ đúng bộ "
                "phận (Hành chính / IT / Nhân sự) giúp em nhé.")

    # (4) Dữ liệu hạn chế → chặn TRƯỚC khi tra tri thức. Không hé lộ một phần.
    restricted = restricted_topics(q)
    if restricted and not may_see_confidential(user_ref):
        return (f"🔒 Cái này là **dữ liệu hạn chế** của team ({', '.join(restricted)}) nên "
                "em không đưa được ạ — kể cả dạng ước lượng hay xác nhận gián tiếp.\n\n"
                "Anh/chị hỏi **quản lý kinh doanh** giúp em nhé, nói rõ mục đích dùng. Nếu "
                "anh/chị cần xem thường xuyên thì đề nghị quản lý thêm mình vào danh sách "
                "được duyệt ạ.")

    # (5) Hỏi cách xử lý khách khó → hướng xử lý + câu nói mẫu, KHÔNG cần tra tri thức.
    kind = objection_kind(q)
    if kind:
        how, sample = _OBJECTION_PLAYBOOK[kind]
        return (f"{how}\n\n**Câu nói mẫu** (anh/chị chỉnh lại cho hợp giọng mình):\n"
                f"> {sample}\n\n"
                "_Chỗ trong `[...]` anh/chị điền từ dữ liệu thật — em không tự điền số vào "
                "miệng khách._")

    hits = ctx.get("knowledge") or []
    wants_draft = bool(re.search(DRAFT_MSG, (q or "").lower()))

    # (6) Không có căn cứ đã duyệt → KHÔNG đưa số, KHÔNG ước lượng.
    if not hits:
        if wants_draft:
            return ("Em soạn được khung tin, nhưng **chưa tìm thấy dữ liệu đã duyệt** cho "
                    "phần số nên em chừa trống:\n\n"
                    "> Dạ em chào anh/chị ạ. Về [sản phẩm] mình hỏi, bên em đang có giá "
                    "[giá: hỏi quản lý], áp dụng [chính sách: hỏi quản lý]. Anh/chị cần số "
                    "lượng bao nhiêu để em báo giá chính xác ạ?\n\n"
                    f"{NO_DATA}")
        return (f"{NO_DATA}\n\n"
                "Em **chưa tìm thấy dữ liệu đã duyệt** cho câu này nên không dám đưa số.\n"
                "• Anh/chị check trực tiếp trên Lark Base / file báo cáo giúp em.\n"
                "• Nếu anh/chị biết dữ liệu này có, gửi link để team đưa vào kho — lần sau "
                "em trả lời được ngay ạ.\n\n"
                f"{DISCLAIMER}")

    # (7) Có căn cứ → trả lời gọn: số + nguồn + kỳ dữ liệu.
    parts = ["**Trả lời**", cite(hits), "",
             f"**📅 Kỳ dữ liệu:** {data_period(hits)} — số chỉ đúng tới kỳ này."]
    if wants_draft:
        parts += ["", "**✉️ Tin nhắn gửi khách** (copy được luôn):",
                  "> Dạ em chào anh/chị ạ. Về sản phẩm mình hỏi, bên em đang có thông tin "
                  "như trên ạ. Anh/chị cho em xin số lượng và địa chỉ để em báo giá cuối và "
                  "gửi thông tin chuyển khoản nhé ạ.",
                  "_Anh/chị đối chiếu số với link nguồn trước khi gửi giúp em._"]
    return "\n".join(parts) + f"\n\n{DISCLAIMER}"


def build_prompt(ctx: dict, question: str) -> str:
    """Ghép prompt stateless — dùng khi thay answer() bằng lời gọi model."""
    parts = []
    if ctx.get("instruction_block"):
        parts.append(ctx["instruction_block"])
    if ctx.get("rolling_summary"):
        parts.append("Tóm tắt hội thoại trước:\n" + ctx["rolling_summary"])
    if ctx.get("user_facts"):
        parts.append("Đã biết về người dùng:\n- " + "\n- ".join(ctx["user_facts"]))
    if ctx.get("knowledge"):
        parts.append("Dữ liệu nội bộ ĐÃ DUYỆT (chỉ được dùng những gì có ở đây, TRÍCH DẪN "
                     "source_url, NÊU RÕ kỳ dữ liệu):\n" + "\n".join(
                         f"- {h['title']}: {h['content'][:300]} "
                         f"(nguồn: {h.get('source_url') or 'nội bộ'})"
                         for h in ctx["knowledge"]))
    else:
        parts.append("KHÔNG có dữ liệu nội bộ liên quan → phải nói rõ chưa có căn cứ, "
                     "KHÔNG đưa số, KHÔNG ước lượng.")
    for t in ctx.get("recent_turns", []):
        parts.append(f"{t['role']}: {t['text']}")
    parts.append(f"user: {question}")
    return "\n\n".join(parts)


# ----------------------------- khung chung (thường không phải sửa) -----------------------------

def handle(job: dict) -> str:
    payload = job.get("payload") or {}
    q = payload.get("text", "")
    sid = job.get("session_id") or f"job-{job['id']}"
    uref = payload.get("sender_open_id") or payload.get("user_ref") or ""

    # Biên bản họp luôn cần ngữ cảnh (để đọc lại bản nháp đang chờ chốt từ recent_turns);
    # ngoài ra chỉ tra tri thức khi câu hỏi thật sự cần — xem needs_knowledge().
    is_meeting = meeting_note.is_meeting_job(job)
    if is_meeting or needs_knowledge(q, uref):
        ctx = api("GET", f"/v1/self/context?session_id={urllib.parse.quote(sid)}"
                         f"&user_ref={urllib.parse.quote(uref)}&q={urllib.parse.quote(q[:200])}")
    else:
        ctx: dict = {}

    # Việc biên bản họp đi nhánh riêng. Đây là tiến trình DUY NHẤT poll /v1/self/jobs —
    # chạy meeting_note.py thành process thứ hai sẽ khiến hai bên giành job của nhau.
    if is_meeting:
        reply_text = meeting_note.handle_meeting_job(job, ctx, api)
    else:
        reply_text = answer(q, ctx, user_ref=uref)

    if DRY_RUN and (job.get("reply_to") or {}).get("channel") in ("lark", "telegram"):
        print(f"[DRY_RUN] không gửi ra {job['reply_to'].get('channel')}: {reply_text[:80]}")
    else:
        api("POST", f"/v1/self/jobs/{job['id']}/reply", {"text": reply_text})

    api("POST", "/v1/self/session/turn", {"session_id": sid, "role": "user", "text": q,
                                          "user_ref": uref, "channel": job.get("channel")})
    r = api("POST", "/v1/self/session/turn", {"session_id": sid, "role": "assistant",
                                              "text": reply_text})
    if r.get("needs_summary"):
        old = " ".join(f"{t['role']}: {t['text']}" for t in r.get("dropped_turns", []))
        api("POST", "/v1/self/session/summary",
            {"session_id": sid, "summary": ((ctx.get("rolling_summary") or "") + " " + old)[-2000:]})
    return reply_text


def main() -> None:
    if not TOKEN:
        print("⚠️  thiếu LSR_AGENT_TOKEN — xin token ở Console hoặc chạy scripts/lsr_adopt.py")
    if not CONFIDENTIAL_VIEWERS:
        print("⚠️  KD_CONFIDENTIAL_VIEWERS rỗng — KHÔNG ai xem được giá vốn/chiết khấu/"
              "danh sách khách. Trưởng nhóm KD chốt danh sách rồi điền vào .env")
    print(f"AG-KD-MATE-MADE chạy — agent={AGENT_ID} DRY_RUN={DRY_RUN} → {PLATFORM}")
    while True:
        try:
            jobs = api("GET", "/v1/self/jobs?wait=25&max=1")
        except urllib.error.HTTPError as e:
            print(f"poll {e.code}"); time.sleep(30 if e.code == 403 else 5); continue
        except Exception as exc:
            print(f"poll lỗi: {exc}"); time.sleep(5); continue
        for job in jobs or []:
            jid = job["id"]
            try:
                out = handle(job)
                api("POST", f"/v1/self/jobs/{jid}/complete", {"result": {"ok": True}})
                print(f"✓ job#{jid} [{job.get('channel')}] → {out[:60]}")
            except Exception as exc:
                print(f"✗ job#{jid}: {exc}")
                try:
                    api("POST", f"/v1/self/jobs/{jid}/fail", {"error": str(exc)[:400]})
                except Exception:
                    pass


if __name__ == "__main__":
    main()
