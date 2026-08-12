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
"""Consumer mẫu — poll job từ platform, xử lý, trả kết quả.

Chạy: LSR_AGENT_TOKEN=... python3 consumer.py   (token nhận khi enroll)
Job đến từ MỌI kênh (Lark/web chat/cron) qua cùng một queue — sửa handle() là đủ.
"""
import json, os, time, urllib.request, urllib.error

PLATFORM = os.environ.get("LSR_PLATFORM_URL", "https://platform.34-126-154-135.sslip.io").rstrip("/")
TOKEN = os.environ["LSR_AGENT_TOKEN"]

def api(method, path, payload=None, timeout=40):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(PLATFORM + path, data=data, method=method, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read().decode()
        return json.loads(b) if b else {}

def handle(job) -> str:
    """<<< SỬA Ở ĐÂY: nhận câu hỏi, trả câu trả lời >>>"""
    q = (job.get("payload") or {}).get("text", "")
    return f"(demo) bạn hỏi: {q}"

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
                answer = handle(job)
                # đẩy câu trả lời (web chat đọc qua SSE; Lark trả qua /v1/lark/send)
                api("POST", f"/v1/self/jobs/{jid}/event",
                    {"kind": "message", "data": {"text": answer}})
                rt = job.get("reply_to") or {}
                if rt.get("channel") == "lark" and rt.get("chat_id"):
                    api("POST", "/v1/lark/send",
                        {"to": rt["chat_id"], "to_type": "chat_id", "text": answer})
                api("POST", f"/v1/self/jobs/{jid}/complete", {"result": {"ok": True}})
                print(f"✓ job#{jid}")
            except Exception as exc:
                print(f"✗ job#{jid}: {exc}")
                try: api("POST", f"/v1/self/jobs/{jid}/fail", {"error": str(exc)[:400]})
                except Exception: pass

if __name__ == "__main__":
    main()
EOF

cat > "$DIR/README.md" <<EOF
# $NAME ($AID)

Thứ tự làm việc (gate tự nhắc nếu bỏ qua):
1. Điền **USECASE.md** → 2. Điền **TESTCASES.md** (+ tests.jsonl) → 3. Code (consumer.py / Claude Code)

Chạy nhanh:
\`\`\`bash
# đăng ký agent (1 lần) — nhận LSR_AGENT_TOKEN, lưu vào .env.lsr (gitignored)
python3 scripts/lsr_adopt.py --enroll-token <hỏi admin> --id $AID --name "$NAME" --owner <email>

# chạy agent
cd agents/$AID && LSR_AGENT_TOKEN=... python3 consumer.py

# test tự động theo tests.jsonl (terminal khác)
bash scripts/agent-test.sh $AID

# chat tay 1 câu
bash scripts/agent-chat.sh $AID "câu hỏi thử"
\`\`\`
EOF

echo "✓ đã tạo $DIR/ (USECASE.md, TESTCASES.md, tests.jsonl, consumer.py, README.md)"
echo ""
echo "Bước tiếp theo:"
echo "  1. Điền $DIR/USECASE.md và $DIR/TESTCASES.md  ← BẮT BUỘC trước khi code"
echo "  2. Đăng ký: python3 scripts/lsr_adopt.py --id $AID ... (xem $DIR/README.md)"
echo "  3. Code handle() trong consumer.py, chạy, rồi: bash scripts/agent-test.sh $AID"
