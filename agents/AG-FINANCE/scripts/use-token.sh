#!/usr/bin/env bash
# Cắm token platform vào .env rồi kiểm tra trước khi chạy agent.
#
# Dùng:  bash scripts/use-token.sh lsr_tel_xxxxxxxx
#
# Kiểm token THUỘC AGENT NÀO trước khi chạy. Platform định danh agent bằng token chứ không
# bằng LSR_AGENT_ID, nên cầm nhầm token của agent khác thì mình ăn job và ghi telemetry vào
# schema của họ — đã xảy ra một lần với token của AG-LEGAL.
set -euo pipefail

TOKEN="${1:?cần token — dùng: bash scripts/use-token.sh lsr_tel_xxxxxxxx}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$DIR/.env"
PY="$DIR/.venv/bin/python"
[ -x "$PY" ] || PY=python3

PLATFORM=$(grep -E '^LSR_PLATFORM_URL=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d ' ')
PLATFORM="${PLATFORM:-https://platform.34-126-154-135.sslip.io}"

echo "→ kiểm token trên $PLATFORM"
SELF=$(curl -s -m 20 "$PLATFORM/v1/self" -H "Authorization: Bearer $TOKEN")

AID=$("$PY" -c "
import sys, json
try:
    d = json.loads(sys.stdin.read())
except ValueError:
    sys.exit(0)
print((d.get('agent') or {}).get('agent_id', ''))
" <<<"$SELF")

if [ -z "$AID" ]; then
  echo "✗ token không dùng được. Platform trả về:"
  echo "  $SELF"
  echo "  Nếu là 'agent token required' thì token sai, hết hạn hoặc đã bị thu hồi."
  exit 1
fi

echo "  token này thuộc agent: $AID"
if [ "$AID" != "AG-FINANCE" ]; then
  echo "✗ DỪNG: đây là token của $AID, không phải AG-FINANCE."
  echo "  Chạy tiếp sẽ lấy job và ghi telemetry vào schema của $AID. Xin token riêng cho AG-FINANCE."
  exit 1
fi

# Ghi vào .env. Dùng file tạm để không hỏng .env nếu sed lỗi giữa chừng.
TMP=$(mktemp)
if grep -qE '^LSR_AGENT_TOKEN=' "$ENV_FILE"; then
  sed "s|^LSR_AGENT_TOKEN=.*|LSR_AGENT_TOKEN=$TOKEN|" "$ENV_FILE" > "$TMP"
else
  cat "$ENV_FILE" > "$TMP"
  echo "LSR_AGENT_TOKEN=$TOKEN" >> "$TMP"
fi
mv "$TMP" "$ENV_FILE"

echo "✓ đã ghi token vào .env (file này đã gitignore)"
echo
echo "Chạy agent:"
echo "  set -a && . ./.env && set +a && .venv/bin/python -u consumer.py"
