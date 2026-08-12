#!/usr/bin/env python3
"""Tiến trình chạy của MAI — nhận job từ platform, trả lời, ghi lượt hội thoại.

Job đến từ MỌI kênh (Telegram / Lark / web chat) qua cùng một queue của platform,
nên chỉ cần chạy file này là MAI trả lời được ở cả 3 nơi.

Xác thực model = **subscription của OWNER** (`claude setup-token`), gọi qua Claude Code CLI.
KHÔNG dùng khoá LLM, KHÔNG auth chung platform — đúng chuẩn agent của platform.

Chạy:
    LSR_AGENT_TOKEN=lsr_tel_... python3 consumer.py

Thử offline (không cần token, không cần platform):
    python3 consumer.py --ask "Ngành Trang sức đang đánh JTBD nào?"
    python3 consumer.py --ask "..." --dump-prompt      # xem đúng cái gửi cho model
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "vn"))
import vietnam_tools as vn                                    # noqa: E402

PLATFORM = os.environ.get(
    "LSR_PLATFORM_URL", "https://platform.34-126-154-135.sslip.io").rstrip("/")
TOKEN = os.environ.get("LSR_AGENT_TOKEN", "")
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
MODEL = os.environ.get("LSR_MODEL", "claude-sonnet-5")
KB_HITS = int(os.environ.get("MAI_KB_HITS", "3"))

# Config luôn nạp sẵn mỗi lượt (nhỏ, quyết định giọng + quyền + bối cảnh).
BASE_CONFIGS = ("persona", "vn_context", "role_permissions")


def api(method, path, payload=None, timeout=40):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(PLATFORM + path, data=data, method=method, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + TOKEN})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read().decode()
        return json.loads(b) if b else {}


def _read(*parts):
    path = os.path.join(HERE, *parts)
    if not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _keywords(question):
    """Từ khoá tra kho: bỏ từ nối, giữ từ có nghĩa. Tra nhiều lần còn hơn tra trượt."""
    stop = {"là", "gì", "của", "cho", "anh", "chị", "em", "cái", "này", "nào", "có",
            "không", "thì", "và", "với", "bao", "nhiêu", "đang", "được", "một", "các"}
    words = [w.strip(".,?!:;\"'()").lower() for w in (question or "").split()]
    return [w for w in words if len(w) > 2 and w not in stop][:6]


def gather_knowledge(question):
    """Tra kho 2 bước (index → read) đúng luật trong system prompt."""
    idx = vn.vn_kb_index()
    if idx.get("status") != "ok":
        return [], idx.get("note", "Kho tri thức đang rỗng.")
    hits, seen = [], set()
    for kw in _keywords(question) or [""]:
        r = vn.vn_kb_index(kw)
        for item in (r.get("items") or []):
            if item["file"] in seen:
                continue
            seen.add(item["file"])
            hits.append(item)
            if len(hits) >= KB_HITS:
                break
        if len(hits) >= KB_HITS:
            break
    if not hits:                       # không khớp từ khoá → đưa mục lục để model tự chọn
        return [], "Không mục nào khớp câu hỏi. Mục lục hiện có: " + ", ".join(
            i["file"] for i in idx["items"][:20])
    docs = [vn.vn_kb_read(file=h["file"]) for h in hits]
    return [d for d in docs if d.get("status") == "ok"], ""


def build_prompt(question, asker=""):
    parts = [_read("system_prompt.md"),
             "## Skills đang hiệu lực\n" + _read("skills", "README.md")]

    cfgs = []
    for key in BASE_CONFIGS:
        c = vn.vn_config_get(key)
        if c.get("status") == "ok":
            flag = "  ⚠ OWNER CHƯA ĐIỀN — coi như CHƯA CÓ, không được đoán số." if c["unfilled"] else ""
            cfgs.append("### {}{}\n```json\n{}\n```".format(
                key, flag, json.dumps(c["value"], ensure_ascii=False, indent=1)))
    if cfgs:
        parts.append("## Config hiện tại (nguồn chuẩn — ưu tiên hơn trí nhớ)\n" + "\n".join(cfgs))

    docs, note = gather_knowledge(question)
    if docs:
        parts.append("## Tri thức lấy từ kho (BẮT BUỘC trích nguồn theo `cite_as`)\n" + "\n\n".join(
            "### {} \n<!-- cite_as: {} -->\n{}".format(d["file"], d["cite_as"], d["content"])
            for d in docs))
    else:
        parts.append("## Tri thức lấy từ kho\nKHÔNG có tài liệu nào khớp. " + note +
                     "\n→ Trả lời thẳng là **chưa có trong kho**. TUYỆT ĐỐI không suy đoán.")

    if asker:
        parts.append("## Người hỏi\n" + asker +
                     "\n→ Đối chiếu role_permissions. Ngoài quyền thì nói rõ "
                     "'phần này em không được chia sẻ'.")

    parts.append("## Câu hỏi\n" + question)
    parts.append("Trả lời bằng tiếng Việt, xưng 'em' gọi 'anh/chị', ngắn gọn. "
                 "Mọi số phải kèm nguồn + thời điểm. Không có dữ liệu thì nói chưa có.")
    return "\n\n---\n\n".join(p for p in parts if p.strip())


def ask_model(prompt):
    """Gọi Claude Code CLI ở chế độ print — dùng subscription đã setup-token của owner."""
    try:
        r = subprocess.run([CLAUDE_BIN, "-p", prompt, "--model", MODEL],
                           capture_output=True, text=True, timeout=180)
    except FileNotFoundError:
        return ("", "chưa có Claude Code CLI ('{}'). Cài Claude Code rồi chạy "
                    "`claude setup-token` bằng tài khoản OWNER.".format(CLAUDE_BIN))
    except subprocess.TimeoutExpired:
        return "", "model quá thời gian (180s)"
    if r.returncode != 0:
        return "", "claude lỗi ({}): {}".format(r.returncode, (r.stderr or "")[:300])
    return r.stdout.strip(), ""


def answer(question, asker=""):
    text, err = ask_model(build_prompt(question, asker))
    if err:
        return ("Em chưa trả lời được — {}. Nhờ anh/chị báo người vận hành agent."
                .format(err))
    return text or "Em chưa có câu trả lời cho câu này."


def handle(job):
    payload = job.get("payload") or {}
    q = payload.get("text", "")
    sid = job.get("session_id") or "job-{}".format(job["id"])
    uref = payload.get("sender_open_id") or payload.get("user_ref") or ""
    asker = payload.get("user_name") or uref

    ctx = {}
    try:                                   # ngữ cảnh do platform giữ (tóm tắt + lượt gần nhất)
        ctx = api("GET", "/v1/self/context?session_id={}&user_ref={}&q={}".format(
            urllib.parse.quote(sid), urllib.parse.quote(uref), urllib.parse.quote(q[:200])))
    except Exception as exc:
        print("… không lấy được context: {}".format(exc))

    question = q
    if ctx.get("rolling_summary") or ctx.get("recent_turns"):
        truoc = "\n".join("{}: {}".format(t["role"], t["text"])
                          for t in (ctx.get("recent_turns") or [])[-6:])
        question = "Hội thoại trước:\n{}\n{}\n\nCâu hỏi mới: {}".format(
            ctx.get("rolling_summary", ""), truoc, q)

    reply = answer(question, asker)

    api("POST", "/v1/self/jobs/{}/reply".format(job["id"]), {"text": reply})
    api("POST", "/v1/self/session/turn", {"session_id": sid, "role": "user", "text": q,
                                          "user_ref": uref, "channel": job.get("channel")})
    r = api("POST", "/v1/self/session/turn", {"session_id": sid, "role": "assistant",
                                              "text": reply})
    if r.get("needs_summary"):
        old = " ".join("{}: {}".format(t["role"], t["text"]) for t in r.get("dropped_turns", []))
        api("POST", "/v1/self/session/summary",
            {"session_id": sid,
             "summary": ((ctx.get("rolling_summary") or "") + " " + old)[-2000:]})
    api("POST", "/v1/self/jobs/{}/complete".format(job["id"]), {"result": {"ok": True}})
    return reply


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "--ask":
        q = argv[1] if len(argv) > 1 else ""
        if "--dump-prompt" in argv:
            print(build_prompt(q))
            return 0
        print(answer(q))
        return 0

    if not TOKEN:
        print("Thiếu LSR_AGENT_TOKEN — xin ở bước enroll (xem README.md).\n"
              "Thử offline không cần token:  python3 consumer.py --ask \"câu hỏi\"")
        return 1

    print("MAI chạy — chờ job từ {} …".format(PLATFORM))
    while True:
        try:
            jobs = api("GET", "/v1/self/jobs?wait=25&max=1")
        except urllib.error.HTTPError as exc:
            print("lấy job lỗi HTTP {}".format(exc.code))
            time.sleep(30 if exc.code == 403 else 5)
            continue
        except Exception as exc:
            print("lấy job lỗi: {}".format(exc))
            time.sleep(5)
            continue
        for job in jobs or []:
            try:
                reply = handle(job)
                print("✓ job#{} [{}] → {}".format(job["id"], job.get("channel"), reply[:70]))
            except Exception as exc:
                print("✗ job#{}: {}".format(job.get("id"), exc))
                try:
                    api("POST", "/v1/self/jobs/{}/fail".format(job["id"]),
                        {"error": str(exc)[:400]})
                except Exception:
                    pass


if __name__ == "__main__":
    sys.exit(main())
