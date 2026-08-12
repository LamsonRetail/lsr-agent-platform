"""Harry — trợ lý Dữ liệu & Họp chung của Lam Sơn Retail.

Poll job từ platform, tra brain (tri thức chung), soạn/chốt biên bản họp, tạo
task. Chạy: LSR_AGENT_TOKEN=... python3 consumer.py (token nhận khi enroll).
Job đến từ MỌI kênh (Lark/web chat/cron) qua cùng một hàng đợi — sửa answer()
là đủ; ngữ cảnh (brain/tóm tắt/fact) do PLATFORM giữ, không nằm ở model.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

PLATFORM = os.environ.get("LSR_PLATFORM_URL", "https://platform.34-126-154-135.sslip.io").rstrip("/")
TOKEN = os.environ["LSR_AGENT_TOKEN"]
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"

CONFIRM_WORDS = ("chốt", "duyệt", "confirm")
RECORDING_KEYS = ("audio", "recording", "file")


def api(method, path, payload=None, timeout=40):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        PLATFORM + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode()
        return json.loads(body) if body else {}


def build_prompt(ctx, question):
    """Ghép prompt stateless từ ngữ cảnh platform trả về (brain/tóm tắt/fact)."""
    parts = []
    if ctx.get("instruction_block"):
        parts.append(ctx["instruction_block"])
    if ctx.get("rolling_summary"):
        parts.append("Tóm tắt hội thoại trước:\n" + ctx["rolling_summary"])
    if ctx.get("user_facts"):
        parts.append("Đã biết về người dùng:\n- " + "\n- ".join(ctx["user_facts"]))
    if ctx.get("knowledge"):
        kb = "\n".join(
            f"- {h['title']}: {h['content'][:300]} (nguồn: {h.get('source_url') or 'nội bộ'})"
            for h in ctx["knowledge"]
        )
        parts.append("Tri thức chung liên quan (TRÍCH DẪN nguồn khi dùng):\n" + kb)
    if ctx.get("pending_minutes_draft"):
        parts.append("Biên bản nháp đang chờ xác nhận:\n" + ctx["pending_minutes_draft"])
    for t in ctx.get("recent_turns", []):
        parts.append(f"{t['role']}: {t['text']}")
    parts.append(f"user: {question}")
    return "\n\n".join(parts)


def draft_minutes(prompt, ctx):
    """<<< SỬA Ở ĐÂY: gọi model soạn biên bản nháp từ nội dung/recording trao đổi.

    Model nên lấy từ ctx.get("model"). Biên bản gồm: mục tiêu, quyết định,
    việc cần làm + người phụ trách.
    """
    return "(nháp) đã nhận nội dung họp — thay draft_minutes() bằng lời gọi model thật."


def answer_question(prompt, ctx):
    """<<< SỬA Ở ĐÂY: gọi model trả lời tri thức chung, kèm trích dẫn nguồn từ
    ctx["knowledge"]. Nếu không có tri thức phù hợp, nói rõ chưa có — không bịa.
    """
    return f"(demo) đã nhận prompt {len(prompt)} ký tự — thay answer_question() bằng lời gọi model."


def confirm_and_create_tasks(ctx, session_id):
    """Chốt biên bản: lưu vào brain (tri thức chung) + tạo task cho từng việc."""
    draft = ctx.get("pending_minutes_draft")
    if not draft:
        return "Chưa có biên bản nháp nào để chốt — gửi nội dung/recording họp trước."

    if not DRY_RUN:
        api("POST", "/v1/self/brain/save", {"title": f"Biên bản họp {session_id}", "content": draft})
        api("POST", "/v1/self/tasks", {"session_id": session_id, "source": "meeting_minutes", "content": draft})
    return "Đã lưu biên bản vào tri thức chung và tạo task cho các việc cần làm."


def is_recording_payload(payload):
    return any(k in payload for k in RECORDING_KEYS)


def answer(prompt, ctx, payload, session_id):
    text = (payload.get("text") or "").strip().lower()

    if is_recording_payload(payload):
        return draft_minutes(prompt, ctx)

    if text in CONFIRM_WORDS:
        return confirm_and_create_tasks(ctx, session_id)

    return answer_question(prompt, ctx)


def handle(job):
    payload = job.get("payload") or {}
    q = payload.get("text", "")
    sid = job.get("session_id") or f"job-{job['id']}"
    uref = payload.get("sender_open_id") or payload.get("user_ref") or ""

    ctx = api(
        "GET",
        f"/v1/self/context?session_id={sid}&user_ref={uref}&q={urllib.parse.quote(q[:200])}",
    )
    reply = answer(build_prompt(ctx, q), ctx, payload, sid)

    # Ghi lại lượt hội thoại để lượt sau có ngữ cảnh
    api(
        "POST",
        "/v1/self/session/turn",
        {"session_id": sid, "role": "user", "text": q, "user_ref": uref, "channel": job.get("channel")},
    )
    r = api("POST", "/v1/self/session/turn", {"session_id": sid, "role": "assistant", "text": reply})
    if r.get("needs_summary"):
        old = " ".join(f"{t['role']}: {t['text']}" for t in r.get("dropped_turns", []))
        summary = (ctx.get("rolling_summary", "") + " " + old)[-2000:]  # <<< nên nén bằng model
        api("POST", "/v1/self/session/summary", {"session_id": sid, "summary": summary})
    return reply


def main():
    print(f"Harry (AG-HARRY) chạy — DRY_RUN={DRY_RUN} — chờ job...")
    while True:
        try:
            jobs = api("GET", "/v1/self/jobs?wait=25&max=1")
        except urllib.error.HTTPError as e:
            time.sleep(30 if e.code == 403 else 5)
            continue
        except Exception:
            time.sleep(5)
            continue
        for job in jobs or []:
            jid = job["id"]
            try:
                reply = handle(job)
                if DRY_RUN:
                    print(f"[DRY_RUN] job#{jid} -> {reply}")
                else:
                    api("POST", f"/v1/self/jobs/{jid}/reply", {"text": reply})
                api("POST", f"/v1/self/jobs/{jid}/complete", {"result": {"ok": True}})
                print(f"✓ job#{jid}")
            except Exception as exc:
                print(f"✗ job#{jid}: {exc}")
                try:
                    api("POST", f"/v1/self/jobs/{jid}/fail", {"error": str(exc)[:400]})
                except Exception:
                    pass


if __name__ == "__main__":
    main()
