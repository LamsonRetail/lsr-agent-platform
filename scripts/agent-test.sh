#!/usr/bin/env bash
# Chạy bộ test tự động của agent: agents/<id>/tests.jsonl (mỗi dòng {"q","expect":[...]}).
# Mỗi case gửi qua Chat API, đợi trả lời, kiểm từng từ khoá kỳ vọng (không phân biệt hoa/thường).
# Dùng: bash scripts/agent-test.sh AG-ID [file.jsonl]      (cần LSR_AGENT_TOKEN)
set -u

AID="${1:?cần agent id}"
FILE="${2:-agents/$AID/tests.jsonl}"
PLATFORM="${LSR_PLATFORM_URL:-https://platform.34-126-154-135.sslip.io}"
TOKEN="${LSR_AGENT_TOKEN:-}"
for f in ".env.lsr" "agents/$AID/.env.lsr"; do
  [ -z "$TOKEN" ] && [ -f "$f" ] && TOKEN=$(grep '^LSR_TELEMETRY_API_KEY=\|^LSR_AGENT_TOKEN=' "$f" | head -1 | cut -d= -f2-)
done
[ -z "$TOKEN" ] && { echo "thiếu LSR_AGENT_TOKEN (hoặc .env.lsr)"; exit 1; }
[ -f "$FILE" ] || { echo "không thấy $FILE — khai test case trước (scripts/new-agent.sh tạo mẫu)"; exit 1; }

export PLATFORM TOKEN AID
python3 - "$FILE" <<'PY'
import json, os, sys, time, urllib.request

PLATFORM, TOKEN, AID = os.environ["PLATFORM"], os.environ["TOKEN"], os.environ["AID"]
TIMEOUT = int(os.environ.get("LSR_CHAT_TIMEOUT", "60"))

def api(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(PLATFORM + path, data=data, method=method, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode() or "{}")

def ask(q):
    r = api("POST", f"/v1/chat/{AID}/messages", {"text": q})
    sid = r["session_id"]
    texts, deadline = [], time.time() + TIMEOUT
    # đọc SSE stream tới khi 'done' hoặc hết giờ
    req = urllib.request.Request(
        f"{PLATFORM}/v1/chat/{AID}/stream?session_id={sid}&token={TOKEN}")
    with urllib.request.urlopen(req, timeout=TIMEOUT + 5) as s:
        kind = ""
        while time.time() < deadline:
            line = s.readline().decode().rstrip("\n")
            if line.startswith("event: "):
                kind = line[7:]
            elif line.startswith("data: "):
                d = json.loads(line[6:] or "{}")
                if kind == "message":
                    texts.append(d.get("text", ""))
                elif kind == "done":
                    return " ".join(texts)
                elif kind in ("error", "timeout"):
                    break
    return " ".join(texts)

cases = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
print(f"chạy {len(cases)} case cho {AID} qua {PLATFORM}\n")
ok = 0
for i, c in enumerate(cases, 1):
    q, expects = c["q"], c.get("expect", [])
    try:
        ans = ask(q)
    except Exception as e:
        print(f"  ❌ case {i}: lỗi gọi API: {e}"); continue
    low = ans.lower()
    miss = [e for e in expects if e.lower() not in low]
    if not miss:
        ok += 1; print(f"  ✅ case {i}: {q[:50]!r}")
    else:
        print(f"  ❌ case {i}: {q[:50]!r}\n     thiếu: {miss}\n     trả lời: {ans[:160]!r}")
print(f"\nKẾT QUẢ: {ok}/{len(cases)} pass")
sys.exit(0 if ok == len(cases) else 1)
PY
