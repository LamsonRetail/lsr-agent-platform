"""LYLY (AG-KD-MATE-MADE) — trợ lý vận hành sàn của team MATE MADE.

Người dùng là **team nội bộ ba nhóm**: ADS · AFF · Vận hành sàn. Không có sale, không ai
chat 1-1 với khách — nên LYLY **không** soạn tin bán hàng và **không** xử lý khách khó.
Việc của LYLY: trả lời câu hỏi về **số vận hành** (ROAS, tồn kho, tỷ lệ hoàn, hoa hồng aff)
và **chính sách sàn**, luôn kèm nguồn và kỳ dữ liệu; cộng với dựng biên bản họp.

Khung chung (poll job → lấy ngữ cảnh → trả lời → ghi lượt) theo khuôn agent mẫu
AG-MINH-ANH. Phần riêng nằm ở ``answer()`` và các hàm nhận diện ý định phía trên nó.

Bốn ràng buộc ép ngay trong code, không chỉ nhắc trong prompt:

  1. **Không có tri thức đã duyệt → không đưa số** (chống bịa, đo bằng OFR). Một con số
     ROAS sai dẫn tới tăng ngân sách cho campaign đang lỗ — mất tiền thật trong ngày.
  2. **Mọi số đều kèm KỲ DỮ LIỆU.** Số vận hành sàn đổi theo ngày; "ROAS 3.2" mà không nói
     của ngày nào là vô nghĩa, tệ hơn là gây hiểu nhầm.
  3. **Không tự quyết** tăng/giảm ngân sách ads, đổi giá bán, đăng ký khuyến mãi sàn, duyệt
     booking KOC hay đền bù ngoài chính sách → đẩy về người có thẩm quyền.
  4. **Dữ liệu hạn chế** (giá vốn, biên lợi nhuận, chi phí booking, dữ liệu người mua) chặn
     TRƯỚC khi tra tri thức; chỉ người trong ``KD_CONFIDENTIAL_VIEWERS`` mới được trả lời.

Số liệu KHÔNG nằm trong prompt — chúng nằm trong kho tri thức đã duyệt, sync hàng ngày từ
Lark Base (xem ``kd_sync.py``). Đổi số = sửa Base, không phải sửa prompt.

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

# Ai được xem dữ liệu hạn chế (giá vốn, biên lợi nhuận, chi phí booking KOC, dữ liệu
# người mua). Danh sách email/open_id, phân tách dấu phẩy.
# RỖNG = không ai được xem — cố ý fail-closed: thà không trả lời còn hơn lộ giá vốn.
CONFIDENTIAL_VIEWERS = {
    v.strip().lower()
    for v in os.environ.get("KD_CONFIDENTIAL_VIEWERS", "").split(",")
    if v.strip()
}

DISCLAIMER = ("_Số lấy từ kho nội bộ đã duyệt — check link nguồn trước khi quyết ngân sách "
              "hay đổi giá nhé._")

# Câu từ chối chuẩn khi không có dữ liệu. Cố định một câu để team quen và nhận ra ngay
# rằng LYLY KHÔNG biết, thay vì đọc lướt một đoạn dài rồi tưởng là có.
NO_DATA = "Cái này em chưa có, anh/chị hỏi lại quản lý nhé."

# Chủ đề dữ liệu hạn chế. Dùng regex vì tiếng Việt cùng một thứ có nhiều cách gọi
# ("giá vốn" / "giá nhập" / "cost"), mà lọt ở đây nghĩa là lộ ra ngoài phạm vi.
RESTRICTED = (
    (r"giá vốn|gia von|giá nhập|giá gốc|cost price|\bcogs\b|giá mua vào",
     "giá vốn"),
    (r"biên lợi nhuận|lợi nhuận gộp|tỷ suất lợi nhuận|\bmargin\b|lãi thực|lợi nhuận ròng",
     "biên lợi nhuận"),
    (r"chi phí booking|giá booking|hợp đồng (aff|affiliate|koc|kol)|"
     r"hoa hồng riêng|mức hoa hồng (của|cho) (koc|kol|aff)",
     "chi phí booking / hợp đồng KOC"),
    (r"danh sách (khách|người mua|buyer)|thông tin (liên hệ|cá nhân) (của )?(khách|người mua)|"
     r"số điện thoại khách|địa chỉ khách",
     "dữ liệu người mua"),
    (r"công nợ|hạn mức tín dụng|dư nợ (của|nhà cung cấp)|giá nhà cung cấp",
     "công nợ / giá nhà cung cấp"),
)

# Việc ngoài phạm vi của trợ lý vận hành sàn.
OUT_OF_SCOPE = (
    r"đặt vé|book vé|vé máy bay|đặt phòng|khách sạn",
    r"cài (win|máy|phần mềm)|lỗi máy tính|reset mật khẩu|quên mật khẩu|wifi",
    r"đơn xin nghỉ|bảng lương|lương tháng|bảo hiểm xã hội|hợp đồng lao động của tôi",
    r"hoa hồng của (em|tôi|mình)|thưởng (tháng|quý) của (em|tôi|mình)",
)

# Người khác (không phải chủ trì) bảo chốt biên bản — trả về hướng dẫn, không tự chốt.
CONFIRM_WORDS = r"^\s*(chốt|duyệt|confirm|ok chốt)\b"

# Quyết định tiêu tiền hoặc đổi giá. LYLY KHÔNG bao giờ tự phán "được" — đây là tiền thật
# và là thẩm quyền của quản lý, không phải của trợ lý. Đặt TRƯỚC mọi nhánh khác.
ASK_APPROVAL = (
    # ngân sách quảng cáo
    (r"tăng (ngân sách|budget|ngs)|giảm (ngân sách|budget)|scale (up|lên)|"
     r"(tắt|bật|dừng) (campaign|chiến dịch|ads|quảng cáo)|đổ thêm tiền|push thêm",
     "ngân sách quảng cáo"),
    # giá bán và khuyến mãi trên sàn
    (r"(đổi|giảm|tăng|set) giá bán|đăng ký (khuyến mãi|chương trình|flash ?sale|campaign)|"
     r"tạo (mã giảm|voucher|mã giảm giá)|treo (deal|voucher)|hạ giá",
     "giá bán / khuyến mãi sàn"),
    # affiliate
    (r"(tăng|đổi|chốt) (hoa hồng|commission)|book (koc|kol)|duyệt booking|ký (với )?(koc|kol)",
     "booking / hoa hồng affiliate"),
    # đền bù khách ngoài chính sách
    (r"(hoàn tiền|đền|bồi thường|tặng voucher) cho khách|refund ngoài|"
     r"xử lý ngoại lệ cho khách",
     "đền bù ngoài chính sách"),
)


def api(method: str, path: str, payload=None, timeout: int = 40):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(PLATFORM + path, data=data, method=method, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read().decode()
        return json.loads(b) if b else {}


# ----------------------------- phần riêng của LYLY -----------------------------

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


def approval_topics(q: str) -> list[str]:
    """Loại quyết định cần người duyệt (rỗng = câu hỏi tra cứu bình thường)."""
    low = (q or "").lower()
    return sorted({label for pattern, label in ASK_APPROVAL if re.search(pattern, low)})


def needs_knowledge(q: str, user_ref: str = "") -> bool:
    """Câu này có cần tra kho tri thức không.

    Các nhánh xử lý bằng luật (xã giao, xin duyệt, chốt biên bản, ngoài phạm vi, dữ liệu
    hạn chế của người ngoài phạm vi) **không** dùng tới tri thức. Gọi ``/v1/self/context``
    cho chúng vừa tốn một round-trip, vừa bị chấm là **dùng tool thừa (UTR)** — bộ test đã
    gắn nhãn ``needs_tool: false`` cho đúng những câu này.

    Riêng nhánh dữ liệu hạn chế còn một lý do nặng hơn: không tra = không kéo nội dung mật
    vào ngữ cảnh, thì không có gì để lỡ miệng.
    """
    low = (q or "").lower()
    if re.fullmatch(r"\s*(chào|hi|hello|xin chào)\b.{0,20}", low):
        return False
    if approval_topics(q) or out_of_scope(q):
        return False
    if re.search(CONFIRM_WORDS, q or "", re.IGNORECASE):
        return False
    if restricted_topics(q) and not may_see_confidential(user_ref):
        return False
    return True


def data_period(hits: list[dict]) -> str:
    """Kỳ dữ liệu của các mục tri thức dùng để trả lời.

    Quan trọng hơn ở agent này so với agent khác: số vận hành sàn đổi theo NGÀY. "ROAS 3.2"
    mà không nói của ngày nào thì người đọc sẽ mặc định là hôm nay và quyết sai ngân sách.
    """
    periods = []
    for h in hits:
        p = h.get("source_ref") or h.get("updated_at") or h.get("created_at") or ""
        if p and p not in periods:
            periods.append(str(p))
    return " · ".join(periods[:3]) if periods else "không ghi rõ trong nguồn"


def cite(hits: list[dict], limit: int = 3) -> str:
    """Phần 'Trả lời + trích dẫn' — mỗi ý kèm link tới đúng dòng dữ liệu."""
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
    # (0) Xã giao — trả lời ngắn, KHÔNG tra tri thức (nằm trong control set đo UTR).
    if re.fullmatch(r"\s*(chào|hi|hello|xin chào)\b.{0,20}", (q or "").lower()):
        return ("Dạ em chào anh/chị 👋 Em là **LYLY**, trợ lý **vận hành sàn** của MATE MADE. "
                "Anh/chị hỏi em số (ROAS, tồn kho, tỷ lệ hoàn, hoa hồng aff) hoặc chính sách "
                "sàn nhé. Gửi recording cuộc họp thì em dựng biên bản luôn ạ.")

    # (1) Quyết định tiêu tiền / đổi giá → KHÔNG tự quyết.
    # Đặt TRƯỚC mọi nhánh khác: kể cả khi kho tri thức có sẵn số, việc "có nên tăng ngân
    # sách không" vẫn là quyết định của người, không phải của trợ lý.
    approvals = approval_topics(q)
    if approvals:
        return (f"Cái này **em không tự quyết được** ạ — {', '.join(approvals)} phải do "
                "người có thẩm quyền duyệt.\n\n"
                "Em tra được **số liệu để anh/chị quyết** (hiệu quả hiện tại, kỳ dữ liệu, "
                "so với kỳ trước) — anh/chị hỏi em phần số đó nhé, rồi trình quản lý kèm "
                "con số + link nguồn.\n\n"
                "Trong lúc chờ duyệt, **đừng đổi trên Seller Center trước** giúp em ạ.")

    # (2) Ai đó bảo "chốt" trong luồng hỏi đáp → biên bản chỉ chủ trì mới chốt được.
    if re.search(CONFIRM_WORDS, q or "", re.IGNORECASE):
        return ("Biên bản chỉ được chốt bởi **chủ trì cuộc họp** ạ. Nhờ chủ trì trả lời "
                "'chốt' ngay dưới bản nháp trong nhóm — lúc đó em mới tạo Lark Docs và "
                "task. Nếu anh/chị là chủ trì thì trả lời ở đúng luồng bản nháp giúp em ạ.")

    # (3) Ngoài phạm vi → từ chối lịch sự, chỉ đúng kênh.
    if out_of_scope(q):
        return ("Việc này **ngoài phạm vi** của em ạ — em chỉ lo số vận hành sàn, chính "
                "sách sàn và biên bản họp của team MATE MADE. Anh/chị liên hệ đúng bộ phận "
                "(Hành chính / IT / Nhân sự) giúp em nhé.")

    # (4) Dữ liệu hạn chế → chặn TRƯỚC khi tra tri thức. Không hé lộ một phần.
    restricted = restricted_topics(q)
    if restricted and not may_see_confidential(user_ref):
        return (f"🔒 Cái này là **dữ liệu hạn chế** ({', '.join(restricted)}) nên em không "
                "đưa được ạ — kể cả dạng ước lượng hay xác nhận gián tiếp.\n\n"
                "Anh/chị hỏi **quản lý** giúp em nhé, nói rõ mục đích dùng. Nếu anh/chị cần "
                "xem thường xuyên thì đề nghị quản lý thêm mình vào danh sách được duyệt ạ.")

    hits = ctx.get("knowledge") or []

    # (5) Không có căn cứ đã duyệt → KHÔNG đưa số, KHÔNG ước lượng.
    # Cố ý KHÔNG kèm DISCLAIMER ở đây: câu disclaimer nói "số lấy từ kho đã duyệt, check
    # link nguồn" — dán nó vào một câu trả lời không có số và không có link thì vô nghĩa,
    # và tệ hơn là khiến câu từ chối trông như một câu trả lời có căn cứ.
    if not hits:
        return (f"{NO_DATA}\n\n"
                "Em **chưa tìm thấy dữ liệu đã duyệt** cho câu này nên không dám đưa số.\n"
                "• Anh/chị check trực tiếp trên Lark Base / Seller Center giúp em.\n"
                "• Nếu số này có trong Base rồi mà em chưa thấy, báo em để team đưa vào kho "
                "— lần sau em trả lời được ngay ạ.")

    # (6) Có căn cứ → trả lời gọn: số + nguồn + kỳ dữ liệu.
    return ("**Trả lời**\n" + cite(hits) + "\n\n"
            f"**📅 Kỳ dữ liệu:** {data_period(hits)} — số chỉ đúng tới kỳ này, "
            "hôm nay có thể đã khác.\n\n"
            f"{DISCLAIMER}")


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
        print("⚠️  KD_CONFIDENTIAL_VIEWERS rỗng — KHÔNG ai xem được giá vốn/biên lợi nhuận/"
              "chi phí booking. Quản lý chốt danh sách rồi điền vào .env")
    print(f"LYLY chạy — agent={AGENT_ID} DRY_RUN={DRY_RUN} → {PLATFORM}")
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
