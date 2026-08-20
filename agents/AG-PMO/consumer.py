"""Consumer mẫu — poll job từ platform, dựng ngữ cảnh, trả lời, ghi nhớ.

Chạy: LSR_AGENT_TOKEN=... python3 consumer.py   (token nhận khi enroll)
Job đến từ MỌI kênh (Lark/web chat/cron) qua cùng một queue — sửa answer() là đủ.

Ngữ cảnh do PLATFORM giữ (không nằm ở model): mỗi lượt gọi /v1/self/context để lấy
instruction (version đang publish) + tóm tắt + N lượt gần nhất + fact người dùng +
tri thức liên quan (có nguồn). Nhờ vậy đổi model/credential hay restart đều không mất mạch.
"""
import json, os, time, urllib.parse, urllib.request, urllib.error

PLATFORM = os.environ.get("LSR_PLATFORM_URL", "https://platform.34-126-154-135.sslip.io").rstrip("/")
TOKEN = os.environ["LSR_AGENT_TOKEN"]

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

_STORE = None


def _store():
    """Nạp danh mục dự án một lần, giữ lại cho các job sau (tránh gọi Lark mỗi câu hỏi)."""
    global _STORE
    if _STORE is None:
        from pmo_data import tu_lark
        _STORE = tu_lark()
    return _STORE


def answer(prompt, ctx, *, question="", email=None):
    """Trả lời câu hỏi dự án.

    Đường đi CỐ Ý không qua model cho phần lớn câu: ``pmo_answer.tra_loi()`` đã cho câu
    trả lời tất định từ dữ liệu thật (có nêu ngày báo cáo, có chặn xin-quyết-định và chặn
    field tài chính mật). Gọi model ở đây chỉ thêm rủi ro diễn giải lệch số.

    Model chỉ dùng khi ``can_model=True`` — hiện chưa có nhánh nào cần, sẽ dùng ở giai đoạn
    biên bản họp (tóm tắt transcript) vì việc đó thực sự cần model.
    """
    from pmo_answer import tra_loi
    kq = tra_loi(question or prompt, email=email, store=_store())
    if not kq.get("can_model"):
        return kq["text"]
    return kq["text"]  # TODO(GĐ1-biên bản họp): gọi Claude Agent SDK để tóm tắt transcript

def handle(job):
    payload = job.get("payload") or {}
    q = payload.get("text", "")
    sid = job.get("session_id") or f"job-{job['id']}"
    uref = payload.get("sender_open_id") or payload.get("user_ref") or ""

    ctx = api("GET", f"/v1/self/context?session_id={sid}&user_ref={uref}"
                     f"&q={urllib.parse.quote(q[:200])}")
    # email dùng để xét quyền xem field tài chính mật (PMO_CONFIDENTIAL_VIEWERS)
    email = payload.get("sender_email") or ctx.get("user_email") or ""
    reply = answer(build_prompt(ctx, q), ctx, question=q, email=email)

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
