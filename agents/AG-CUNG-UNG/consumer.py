"""Trợ lý Cung Ứng — Agent squad SQ-CUNGUNG.

Khung chung copy từ agent mẫu của platform (`agents/AG-MINH-ANH/consumer.py`):
nhận job từ MỌI kênh (Lark · web chat · agent khác), dựng ngữ cảnh từ platform,
trả lời qua một API duy nhất.

Điểm cần nhớ (giống mọi agent trên platform):
  • KHÔNG cần biết tin đến từ kênh nào — `reply()` để platform tự gửi đúng chỗ.
  • KHÔNG giữ lịch sử hội thoại trong bộ nhớ — platform giữ (đổi máy/restart vẫn liền mạch).
  • KHÔNG cầm secret của Lark — gọi qua connector dùng chung.
  • Chỉ cần sửa hàm `answer()`.

Chạy:  LSR_AGENT_TOKEN=... python3 consumer.py
Docker: docker compose up   (xem docker-compose.yml cùng thư mục)
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

PLATFORM = os.environ.get("LSR_PLATFORM_URL", "https://platform.34-126-154-135.sslip.io").rstrip("/")
TOKEN = os.environ.get("LSR_AGENT_TOKEN", "")
AGENT_ID = os.environ.get("LSR_AGENT_ID", "AG-CUNG-UNG")
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"

RECORDING_TYPES = {"audio", "media", "file"}
CONFIRM_WORDS = {"chốt", "chot", "confirm", "duyệt", "duyet"}


def api(method: str, path: str, payload=None, timeout: int = 40):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(PLATFORM + path, data=data, method=method, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read().decode()
        return json.loads(b) if b else {}


# ----------------------------- phần cần sửa cho agent của bạn -----------------------------

def answer(q: str, ctx: dict, payload: dict) -> str:
    """Sinh câu trả lời. ctx đã có: instruction, tóm tắt, N lượt gần nhất, fact, tri thức.

    Bản demo dùng luật đơn giản để chạy được ngay & test được. Agent thật thay bằng
    lời gọi model (Claude Agent SDK), truyền `build_prompt(ctx, q)` vào.
    """
    low = q.lower().strip()
    mtype = payload.get("message_type", "text")

    if mtype in RECORDING_TYPES:
        return ("Đã nhận recording. Tôi sẽ dựng **biên bản** rồi gửi lại để anh/chị xác nhận. "
                "Trả lời `chốt` khi biên bản đúng.")
    if any(w in low for w in CONFIRM_WORDS):
        return "Đã chốt biên bản, tạo task cho các đầu việc và lưu vào kho tri thức Cung Ứng. ✅"
    if any(w in low for w in ("chào", "chao", "hello", "hi")):
        return ("Xin chào! Tôi là Trợ lý Cung Ứng — đầu mối tri thức chung của team và "
                "trợ lý biên bản họp. Hỏi tôi về nhà cung cấp/đơn hàng/hợp đồng đã được duyệt, "
                "hoặc gửi recording cuộc họp để tôi dựng biên bản.")
    if "làm được gì" in low or "lam duoc gi" in low or "giúp gì" in low:
        return ("Tôi làm 3 việc: (1) tra **tri thức Cung Ứng** đã duyệt (nhà cung cấp, đơn "
                "hàng, hợp đồng, tồn kho...), (2) dựng **biên bản họp** từ recording/nội dung "
                "trao đổi, (3) chốt biên bản rồi tạo **task**.")

    # Có tri thức liên quan → trả lời kèm trích dẫn nguồn (không bịa).
    hits = ctx.get("knowledge") or []
    if hits:
        h = hits[0]
        src = h.get("source_url") or "kho tri thức Cung Ứng"
        return f"{h.get('title')}: {(h.get('content') or '')[:400]}\n\n(nguồn: {src})"

    return ("Tôi chưa có thông tin đã được duyệt cho câu này nên không đoán. "
            "Anh/chị gửi tài liệu/nội dung liên quan hoặc nhờ người phụ trách xác nhận nhé.")


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


# ----------------------------- khung chung (thường không phải sửa) -----------------------------

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
        # MỘT lời gọi cho mọi kênh — platform tự gửi đúng Lark/web/A2A.
        api("POST", f"/v1/self/jobs/{job['id']}/reply", {"text": reply_text})

    # Ghi lượt để lượt sau còn ngữ cảnh
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
    print(f"Trợ lý Cung Ứng chạy — agent={AGENT_ID} DRY_RUN={DRY_RUN} → {PLATFORM}")
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
