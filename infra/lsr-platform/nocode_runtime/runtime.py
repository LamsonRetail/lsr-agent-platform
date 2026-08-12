"""Runtime cho agent NO-CODE (P9).

Một service phục vụ NHIỀU agent: agent nào có `runtime='nocode'` thì platform tự chạy,
người tạo không phải viết dòng code nào.

Vòng đời một lượt:
  1. lấy job của mọi agent no-code   → GET /v1/runtime/jobs
  2. lấy instruction đang publish     → GET /v1/runtime/agent/{id}/config
  3. dựng ngữ cảnh (tóm tắt + lượt gần nhất + fact + tri thức) → /v1/self/context (P4)
  4. mượn quyền gọi model              → ladder P2 (qua litellm hoặc subscription)
  5. trả lời                           → /v1/self/jobs/{id}/reply (tự đúng kênh, P-A)
  6. ghi lượt hội thoại                → /v1/self/session/turn

Không giữ state trong bộ nhớ: mọi thứ nằm ở platform nên restart/scale đều an toàn.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request

PLATFORM = os.environ.get("PLATFORM_URL", "http://platform_api:8090").rstrip("/")
RUNTIME_TOKEN = os.environ.get("GATEWAY_INGEST_TOKEN") or os.environ.get("PLATFORM_ADMIN_TOKEN", "")
POLL_SECS = int(os.environ.get("NOCODE_POLL_SECS", "3"))
LLM_BASE = os.environ.get("LLM_BASE_URL", "")          # vd http://litellm:4000
LLM_KEY = os.environ.get("LLM_API_KEY", "")
DEFAULT_MODEL = os.environ.get("NOCODE_DEFAULT_MODEL", "claude-sonnet-4-5")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("nocode")


def api(method: str, path: str, payload=None, token: str = "", timeout: int = 40):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(PLATFORM + path, data=data, method=method, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {token or RUNTIME_TOKEN}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read().decode()
        return json.loads(b) if b else {}


_TOKENS: dict = {}          # agent_id -> (token, hết hạn)


def _agent_token(agent_id: str) -> str:
    tok, exp = _TOKENS.get(agent_id, ("", 0))
    if tok and time.time() < exp:
        return tok
    d = api("GET", f"/v1/agents/{agent_id}/runtime-token")
    _TOKENS[agent_id] = (d.get("token", ""), time.time() + 25 * 60)
    return _TOKENS[agent_id][0]


def build_prompt(cfg: dict, ctx: dict, question: str) -> str:
    """Ghép prompt stateless: instruction + tóm tắt + lượt gần nhất + fact + tri thức."""
    parts = [cfg.get("instruction_block") or "Bạn là trợ lý nội bộ của LamsonRetail."]
    parts.append("Nguyên tắc: chỉ trả lời dựa trên tri thức được cung cấp; "
                 "không chắc thì nói chưa có thông tin, KHÔNG bịa. "
                 "Khi dùng tri thức, ghi rõ nguồn.")
    if ctx.get("rolling_summary"):
        parts.append("Tóm tắt hội thoại trước:\n" + ctx["rolling_summary"])
    if ctx.get("user_facts"):
        parts.append("Đã biết về người dùng:\n- " + "\n- ".join(ctx["user_facts"]))
    if ctx.get("knowledge"):
        parts.append("Tri thức liên quan:\n" + "\n".join(
            f"- {h['title']}: {(h.get('content') or '')[:400]} "
            f"(nguồn: {h.get('source_url') or 'kho nội bộ'})" for h in ctx["knowledge"]))
    for t in ctx.get("recent_turns", []):
        parts.append(f"{t['role']}: {t['text']}")
    parts.append(f"user: {question}")
    return "\n\n".join(parts)


def call_model(prompt: str, model: str) -> str:
    """Gọi model qua LLM gateway. Chưa cấu hình gateway → trả lời dựa trên tri thức sẵn có."""
    if not (LLM_BASE and LLM_KEY):
        return ""
    body = {"model": model or DEFAULT_MODEL, "max_tokens": 800,
            "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(
        LLM_BASE.rstrip("/") + "/v1/messages", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-api-key": LLM_KEY,
                 "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode())
        return "".join(c.get("text", "") for c in d.get("content", []) if isinstance(c, dict)).strip()
    except Exception as exc:
        log.warning("gọi model lỗi: %s", exc)
        return ""


def fallback_answer(ctx: dict, question: str) -> str:
    """Khi chưa nối được model: vẫn trả lời được từ tri thức (có trích dẫn), không bịa."""
    hits = ctx.get("knowledge") or []
    if hits:
        h = hits[0]
        return (f"{h.get('title')}: {(h.get('content') or '')[:500]}\n\n"
                f"(nguồn: {h.get('source_url') or 'kho tri thức nội bộ'})")
    return ("Tôi chưa có thông tin đã được duyệt cho câu hỏi này nên không đoán. "
            "Bạn bổ sung tri thức vào Brain hoặc hỏi rõ hơn giúp tôi.")


def handle(job: dict) -> None:
    aid = job["agent_id"]
    jid = job["id"]
    payload = job.get("payload") or {}
    q = payload.get("text", "")
    sid = job.get("session_id") or f"job-{jid}"
    uref = payload.get("user_ref") or payload.get("sender_open_id") or ""

    cfg = api("GET", f"/v1/runtime/agent/{aid}/config")
    # Token ngắn hạn để hành động NHÂN DANH agent (nhóm /v1/self/*), cache theo agent.
    atok = _agent_token(aid)
    ctx = api("GET", f"/v1/self/context?session_id={urllib.parse.quote(sid)}"
                     f"&user_ref={urllib.parse.quote(uref)}&q={urllib.parse.quote(q[:200])}",
              token=atok)

    reply = call_model(build_prompt(cfg, ctx, q), cfg.get("model")) or fallback_answer(ctx, q)

    api("POST", f"/v1/self/jobs/{jid}/reply", {"text": reply}, token=atok)
    api("POST", "/v1/self/session/turn",
        {"session_id": sid, "role": "user", "text": q, "user_ref": uref,
         "channel": job.get("channel")}, token=atok)
    r = api("POST", "/v1/self/session/turn",
            {"session_id": sid, "role": "assistant", "text": reply}, token=atok)
    if r.get("needs_summary"):
        old = " ".join(f"{t['role']}: {t['text']}" for t in r.get("dropped_turns", []))
        api("POST", "/v1/self/session/summary",
            {"session_id": sid, "summary": ((ctx.get("rolling_summary") or "") + " " + old)[-2000:]},
            token=atok)
    api("POST", f"/v1/self/jobs/{jid}/complete", {"result": {"ok": True}}, token=atok)
    log.info("✓ %s job#%s [%s] → %s", aid, jid, job.get("channel"), reply[:60])


def main() -> None:
    log.info("Runtime no-code khởi động → %s (model gateway: %s)",
             PLATFORM, "có" if (LLM_BASE and LLM_KEY) else "CHƯA nối — dùng tri thức sẵn có")
    while True:
        try:
            jobs = api("GET", "/v1/runtime/jobs?max=3")
        except Exception as exc:
            log.warning("lấy job lỗi: %s", exc)
            time.sleep(5)
            continue
        if not jobs:
            time.sleep(POLL_SECS)
            continue
        for job in jobs:
            try:
                handle(job)
            except Exception as exc:
                log.exception("job#%s lỗi", job.get("id"))
                try:
                    api("POST", f"/v1/self/jobs/{job['id']}/fail", {"error": str(exc)[:400]},
                        token=_agent_token(job["agent_id"]))
                except Exception:
                    pass


if __name__ == "__main__":
    main()
