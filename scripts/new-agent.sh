#!/usr/bin/env bash
# Scaffold agent mới theo quy trình platform: USE CASE → TEST CASE → code.
# Dùng: bash scripts/new-agent.sh AG-TEN-AGENT "Tên hiển thị"
set -euo pipefail

AID="${1:?cần agent id, vd: AG-KHO-HN}"
NAME="${2:-$AID}"
DIR="agents/$AID"

[[ "$AID" =~ ^AG-[A-Z0-9-]+$ ]] || { echo "agent id dạng AG-TEN-VIET-HOA (A-Z, 0-9, -)"; exit 1; }
[ -d "$DIR" ] && { echo "⛔ $DIR đã tồn tại"; exit 1; }
mkdir -p "$DIR"

cat > "$DIR/USECASE.md" <<EOF
# Use case — $NAME ($AID)

> ⚠️ BẮT BUỘC điền trước khi code (gate của platform sẽ chặn code nếu thiếu file này).

## Bài toán
<!-- Agent này giải quyết việc gì? Ai đang tốn thời gian vào việc đó? -->

## Người dùng
<!-- Ai dùng? Qua kênh nào (Lark nhóm nào / web chat / cron)? -->

## Luồng chính (happy path)
1. Người dùng gửi ...
2. Agent làm ...
3. Kết quả trả về ...

## Ngoài phạm vi (không làm)
-

## Dữ liệu cần truy cập
<!-- Nguồn nào (BigQuery/Sheet/Lark Doc...)? Đã được cấp quyền chưa? -->

## Rủi ro & giới hạn
-
EOF

cat > "$DIR/TESTCASES.md" <<EOF
# Test cases — $NAME ($AID)

> ⚠️ BẮT BUỘC trước khi code. Mỗi luồng ở USECASE.md có ít nhất 1 case.
> Case chạy tự động khai thêm ở tests.jsonl (bash scripts/agent-test.sh $AID).

| # | Kịch bản | Đầu vào | Kỳ vọng |
|---|----------|---------|---------|
| 1 | Happy path | "..." | Trả lời chứa ... |
| 2 | Thiếu dữ liệu | "..." | Hỏi lại, không bịa |
| 3 | Ngoài phạm vi | "..." | Từ chối lịch sự + chỉ đúng kênh |
EOF

cat > "$DIR/tests.jsonl" <<EOF
{"q": "câu hỏi happy path ở đây", "expect": ["từ khoá 1", "từ khoá 2"]}
{"q": "câu hỏi ngoài phạm vi", "expect": ["không"]}
EOF

cat > "$DIR/consumer.py" <<'EOF'
"""Consumer mẫu — poll job từ platform, dựng ngữ cảnh, trả lời, ghi nhớ.

Chạy tay: LSR_AGENT_TOKEN=... python3 consumer.py   (token nhận khi enroll)
Chạy trên VM qua POST /v1/self/deploy: runner tự tiêm token dưới tên LSR_TELEMETRY_API_KEY.
Job đến từ MỌI kênh (Lark/web chat/cron) qua cùng một queue — sửa answer() là đủ.

Ngữ cảnh do PLATFORM giữ (không nằm ở model): mỗi lượt gọi /v1/self/context để lấy
instruction (version đang publish) + tóm tắt + N lượt gần nhất + fact người dùng +
tri thức liên quan (có nguồn). Nhờ vậy đổi model/credential hay restart đều không mất mạch.
"""
import json, os, time, urllib.parse, urllib.request, urllib.error

PLATFORM = os.environ.get("LSR_PLATFORM_URL", "https://platform.34-126-154-135.sslip.io").rstrip("/")
# Hai tên, vì có hai đường chạy: docker-compose/chạy tay truyền LSR_AGENT_TOKEN, còn runtime
# trên VM (POST /v1/self/deploy) tiêm token agent dưới tên LSR_TELEMETRY_API_KEY
# (platform_api/app.py:1693 — entrypoint.sh:10 cũng đọc thứ tự này).
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
EOF

cat > "$DIR/Dockerfile" <<'EOF'
# Agent chạy trong container riêng — chỉ cần stdlib.
FROM python:3.11-slim
WORKDIR /agent
COPY consumer.py .
CMD ["python", "consumer.py"]
EOF

cat > "$DIR/docker-compose.yml" <<EOF
# Chạy agent ở bất kỳ đâu: docker compose up
# Chỉ cần LSR_AGENT_TOKEN — KHÔNG cần Vercel/Supabase/DB riêng.
services:
  agent:
    build: .
    environment:
      LSR_PLATFORM_URL: \${LSR_PLATFORM_URL:-https://platform.34-126-154-135.sslip.io}
      LSR_AGENT_ID: $AID
      LSR_AGENT_TOKEN: \${LSR_AGENT_TOKEN:?cần token — xin ở Console hoặc scripts/lsr_adopt.py}
      DRY_RUN: \${DRY_RUN:-true}
    restart: unless-stopped
EOF

cat > "$DIR/.env.example" <<'EOF'
# Copy thành .env rồi điền (KHÔNG commit .env)
LSR_AGENT_TOKEN=lsr_tel_...
DRY_RUN=true
EOF

cat > "$DIR/README.md" <<EOF
# $NAME ($AID)

Thứ tự làm việc (gate tự nhắc nếu bỏ qua):
1. Điền **USECASE.md** → 2. Điền **TESTCASES.md** (+ tests.jsonl) → 3. Code (consumer.py / Claude Code)

Chạy nhanh:
\`\`\`bash
# đăng ký agent (1 lần) — nhận LSR_AGENT_TOKEN, lưu vào .env.lsr (gitignored)
python3 scripts/lsr_adopt.py --enroll-token <hỏi admin> --id $AID --name "$NAME" --owner <email>

# chạy agent (Docker — giống môi trường thật)
cd agents/$AID && cp .env.example .env && vi .env && docker compose up
# hoặc chạy trực tiếp: LSR_AGENT_TOKEN=... python3 consumer.py

# test tự động theo tests.jsonl (terminal khác)
bash scripts/agent-test.sh $AID

# chat tay 1 câu
bash scripts/agent-chat.sh $AID "câu hỏi thử"
\`\`\`

## Console của agent
**https://app.34-126-154-135.sslip.io/agent/$AID** — chat thử, jobs, traces, chi phí,
brain riêng, version. KHÔNG cần tài khoản Vercel/Supabase: console nằm sẵn trong platform.

## Kênh vào (admin gán 1 dòng ở Console → Ingress)
| Kênh | Cần gì |
|---|---|
| Web chat | có sẵn, không cần gán |
| Telegram | channel=telegram, chat_id của chat |
| Lark | channel=lark, chat_id nhóm |
EOF

echo "✓ đã tạo $DIR/ (USECASE.md, TESTCASES.md, tests.jsonl, consumer.py, README.md)"
echo ""
echo "Bước tiếp theo:"
echo "  1. Điền $DIR/USECASE.md và $DIR/TESTCASES.md  ← BẮT BUỘC trước khi code"
echo "  2. Đăng ký: python3 scripts/lsr_adopt.py --id $AID ... (xem $DIR/README.md)"
echo "  3. Code handle() trong consumer.py, chạy, rồi: bash scripts/agent-test.sh $AID"
