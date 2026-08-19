"""Trợ lý Squad Thái Lan (AG-SQ-THAILAND) — consumer.

Nhận job từ MỌI kênh (Lark · Telegram · web chat · A2A) qua cùng một hàng đợi của
platform, định tuyến sang 3 luồng của USECASE.md:

  1. kho dữ liệu chung  → knowledge.py   (chủ file: Thái)
  2. hỏi đáp cả squad   → knowledge.py + ngữ cảnh platform
  3. biên bản họp       → transcribe.py + minutes.py  (chủ file: Hương)

Khung chung bên dưới **thường không phải sửa** (chủ file: owner). Nguyên tắc platform:
  • KHÔNG cần biết tin đến từ kênh nào — reply() để platform gửi đúng chỗ.
  • KHÔNG giữ lịch sử hội thoại trong tiến trình — platform giữ.
  • KHÔNG cầm secret của Lark/Telegram — đi qua connector dùng chung.

Chạy:  LSR_AGENT_TOKEN=... python3 consumer.py      ·      Docker: docker compose up
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import knowledge
import minutes
import model
import thailand_tools
import transcribe

PLATFORM = os.environ.get("LSR_PLATFORM_URL", "https://platform.34-126-154-135.sslip.io").rstrip("/")
TOKEN = os.environ.get("LSR_AGENT_TOKEN", "")
AGENT_ID = os.environ.get("LSR_AGENT_ID", "AG-SQ-THAILAND")
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"

# Job nhận được trong ~90s đầu sau khi bật = job ĐÃ nằm chờ trong hàng đợi (bot vừa tắt/
# restart) → nói thật là trả lời trễ, thay vì im lặng xuất hiện sau nhiều giờ.
START_TS = time.time()
STALE_WINDOW = 90
LATE_NOTE = ("_(Em vừa được bật lại nên trả lời trễ — tin của anh/chị nằm trong hàng đợi. "
             "Không mất tin nào ạ.)_")

RECORDING_TYPES = {"audio", "media", "file", "video"}
TRANSCRIPT_HINTS = ("họp xong", "hop xong", "nội dung họp", "noi dung hop", "biên bản:",
                    "transcript", "ghi chú họp", "tóm tắt họp")
GREET_WORDS = ("chào", "chao", "hello", "hi ", "xin chao")
CAPABILITY_WORDS = ("làm được gì", "lam duoc gi", "giúp gì", "giup gi", "bạn là ai")
TASK_WORDS = ("tạo task", "tao task", "giao việc", "tạo đầu việc")

INTRO = ("Dạ em là **Ploy** — trợ lý thị trường **Thái Lan** (HAPAS TH + MATE MADE TH). "
         "Em giữ kho dữ liệu chung của squad, theo mốc BST & lịch mùa vụ Thái, và làm biên "
         "bản họp. Cả nhóm cứ tag em rồi hỏi ạ.")
# Cấu trúc đánh số + TUYÊN BỐ GIỚI HẠN QUYỀN — học từ bot Mira (KHHH) trong nhóm sharing:
# nói rõ việc gì em tự làm, việc gì phải người duyệt, để không ai kỳ vọng sai.
CAPABILITY = ("Dạ em là **Ploy**, trợ lý thị trường Thái Lan. Em làm 5 việc:\n"
              "1. **Kho dữ liệu chung** — gửi tài liệu/link vào, em đưa vào kho (chờ duyệt) "
              "rồi ai cũng tra được, luôn kèm nguồn.\n"
              "2. **Hỏi đáp cả squad** — qua nhóm Lark, Telegram hay web chat đều được.\n"
              "3. **Mốc BST** — đếm ngược tới hạn, cảnh báo quá hạn, và soi khi một mốc có "
              "nhiều phiên bản ngày giữa các nguồn.\n"
              "4. **Lịch mùa vụ Thái** — dịp lễ nào nên làm / không làm, kèm lý do.\n"
              "5. **Biên bản họp** — gửi recording hoặc dán nội dung, em dựng biên bản; "
              "chủ trì trả lời `chốt` thì em mới lưu kho và đề xuất đầu việc.\n\n"
              "Giới hạn của em, nói trước để anh/chị không chờ nhầm: em **không tự tạo task** "
              "(chỉ đề xuất, người duyệt trên console) · **không gửi tin ra ngoài** nhóm đang "
              "trao đổi · **không đưa số khi chưa có nguồn đã duyệt** · không xử lý lương / "
              "giá vốn / thông tin cá nhân khách hàng.")


def api(method: str, path: str, payload=None, timeout: int = 40):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(PLATFORM + path, data=data, method=method, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read().decode()
        return json.loads(b) if b else {}


# ----------------------------- định tuyến (phần nghiệp vụ) -----------------------------

# Phủ định đứng gần chữ chốt/duyệt → KHÔNG phải confirm ("khoan, chưa chốt nhé").
_NEG_CONFIRM = re.compile(
    r"(khoan|chưa|chua|không|khong|đừng|dung|dừng|hoãn|hoan)[^.!?\n]{0,24}"
    r"(chốt|chot|duyệt|duyet|confirm)")
_MEETING_MARKERS = minutes.DECISION_WORDS + minutes.TASK_WORDS


def is_transcript(q: str, low: str) -> bool:
    """Text dán tay có phải nội dung họp không (để dựng biên bản nháp)."""
    if len(q) > 80 and any(h in low for h in TRANSCRIPT_HINTS):
        return True
    return len(q) > 200 and sum(1 for w in _MEETING_MARKERS if w in low) >= 2


def is_real_confirm(low: str, ctx: dict) -> bool:
    """Gate HITL: chỉ coi là chủ trì chốt khi không có phủ định và không phải câu hỏi."""
    if not minutes.is_confirm(low):
        return False
    if _NEG_CONFIRM.search(low) or low.rstrip().endswith("?"):
        return False
    return bool(minutes.find_draft(ctx)) or low.startswith(minutes.CONFIRM_WORDS)


def _is_confirmed(draft_text: str) -> bool:
    return "Trạng thái: đã chốt" in draft_text


def working_note(ctx: dict) -> str:
    """Dòng 'em đang làm gì' gửi TRƯỚC khi suy luận — để người hỏi thấy logic, không chờ mù.

    Câu chữ lấy từ configs/reply_rules.json (ack_message) → sửa config là đổi, không deploy.
    """
    cfg = thailand_tools.load_config("reply_rules") or {}
    ack = cfg.get("ack_message", "⏳ Em đang xử lý…")
    hits = ctx.get("knowledge") or []
    found = (f"thấy {len(hits)} mục liên quan: " + ", ".join(
        (h.get("title") or "?")[:40] for h in hits[:3])) if hits else \
        "chưa có mục nào đã duyệt khớp câu này"
    return (f"{ack}\nEm đã kiểm: mốc BST · lịch mùa vụ · base target · kho tri thức "
            f"({found}). Giờ em suy luận thêm rồi trả lời ngay ạ.")


def answer(q: str, ctx: dict, payload: dict, notify=None) -> str:
    low = q.lower().strip()

    # --- Luồng 3: recording → transcript → biên bản nháp ---
    if payload.get("message_type") in RECORDING_TYPES:
        return handle_recording(q, payload)

    # --- Luồng 3: dán NỘI DUNG họp bằng text → biên bản nháp (USECASE: "hoặc nội dung
    # trao đổi"). Phải đứng TRƯỚC gate confirm: transcript hay chứa chữ "chốt" giữa câu.
    # Nhận diện 2 cách: có hint rõ ("họp xong", "nội dung họp"…) HOẶC text dài có ≥2 dấu
    # hiệu cuộc họp (quyết định/giao việc/hạn) — transcript thô không cần "từ khoá thần chú".
    if is_transcript(q, low):
        draft = minutes.build_draft(q, "Họp squad Thái Lan (nội dung dán tay)")
        return (draft.render() +
                "\n\nNhờ **chủ trì** kiểm rồi trả lời `chốt` để tôi lưu kho và đề xuất đầu việc.")

    # --- Luồng 3: chủ trì chốt biên bản. Chỉ là confirm khi: có chữ chốt/duyệt, KHÔNG bị
    # phủ định ("khoan/chưa/không/đừng… chốt"), không phải câu hỏi, và (đang có nháp chờ
    # hoặc chữ chốt đứng đầu câu — tránh nuốt "hạn chốt KOC"). ---
    if is_real_confirm(low, ctx):
        return handle_confirm(ctx)

    # --- Gate: không tạo task khi chưa có biên bản được chốt ---
    if any(w in low for w in TASK_WORDS):
        draft = minutes.find_draft(ctx)
        if not draft:
            return ("Chưa có biên bản nào được **xác nhận**. Quy trình: recording → biên bản "
                    "nháp → chủ trì xác nhận (`chốt`) → khi đó tôi mới đề xuất đầu việc.")
        if _is_confirmed(draft):
            return ("Biên bản gần nhất **đã chốt** và đầu việc đã được đề xuất lên console "
                    "(chờ duyệt ở đó). Giao việc mới ngoài biên bản sẽ có ở luồng giao việc "
                    "Phase 2 (`th_assignment_create`).")
        return ("Biên bản chưa được chủ trì **xác nhận**. Nhờ chủ trì trả lời `chốt` để tôi "
                "đề xuất đầu việc.")

    # --- Luồng 1: đưa tài liệu vào kho ---
    if knowledge.is_save_request(low):
        return knowledge.save(api, q)

    # --- Chặn nội dung nhạy cảm ở mọi câu hỏi ---
    if knowledge.is_sensitive(low):
        return ("Tôi **không** cung cấp/lưu thông tin nhạy cảm (lương, giá vốn, thông tin cá "
                "nhân khách hàng) qua kênh chung. Anh/chị hỏi đúng bộ phận phụ trách nhé.")

    # --- Chào hỏi / năng lực ---
    if any(w in low for w in CAPABILITY_WORDS):
        return CAPABILITY
    if any(w in low for w in GREET_WORDS):
        return INTRO

    # --- Ploy: bối cảnh thị trường Thái từ configs/ (mùa vụ, mốc BST, base target...) ---
    hit = thailand_tools.route(low)
    if hit:
        return hit

    # --- Luồng 2: trả lời từ tri thức đã duyệt, luôn có nguồn ---
    hit = knowledge.answer_from_knowledge(ctx)
    if hit:
        return hit

    # --- Phase 2: model với ngữ cảnh platform (LSR_MODEL_MODE=off/không CLI → về luật) ---
    # Đây là nhánh DUY NHẤT chậm (vài giây) → báo trước "đang làm gì" rồi mới suy luận.
    if model.enabled():
        if notify:
            notify(working_note(ctx))
        out = model.complete(build_prompt(ctx, q), system=model.lean_system())
        if out:
            return out
    # Bí thì KHÔNG chỉ nói "chưa có" — kèm menu dạng câu hỏi em trả lời ngay được.
    return knowledge.NO_DATA + "\n\n" + thailand_tools.suggest_menu()


def handle_recording(q: str, payload: dict) -> str:
    """Recording → transcript → biên bản nháp → xin xác nhận chủ trì."""
    title = q.strip() or f"Họp squad Thái Lan · {payload.get('message_id', '')[:8]}"
    blob = fetch_recording(payload)
    if blob is None:
        # Gateway hiện chỉ đẩy text/message_type, CHƯA có file_key/URL tải file
        # (infra/lsr-platform/event_gateway/gateway.py) — xem PLAN.md mục "Cần core".
        return ("Đã nhận recording nhưng tôi **chưa tải được file** (kênh chưa mở đường lấy "
                "file). Tạm thời anh/chị dán transcript vào đây, tôi dựng **biên bản** ngay "
                "và gửi lại để xác nhận.")

    job_id = transcribe.submit(blob, meeting_title=title)     # lỗi → TranscribeError → DLQ
    transcript = transcribe.wait(job_id)
    draft = minutes.build_draft(transcript, title)
    return (draft.render() +
            "\n\nNhờ **chủ trì** kiểm rồi trả lời `chốt` để tôi lưu kho và đề xuất đầu việc.")


def fetch_recording(payload: dict) -> bytes | None:
    """Tải file recording nếu payload có đường lấy file. Chưa có → None (trả lời nhã nhặn)."""
    url = payload.get("file_url")
    if not url:
        return None
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def handle_confirm(ctx: dict) -> str:
    """Chủ trì chốt → lưu biên bản vào kho + ĐỀ XUẤT task (không tự tạo).

    Idempotent: biên bản đã chốt thì không chốt lại (tránh lưu kho + đề xuất task trùng).
    Reply kèm nguyên văn biên bản ĐÃ CHỐT — để lượt sau find_draft() thấy đúng trạng thái.
    """
    draft = minutes.find_draft(ctx)
    if not draft:
        return ("Chưa có biên bản nháp nào để **chốt**. Anh/chị gửi recording hoặc dán nội "
                "dung cuộc họp, tôi dựng biên bản trước đã.")
    if _is_confirmed(draft):
        return ("Biên bản gần nhất **đã chốt trước đó** — không chốt lại để tránh trùng đề "
                "xuất. Cần biên bản mới thì gửi recording / dán nội dung cuộc họp mới.")

    final = minutes.confirm(draft)
    title = final.splitlines()[0].replace(minutes.HEADER, "").strip() or "Biên bản squad Thái Lan"
    knowledge.save_minutes(api, f"Biên bản: {title}", final)

    tasks = minutes.task_lines(final)
    for t in tasks:
        api("POST", "/v1/self/actions/propose",
            {"kind": "create_task", "summary": t, "source": "AG-SQ-THAILAND/minutes"})

    return (final +
            f"\n\nĐã **chốt** biên bản và lưu vào kho squad Thái Lan (chờ duyệt).\n"
            f"Đã đề xuất {len(tasks)} đầu việc — duyệt trên console để tạo task. ✅")


# ----------------------------- khung chung (thường không phải sửa) -----------------------------

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
        parts.append("Tri thức liên quan (TRÍCH DẪN nguồn khi dùng):\n" + "\n".join(
            f"- {h['title']}: {h['content'][:300]} (nguồn: {h.get('source_url') or 'nội bộ'})"
            for h in ctx["knowledge"]))
    for t in ctx.get("recent_turns", []):
        parts.append(f"{t['role']}: {t['text']}")
    parts.append(f"user: {question}")
    return "\n\n".join(parts)


def handle(job: dict) -> str:
    payload = job.get("payload") or {}
    q = payload.get("text", "")
    sid = job.get("session_id") or f"job-{job['id']}"
    uref = payload.get("sender_open_id") or payload.get("user_ref") or ""

    ctx = api("GET", f"/v1/self/context?session_id={urllib.parse.quote(sid)}"
                     f"&user_ref={urllib.parse.quote(uref)}&q={urllib.parse.quote(q[:200])}")

    def send(text: str) -> None:
        """Gửi 1 tin về đúng kênh của job. Gọi được NHIỀU lần (ack trước, trả lời sau)."""
        if DRY_RUN and (job.get("reply_to") or {}).get("channel") in ("lark", "telegram"):
            print(f"[DRY_RUN] không gửi ra {job['reply_to'].get('channel')}: {text[:80]}")
            return
        # MỘT lời gọi cho mọi kênh — platform tự gửi đúng Lark/Telegram/web/A2A.
        api("POST", f"/v1/self/jobs/{job['id']}/reply", {"text": text})

    reply_text = answer(q, ctx, payload, notify=send)
    if time.time() - START_TS < STALE_WINDOW:
        reply_text = LATE_NOTE + "\n\n" + reply_text
    send(reply_text)

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
    print(f"Squad Thái Lan chạy — agent={AGENT_ID} DRY_RUN={DRY_RUN} → {PLATFORM}")
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
                # gồm cả TranscribeError → job vào DLQ, replay được từ console
                print(f"✗ job#{jid}: {exc}")
                try:
                    api("POST", f"/v1/self/jobs/{jid}/fail", {"error": str(exc)[:400]})
                except Exception:
                    pass


if __name__ == "__main__":
    main()
