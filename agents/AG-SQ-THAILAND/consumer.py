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
import time
import urllib.error
import urllib.parse
import urllib.request

import knowledge
import minutes
import thailand_tools
import transcribe

PLATFORM = os.environ.get("LSR_PLATFORM_URL", "https://platform.34-126-154-135.sslip.io").rstrip("/")
TOKEN = os.environ.get("LSR_AGENT_TOKEN", "")
AGENT_ID = os.environ.get("LSR_AGENT_ID", "AG-SQ-THAILAND")
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"

RECORDING_TYPES = {"audio", "media", "file", "video"}
GREET_WORDS = ("chào", "chao", "hello", "hi ", "xin chao")
CAPABILITY_WORDS = ("làm được gì", "lam duoc gi", "giúp gì", "giup gi", "bạn là ai")
TASK_WORDS = ("tạo task", "tao task", "giao việc", "tạo đầu việc")

INTRO = ("Xin chào! Tôi là trợ lý của **squad Thái Lan**. Tôi giữ kho dữ liệu chung của "
         "squad và làm biên bản họp — cả nhóm hỏi gì cứ nhắn ở đây.")
CAPABILITY = ("Tôi làm 3 việc cho squad Thái Lan:\n"
              "1. **Kho dữ liệu chung** — gửi tài liệu/link vào, tôi đưa vào kho (chờ duyệt) "
              "rồi ai cũng tra được, luôn kèm nguồn.\n"
              "2. **Hỏi đáp cả squad** — qua nhóm Lark, Telegram hay web chat đều được.\n"
              "3. **Biên bản họp** — gửi recording, tôi dựng biên bản, chủ trì chốt rồi tôi "
              "lưu kho và đề xuất đầu việc.")


def api(method: str, path: str, payload=None, timeout: int = 40):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(PLATFORM + path, data=data, method=method, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read().decode()
        return json.loads(b) if b else {}


# ----------------------------- định tuyến (phần nghiệp vụ) -----------------------------

def answer(q: str, ctx: dict, payload: dict) -> str:
    low = q.lower().strip()

    # --- Luồng 3: recording → transcript → biên bản nháp ---
    if payload.get("message_type") in RECORDING_TYPES:
        return handle_recording(q, payload)

    # --- Luồng 3: chủ trì chốt biên bản ---
    if minutes.is_confirm(low):
        return handle_confirm(ctx)

    # --- Gate: không tạo task khi chưa có biên bản được chốt ---
    if any(w in low for w in TASK_WORDS):
        if not minutes.find_draft(ctx):
            return ("Chưa có biên bản nào được **xác nhận**. Quy trình: recording → biên bản "
                    "nháp → chủ trì xác nhận (`chốt`) → khi đó tôi mới đề xuất đầu việc.")
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
    return knowledge.NO_DATA


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
    """Chủ trì chốt → lưu biên bản vào kho + ĐỀ XUẤT task (không tự tạo)."""
    draft = minutes.find_draft(ctx)
    if not draft:
        return ("Chưa có biên bản nháp nào để **chốt**. Anh/chị gửi recording hoặc dán nội "
                "dung cuộc họp, tôi dựng biên bản trước đã.")

    final = minutes.confirm(draft)
    title = final.splitlines()[0].replace(minutes.HEADER, "").strip() or "Biên bản squad Thái Lan"
    knowledge.save_minutes(api, f"Biên bản: {title}", final)

    tasks = minutes.task_lines(final)
    for t in tasks:
        api("POST", "/v1/self/actions/propose",
            {"kind": "create_task", "summary": t, "source": "AG-SQ-THAILAND/minutes"})

    return (f"Đã **chốt** biên bản và lưu vào kho squad Thái Lan (chờ duyệt).\n"
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
    reply_text = answer(q, ctx, payload)

    if DRY_RUN and (job.get("reply_to") or {}).get("channel") in ("lark", "telegram"):
        print(f"[DRY_RUN] không gửi ra {job['reply_to'].get('channel')}: {reply_text[:80]}")
    else:
        # MỘT lời gọi cho mọi kênh — platform tự gửi đúng Lark/Telegram/web/A2A.
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
