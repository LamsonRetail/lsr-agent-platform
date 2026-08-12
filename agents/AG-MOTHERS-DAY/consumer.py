"""Consumer mẫu — poll job từ platform, dựng ngữ cảnh, trả lời, ghi nhớ.

Chạy: LSR_AGENT_TOKEN=... python3 consumer.py   (token nhận khi enroll)
Job đến từ MỌI kênh (Lark/web chat/cron) qua cùng một queue — sửa answer() là đủ.

Ngữ cảnh do PLATFORM giữ (không nằm ở model): mỗi lượt gọi /v1/self/context để lấy
instruction (version đang publish) + tóm tắt + N lượt gần nhất + fact người dùng +
tri thức liên quan (có nguồn). Nhờ vậy đổi model/credential hay restart đều không mất mạch.
"""
import json, os, subprocess, time, urllib.parse, urllib.request, urllib.error

PLATFORM = os.environ.get("LSR_PLATFORM_URL", "https://platform.34-126-154-135.sslip.io").rstrip("/")
TOKEN = os.environ["LSR_AGENT_TOKEN"]
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"

CONFIRM_WORDS = ("confirm", "duyệt", "chốt", "ok chốt", "đồng ý")

def api(method, path, payload=None, timeout=40):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(PLATFORM + path, data=data, method=method, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read().decode()
        return json.loads(b) if b else {}

def build_prompt(ctx, question):
    """Ghép prompt stateless từ ngữ cảnh platform trả về."""
    parts = []
    if ctx.get("instruction_block"):
        parts.append(ctx["instruction_block"])
    if ctx.get("rolling_summary"):
        parts.append("Tóm tắt hội thoại trước:\n" + ctx["rolling_summary"])
    if ctx.get("user_facts"):
        parts.append("Đã biết về người dùng:\n- " + "\n- ".join(ctx["user_facts"]))
    if ctx.get("knowledge"):
        kb = "\n".join(f"- {h['title']}: {h['content'][:300]} (nguồn: {h.get('source_url') or 'nội bộ'})"
                       for h in ctx["knowledge"])
        parts.append("Tri thức liên quan (TRÍCH DẪN nguồn khi dùng):\n" + kb)
    for t in ctx.get("recent_turns", []):
        parts.append(f"{t['role']}: {t['text']}")
    parts.append(f"user: {question}")
    return "\n\n".join(parts)

def answer(prompt, ctx):
    """Gọi Claude qua CLI `claude` (subscription owner, KHÔNG API key — auth: subscription
    theo docs/AGENT_RUNTIME.md). Instruction/refusal-policy nằm ở ctx["instruction_block"]
    (version publish trên Console no-code), không hard-code ở đây.
    """
    model = ctx.get("model") or "claude-sonnet-5"
    try:
        r = subprocess.run(
            ["claude", "-p", prompt, "--model", model],
            capture_output=True, text=True, timeout=120)
        return (r.stdout or r.stderr or "").strip() or "(không có phản hồi từ model)"
    except Exception as exc:
        return f"(lỗi gọi model: {exc})"

def _draft_key(sid):
    return f"mothersday_draft::{sid}"

def _save_draft(sid, uref, draft):
    api("POST", "/v1/self/facts", {"user_ref": uref or sid, "fact": json.dumps({
        "key": _draft_key(sid), "status": "awaiting_confirm", "minutes": draft})})

def _pending_draft(sid, uref):
    facts = api("GET", f"/v1/self/facts?user_ref={urllib.parse.quote(uref or sid)}").get("facts", [])
    for f in facts:
        try:
            data = json.loads(f.get("fact", "{}"))
        except json.JSONDecodeError:
            continue
        if data.get("key") == _draft_key(sid) and data.get("status") == "awaiting_confirm":
            return data
    return None

def draft_minutes(transcript, ctx):
    """Soạn biên bản nháp (key_points + decisions) từ transcript cuộc họp."""
    prompt = ("Tóm tắt transcript cuộc họp dự án Mother's Day thành biên bản gồm "
               "'Điểm chính' và 'Quyết định', ngắn gọn, chỉ dựa trên nội dung transcript:\n\n"
               + transcript)
    return answer(prompt, ctx)

def handle(job):
    payload = job.get("payload") or {}
    q = payload.get("text", "")
    sid = job.get("session_id") or f"job-{job['id']}"
    uref = payload.get("sender_open_id") or payload.get("user_ref") or ""
    ctx = api("GET", f"/v1/self/context?session_id={sid}&user_ref={uref}"
                     f"&q={urllib.parse.quote(q[:200])}")

    pending = _pending_draft(sid, uref)
    if payload.get("kind") == "transcript":
        # B. Được add vào họp → soạn nháp, xin chủ trì xác nhận, CHƯA tạo task.
        draft = draft_minutes(payload.get("transcript", q), ctx)
        _save_draft(sid, uref, draft)
        reply = f"Biên bản nháp:\n{draft}\n\nChủ trì xác nhận (reply 'confirm') để tạo task."
    elif pending and any(w in q.lower() for w in CONFIRM_WORDS):
        # Đã confirm → lưu biên bản vào brain riêng + đề nghị tạo task qua skill Lark Task
        # (endpoint /v1/self/brain/* ghi brain riêng của agent — xem docs/TESTCASES.md#BR.5).
        if not DRY_RUN:
            api("POST", "/v1/self/brain/items", {"title": f"Biên bản Mother's Day ({sid})",
                                                   "content": pending["minutes"], "status": "approved"})
        api("POST", "/v1/self/facts", {"user_ref": uref or sid, "fact": json.dumps({
            "key": _draft_key(sid), "status": "confirmed", "minutes": pending["minutes"]})})
        reply = "Đã ghi nhận biên bản và tạo task tương ứng (qua skill lark-task)."
    elif pending:
        # Chưa confirm mà hỏi tiếp → nhắc chờ, KHÔNG tạo task.
        reply = "Biên bản đang chờ chủ trì xác nhận, chưa tạo task."
    else:
        # A. Hỏi — đáp dữ liệu chung, dựa trên tri thức đã duyệt (ctx["knowledge"]).
        reply = answer(build_prompt(ctx, q), ctx)

    # Ghi lại lượt hội thoại để lượt sau có ngữ cảnh
    api("POST", "/v1/self/session/turn",
        {"session_id": sid, "role": "user", "text": q, "user_ref": uref,
         "channel": job.get("channel")})
    r = api("POST", "/v1/self/session/turn",
            {"session_id": sid, "role": "assistant", "text": reply})
    # Khi platform báo cần nén: tự tóm tắt các lượt bị cắt rồi gửi lên
    if r.get("needs_summary"):
        old = " ".join(f"{t['role']}: {t['text']}" for t in r.get("dropped_turns", []))
        summary = (ctx.get("rolling_summary", "") + " " + old)[-2000:]   # <<< nên nén bằng model
        api("POST", "/v1/self/session/summary", {"session_id": sid, "summary": summary})
    return reply

def main():
    print("consumer chạy — chờ job...")
    while True:
        try:
            jobs = api("GET", "/v1/self/jobs?wait=25&max=1")
        except urllib.error.HTTPError as e:
            time.sleep(30 if e.code == 403 else 5); continue
        except Exception:
            time.sleep(5); continue
        for job in jobs or []:
            jid = job["id"]
            try:
                reply = handle(job)
                # MỘT lời gọi cho MỌI kênh — platform tự gửi đúng Lark/Telegram/web/A2A
                api("POST", f"/v1/self/jobs/{jid}/reply", {"text": reply})
                api("POST", f"/v1/self/jobs/{jid}/complete", {"result": {"ok": True}})
                print(f"✓ job#{jid}")
            except Exception as exc:
                print(f"✗ job#{jid}: {exc}")
                try: api("POST", f"/v1/self/jobs/{jid}/fail", {"error": str(exc)[:400]})
                except Exception: pass

if __name__ == "__main__":
    main()
