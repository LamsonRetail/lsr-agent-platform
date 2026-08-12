#!/usr/bin/env bash
# Chat 1 câu với agent qua Chat API (đi qua ingress chung, có telemetry/quota).
# Dùng: bash scripts/agent-chat.sh AG-ID "câu hỏi"   (cần LSR_AGENT_TOKEN)
set -euo pipefail

AID="${1:?cần agent id}"; Q="${2:?cần câu hỏi}"
PLATFORM="${LSR_PLATFORM_URL:-https://platform.34-126-154-135.sslip.io}"
TOKEN="${LSR_AGENT_TOKEN:-}"
# tự đọc .env.lsr nếu chưa có token (repo root hoặc agents/<id>/)
for f in ".env.lsr" "agents/$AID/.env.lsr"; do
  [ -z "$TOKEN" ] && [ -f "$f" ] && TOKEN=$(grep '^LSR_TELEMETRY_API_KEY=\|^LSR_AGENT_TOKEN=' "$f" | head -1 | cut -d= -f2-)
done
[ -z "$TOKEN" ] && { echo "thiếu LSR_AGENT_TOKEN (hoặc .env.lsr)"; exit 1; }

R=$(curl -s -X POST "$PLATFORM/v1/chat/$AID/messages" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "$(python3 -c "import json,sys;print(json.dumps({'text':sys.argv[1]}))" "$Q")")
SID=$(echo "$R" | python3 -c "import sys,json;print(json.load(sys.stdin).get('session_id',''))")
[ -z "$SID" ] && { echo "gửi lỗi: $R"; exit 1; }
echo "→ đã gửi (session=$SID), chờ trả lời..."

curl -s -N --max-time "${LSR_CHAT_TIMEOUT:-60}" \
  "$PLATFORM/v1/chat/$AID/stream?session_id=$SID&token=$TOKEN" \
| while IFS= read -r line; do
    case "$line" in
      event:\ message) kind=message ;;
      event:\ done)    kind=done ;;
      event:\ error)   kind=error ;;
      data:*)
        d="${line#data: }"
        if [ "${kind:-}" = "message" ]; then
          echo "$d" | python3 -c "import sys,json;print('🤖', json.load(sys.stdin).get('text',''))"
        elif [ "${kind:-}" = "done" ]; then echo "✓ xong"; exit 0
        elif [ "${kind:-}" = "error" ]; then echo "✗ lỗi: $d"; exit 1; fi ;;
    esac
  done
