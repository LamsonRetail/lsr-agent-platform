"""Data Support — consumer: poll job từ platform, trả lời câu hỏi dữ liệu HOẶC dựng/
chốt biên bản họp. Dựa trên mẫu chuẩn của platform (`scripts/new-agent.sh`) — mọi
kênh (Lark / web chat / cron) vào CÙNG một hàng đợi, chỉ cần sửa các hàm `answer_*`.

Chạy: LSR_AGENT_TOKEN=... python3 consumer.py   (token nhận khi enroll/adopt)

Ngữ cảnh do PLATFORM giữ (không nằm ở model): mỗi lượt gọi /v1/self/context để lấy
instruction (version đang publish) + tóm tắt + N lượt gần nhất + fact người dùng +
tri thức liên quan (có nguồn, lấy từ Brain riêng của agent này). Nhờ vậy đổi model/
credential hay restart đều không mất mạch.

Giới hạn MVP: bản nháp biên bản đang chờ xác nhận được giữ trong RAM theo session_id
(_PENDING_MINUTES). Nếu cần bền qua restart, chuyển sang lưu bằng
`api("POST", "/v1/self/facts", ...)` hoặc một bảng riêng — TODO khi có nhu cầu thật.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

PLATFORM = os.environ.get("LSR_PLATFORM_URL", "https://platform.34-126-154-135.sslip.io").rstrip("/")
TOKEN = os.environ["LSR_AGENT_TOKEN"]
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"

CONFIRM_WORDS = ("chốt", "duyệt", "confirm", "ok chốt", "đồng ý")
ZOOM_MEET_WORDS = ("zoom", "google meet", "meet.google")
WRITE_ACTION_WORDS = ("xoá", "xóa", "sửa", "cập nhật", "update", "delete", "ghi vào")
DATA_SOURCE_WORDS = ("bigquery", "lark base", "bảng", "dữ liệu gốc")

# Bản nháp biên bản đang chờ xác nhận, theo session_id. MVP — xem giới hạn ở docstring.
_PENDING_MINUTES: dict[str, dict] = {}


def api(method, path, payload=None, timeout=40):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        PLATFORM + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"},
    )
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
        kb = "\n".join(
            f"- {h['title']}: {h['content'][:300]} (nguồn: {h.get('source_url') or 'nội bộ'})"
            for h in ctx["knowledge"]
        )
        parts.append("Tri thức liên quan (TRÍCH DẪN nguồn khi dùng):\n" + kb)
    for t in ctx.get("recent_turns", []):
        parts.append(f"{t['role']}: {t['text']}")
    parts.append(f"user: {question}")
    return "\n\n".join(parts)


def is_meeting_payload(payload):
    """Recording/file đính kèm → coi là nội dung cuộc họp cần dựng biên bản."""
    return bool(payload.get("attachment") or payload.get("audio_url") or payload.get("file_url"))


def transcribe(payload):
    """<<< SỬA Ở ĐÂY: gọi dịch vụ transcript (vd Whisper) cho recording Lark Meeting.

    MVP: nếu payload đã có `text`/`transcript` (vd forward transcript có sẵn từ Lark
    Minutes) thì dùng luôn, không cần STT riêng.
    """
    return payload.get("transcript") or payload.get("text", "")


def draft_minutes(transcript):
    """<<< SỬA Ở ĐÂY: gọi model (Claude Agent SDK, đăng nhập subscription của owner)
    để dựng biên bản có cấu trúc từ transcript. Model nên lấy từ ctx.get("model").

    Trả về dict: {attendees, agenda, decisions, action_items: [{title, owner}]}
    """
    return {
        "attendees": [],
        "agenda": [],
        "decisions": [],
        "action_items": [],
        "raw_transcript": transcript,
    }


def format_minutes_draft(minutes):
    lines = ["📝 **Biên bản nháp** — gõ \"chốt\" để xác nhận và tạo task:"]
    if minutes["attendees"]:
        lines.append("Người tham dự: " + ", ".join(minutes["attendees"]))
    if minutes["decisions"]:
        lines.append("Quyết định:\n- " + "\n- ".join(minutes["decisions"]))
    if minutes["action_items"]:
        lines.append(
            "Action item:\n"
            + "\n".join(f"- {a['title']} (phụ trách: {a.get('owner') or 'chưa rõ'})" for a in minutes["action_items"])
        )
    if not (minutes["attendees"] or minutes["decisions"] or minutes["action_items"]):
        lines.append("(chưa trích được nội dung cụ thể — kiểm tra lại transcript)")
    return "\n".join(lines)


def create_lark_task(action_item):
    """<<< SỬA Ở ĐÂY: gọi connector Lark task có sẵn của platform để tạo task thật.
    Khi DRY_RUN=true chỉ log, không gửi thật (đúng chuẩn platform).
    """
    if DRY_RUN:
        print(f"[DRY_RUN] sẽ tạo task Lark: {action_item}")
        return {"ok": True, "dry_run": True}
    # TODO: api("POST", "/v1/self/lark/task", {...}) khi connector task self-service sẵn sàng.
    return {"ok": True}


def save_minutes_to_brain(minutes, session_id):
    """Lưu biên bản đã chốt vào Brain RIÊNG của agent này (không lẫn sang shared)."""
    content = format_minutes_draft(minutes)
    try:
        api(
            "POST",
            "/v1/self/brain/items",
            {
                "title": f"Biên bản họp {session_id}",
                "content": content,
                "source_url": f"lark://meeting/{session_id}",
            },
        )
    except Exception as exc:  # không chặn luồng trả lời nếu ghi brain lỗi
        print(f"⚠ ghi brain lỗi (không chặn trả lời): {exc}")


def answer_data_question(prompt, question):
    """<<< SỬA Ở ĐÂY: gọi Claude Agent SDK (đăng nhập subscription) với `prompt`.

    `prompt` đã kèm tri thức liên quan (ctx["knowledge"], lấy từ ingest/bigquery_sync.py
    + ingest/lark_base_sync.py) — LUÔN trích dẫn nguồn, nếu tri thức trống thì trả lời
    thẳng "chưa có dữ liệu này", không bịa số liệu.
    """
    return f"(demo) đã nhận câu hỏi dữ liệu ({len(prompt)} ký tự ngữ cảnh) — thay answer_data_question() bằng lời gọi model."


def answer(payload, ctx, question, session_id):
    q_lower = question.lower()

    # Ngoài phạm vi — từ chối lịch sự, không lẫn vào luồng dữ liệu/họp.
    if any(w in q_lower for w in ZOOM_MEET_WORDS):
        return "Data Support hiện chỉ hỗ trợ họp qua Lark Meeting ở bản v1, chưa vào được Zoom/Google Meet."

    # Ngoài phạm vi — yêu cầu sửa/xoá dữ liệu gốc: agent chỉ đọc (xem USECASE.md).
    if any(w in q_lower for w in WRITE_ACTION_WORDS) and any(w in q_lower for w in DATA_SOURCE_WORDS):
        return "Data Support chỉ đọc dữ liệu để tổng hợp, không sửa/xoá dữ liệu gốc ở BigQuery/Lark Base."

    # C. Biên bản họp — nhận recording/transcript.
    if is_meeting_payload(payload):
        transcript = transcribe(payload)
        minutes = draft_minutes(transcript)
        _PENDING_MINUTES[session_id] = minutes
        return format_minutes_draft(minutes)

    # C. Biên bản họp — xác nhận bản nháp đang chờ.
    if any(w in q_lower for w in CONFIRM_WORDS) and session_id in _PENDING_MINUTES:
        minutes = _PENDING_MINUTES.pop(session_id)
        results = [create_lark_task(a) for a in minutes["action_items"]]
        save_minutes_to_brain(minutes, session_id)
        n_ok = sum(1 for r in results if r.get("ok"))
        return f"✅ Đã chốt biên bản, tạo {n_ok}/{len(minutes['action_items'])} task, lưu vào kho tri thức chung."

    # A. Hỏi dữ liệu chung — dùng tri thức đã đồng bộ (Brain riêng của agent).
    prompt = build_prompt(ctx, question)
    if not ctx.get("knowledge"):
        return "Chưa có dữ liệu này trong kho tri thức đã đồng bộ — báo Data lead bổ sung nguồn nếu cần."
    return answer_data_question(prompt, question)


def handle(job):
    payload = job.get("payload") or {}
    q = payload.get("text", "")
    sid = job.get("session_id") or f"job-{job['id']}"
    uref = payload.get("sender_open_id") or payload.get("user_ref") or ""

    ctx = api(
        "GET",
        f"/v1/self/context?session_id={sid}&user_ref={uref}&q={urllib.parse.quote(q[:200])}",
    )
    reply = answer(payload, ctx, q, sid)

    # Ghi lại lượt hội thoại để lượt sau có ngữ cảnh
    api(
        "POST",
        "/v1/self/session/turn",
        {"session_id": sid, "role": "user", "text": q, "user_ref": uref, "channel": job.get("channel")},
    )
    r = api("POST", "/v1/self/session/turn", {"session_id": sid, "role": "assistant", "text": reply})
    # Khi platform báo cần nén: tự tóm tắt các lượt bị cắt rồi gửi lên
    if r.get("needs_summary"):
        old = " ".join(f"{t['role']}: {t['text']}" for t in r.get("dropped_turns", []))
        summary = (ctx.get("rolling_summary", "") + " " + old)[-2000:]  # <<< nên nén bằng model
        api("POST", "/v1/self/session/summary", {"session_id": sid, "summary": summary})
    return reply


def main():
    print(f"Data Support consumer chạy (DRY_RUN={DRY_RUN}) — chờ job...")
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
                # MỘT lời gọi cho MỌI kênh — platform tự gửi đúng Lark/Telegram/web/A2A
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
