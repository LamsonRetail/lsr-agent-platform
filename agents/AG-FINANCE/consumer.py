"""AG-FINANCE — entrypoint. Poll job từ platform, phân loại, giao cho module, trả lời.

File này chỉ ĐIỀU PHỐI. Logic nghiệp vụ nằm trong data_hub/ (Hương) và meeting/ (Thái).
Thêm code nghiệp vụ vào đây là sai chỗ và sẽ làm hai người sửa chồng file nhau.

Trạng thái Phase 1: phân quyền, ranh giới phạm vi và tra cứu số liệu đã chạy thật. Biên bản
họp trả lời rõ là chưa triển khai, thay vì trả lời sai.

Chạy:   LSR_AGENT_TOKEN=... python3 consumer.py
Docker: docker compose up
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from data_hub import ask, runtime
from data_hub.sources.base import SourceError
from shared.auth import DENY_MESSAGE, is_squad_member_from_payload

PLATFORM = os.environ.get("LSR_PLATFORM_URL", "https://platform.34-126-154-135.sslip.io").rstrip("/")
TOKEN = os.environ.get("LSR_AGENT_TOKEN", "")
AGENT_ID = os.environ.get("LSR_AGENT_ID", "AG-FINANCE")
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"

INTENT_SMALLTALK = "smalltalk"
INTENT_OUT_OF_SCOPE = "out_of_scope"
INTENT_MEETING = "meeting"
INTENT_FINANCIAL = "financial"

SMALLTALK = ("chào", "chao", "hello", "hi ", "làm được gì", "lam duoc gi", "giúp gì", "giup gi")
OUT_OF_SCOPE = (
    "hạch toán", "hach toan", "bút toán", "but toan", "ghi vào misa", "ghi vao misa",
    "duyệt chi", "duyet chi", "phê duyệt", "phe duyet", "báo cáo thuế", "bao cao thue",
    "quyết toán thuế", "quyet toan thue",
)
MEETING = ("biên bản", "bien ban", "cuộc họp", "cuoc hop", "transcript", "chốt", "chot")


def api(method: str, path: str, payload=None, timeout: int = 40):
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


def classify(question: str, payload: dict) -> str:
    """Phân loại ý định.

    Mặc định là INTENT_FINANCIAL, không phải smalltalk. Phân loại sai theo hướng "coi là
    câu hỏi số liệu" thì cùng lắm là từ chối oan; sai theo hướng ngược lại thì lọt dữ liệu
    ra người ngoài squad.

    Phase 1 sẽ thay bằng model. Tầng keyword giữ lại làm lớp chặn thứ hai.
    """
    low = f" {question.lower().strip()} "
    if payload.get("message_type") in ("audio", "media", "file"):
        return INTENT_MEETING
    if any(k in low for k in OUT_OF_SCOPE):
        return INTENT_OUT_OF_SCOPE
    if any(k in low for k in MEETING):
        return INTENT_MEETING
    if any(k in low for k in SMALLTALK):
        return INTENT_SMALLTALK
    return INTENT_FINANCIAL


def answer(question: str, ctx: dict, payload: dict) -> str:
    intent = classify(question, payload)

    if intent == INTENT_SMALLTALK:
        return (
            "Tôi là trợ lý Tài chính - Kế toán. Tôi tra công nợ, doanh thu, chi phí, lãi lỗ, "
            "dòng tiền cho squad Finance-Accounting, và dựng biên bản họp. "
            "Số liệu chỉ cung cấp cho thành viên squad."
        )

    if intent == INTENT_OUT_OF_SCOPE:
        return (
            "Việc này ngoài phạm vi của tôi. Tôi chỉ đọc số liệu, không hạch toán vào MISA, "
            "không phê duyệt chi và không lập báo cáo thuế. Anh/chị làm trực tiếp trên MISA "
            "hoặc theo quy trình duyệt của công ty."
        )

    # Từ đây trở xuống đều cần quyền squad.
    if not is_squad_member_from_payload(payload):
        return DENY_MESSAGE

    if intent == INTENT_MEETING:
        return "Luồng biên bản họp đang được xây (Phase 3). Hiện tôi chưa dựng được biên bản."

    try:
        return ask.answer_question(question, runtime.hub()).text
    except SourceError as exc:
        # Chưa nối được nguồn thật. Nói thẳng, KHÔNG rơi về dữ liệu giả.
        return f"Tôi chưa truy cập được nguồn số liệu nên chưa trả lời được ({exc})."


def handle(job: dict) -> str:
    payload = job.get("payload") or {}
    question = payload.get("text", "")
    sid = job.get("session_id") or f"job-{job['id']}"
    uref = payload.get("sender_open_id") or payload.get("user_ref") or ""

    ctx = api(
        "GET",
        f"/v1/self/context?session_id={urllib.parse.quote(sid)}"
        f"&user_ref={urllib.parse.quote(uref)}&q={urllib.parse.quote(question[:200])}",
    )
    reply = answer(question, ctx, payload)

    channel = (job.get("reply_to") or {}).get("channel")
    if DRY_RUN and channel in ("lark", "telegram"):
        print(f"[DRY_RUN] không gửi ra {channel}: {reply[:80]}")
    else:
        api("POST", f"/v1/self/jobs/{job['id']}/reply", {"text": reply})

    api("POST", "/v1/self/session/turn", {
        "session_id": sid, "role": "user", "text": question,
        "user_ref": uref, "channel": job.get("channel"),
    })
    r = api("POST", "/v1/self/session/turn", {
        "session_id": sid, "role": "assistant", "text": reply,
    })
    if r.get("needs_summary"):
        dropped = " ".join(f"{t['role']}: {t['text']}" for t in r.get("dropped_turns", []))
        api("POST", "/v1/self/session/summary", {
            "session_id": sid,
            "summary": ((ctx.get("rolling_summary") or "") + " " + dropped)[-2000:],
        })
    return reply


def main() -> None:
    if not TOKEN:
        print("⚠️  thiếu LSR_AGENT_TOKEN — xin ở Console hoặc chạy scripts/lsr_adopt.py")
    print(
        f"AG-FINANCE chạy — agent={AGENT_ID} DRY_RUN={DRY_RUN} "
        f"FIN_FAKE_DATA={runtime.fake_mode()} → {PLATFORM}"
    )
    while True:
        try:
            jobs = api("GET", "/v1/self/jobs?wait=25&max=1")
        except urllib.error.HTTPError as e:
            print(f"poll {e.code}")
            time.sleep(30 if e.code == 403 else 5)
            continue
        except Exception as exc:
            print(f"poll lỗi: {exc}")
            time.sleep(5)
            continue
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
