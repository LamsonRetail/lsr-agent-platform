"""Consumer mẫu — poll job từ platform, dựng ngữ cảnh, trả lời, ghi nhớ.

Chạy: LSR_AGENT_TOKEN=... python3 consumer.py   (token nhận khi enroll)
Job đến từ MỌI kênh (Lark/web chat/cron) qua cùng một queue — sửa answer() là đủ.

Ngữ cảnh do PLATFORM giữ (không nằm ở model): mỗi lượt gọi /v1/self/context để lấy
instruction (version đang publish) + tóm tắt + N lượt gần nhất + fact người dùng +
tri thức liên quan (có nguồn). Nhờ vậy đổi model/credential hay restart đều không mất mạch.
"""
import json, os, time, urllib.parse, urllib.request, urllib.error

PLATFORM = os.environ.get("LSR_PLATFORM_URL", "https://platform.34-126-154-135.sslip.io").rstrip("/")
# Hai tên, vì có hai đường chạy: docker-compose/chạy tay truyền LSR_AGENT_TOKEN, còn runtime
# trên VM (POST /v1/self/deploy) tiêm token agent dưới tên LSR_TELEMETRY_API_KEY.
# Xem dòng `"LSR_TELEMETRY_API_KEY": tok` trong handler /v1/self/deploy của
# platform_api/app.py — agent_runner/entrypoint.sh:10 cũng đọc theo đúng thứ tự này.
TOKEN = os.environ.get("LSR_AGENT_TOKEN") or os.environ.get("LSR_TELEMETRY_API_KEY") or ""
if not TOKEN:
    raise SystemExit("thiếu token agent: đặt LSR_AGENT_TOKEN (chạy tay) "
                     "hoặc LSR_TELEMETRY_API_KEY (runner trên VM tự tiêm)")

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
    """<<< SỬA Ở ĐÂY: gọi model của bạn với `prompt` và trả câu trả lời >>>

    Gợi ý: dùng Claude Agent SDK / claude CLI. Model nên lấy từ ctx.get("model").
    """
    return f"(demo) đã nhận prompt {len(prompt)} ký tự — thay hàm answer() bằng lời gọi model."

def handle(job):
    payload = job.get("payload") or {}
    q = payload.get("text", "")
    sid = job.get("session_id") or f"job-{job['id']}"
    uref = payload.get("sender_open_id") or payload.get("user_ref") or ""

    ctx = api("GET", f"/v1/self/context?session_id={sid}&user_ref={uref}"
                     f"&q={urllib.parse.quote(q[:200])}")
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
