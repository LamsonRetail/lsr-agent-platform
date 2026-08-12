#!/usr/bin/env bash
# Thêm 1 credential model vào POOL (chạy TRÊN VM /opt/lsr-platform).
# Secret chỉ ghi ra file trên VM; DB chỉ giữ ref. Token KHÔNG bao giờ vào git/DB/log.
#
# Dùng:
#   ./add-model-credential.sh <id> <subscription|api_key> [priority] [owner_email] [expires_days]
# expires_days: token `claude setup-token` sống ~1 năm → mặc định 365 cho subscription.
#   Platform sẽ cảnh báo qua Telegram khi còn 30/7/3 ngày và TỰ BỎ QUA token đã quá hạn.
# Rồi dán token khi được hỏi (không hiện lên màn hình).
#
# Ví dụ:
#   ./add-model-credential.sh sub-nga subscription 10 ngadt@hapas.vn
#   ./add-model-credential.sh api-main api_key 100 platform@lamsonretail.vn
set -euo pipefail

ID="${1:?cần id}"; KIND="${2:?cần kind: subscription|api_key}"
PRIO="${3:-100}"; OWNER="${4:-}"
if [ -n "${5:-}" ]; then EXP_DAYS="$5"
elif [ "$KIND" = "subscription" ]; then EXP_DAYS=365      # setup-token ~1 năm
else EXP_DAYS=""; fi
case "$KIND" in subscription|api_key) ;; *) echo "kind phải là subscription|api_key"; exit 1;; esac

ROOT="${LSR_ROOT:-/opt/lsr-platform}"
SECRETS_DIR="$ROOT/secrets/model"
REF="model/${ID}.env"
mkdir -p "$SECRETS_DIR"
chmod 700 "$ROOT/secrets" "$SECRETS_DIR" 2>/dev/null || true

echo -n "Dán token cho '$ID' ($KIND) rồi Enter (ẩn): "
read -r -s TOKEN; echo
[ -z "$TOKEN" ] && { echo "token rỗng — huỷ"; exit 1; }
printf '%s' "$TOKEN" > "$SECRETS_DIR/${ID}.env"
chmod 600 "$SECRETS_DIR/${ID}.env"
unset TOKEN
echo "✓ đã ghi secret: $SECRETS_DIR/${ID}.env (chmod 600)"

# Đăng ký metadata (ref) vào DB qua admin API — KHÔNG gửi secret.
ADMIN="$(grep '^PLATFORM_ADMIN_TOKEN=' "$ROOT/.env" | cut -d= -f2-)"
curl -s -X POST "http://localhost:8090/v1/model-auth/credentials" \
  -H "Authorization: Bearer $ADMIN" -H "Content-Type: application/json" \
  -d "{\"id\":\"$ID\",\"kind\":\"$KIND\",\"secret_ref\":\"$REF\",\"priority\":$PRIO,\"owner_email\":\"$OWNER\"${EXP_DAYS:+,\"expires_days\":$EXP_DAYS}}"
echo
echo "✓ đã đăng ký '$REF' vào pool (priority=$PRIO${EXP_DAYS:+, hạn ${EXP_DAYS} ngày})."
[ -n "$EXP_DAYS" ] && echo "  → AG-OPS sẽ nhắc qua Telegram khi còn 30/7/3 ngày."
echo "  Xem lại: Console → Model Auth"
