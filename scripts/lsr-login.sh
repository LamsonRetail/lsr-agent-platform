#!/usr/bin/env bash
# Đăng nhập platform cho CLI/Claude Code — KHÔNG cần xin enroll token của ai.
#
# Cách hoạt động (giống `gh auth login`): script xin 1 mã, bạn mở console duyệt
# một lần, script nhận TOKEN CÁ NHÂN mang đúng quyền của bạn và lưu ~/.lsr/token.
# Từ đó `lsr_adopt.py`, `new-agent.sh`, các script khác tự dùng — không dán secret.
#
# Dùng:  bash scripts/lsr-login.sh          (mặc định 90 ngày)
#        bash scripts/lsr-login.sh --status  (xem đang đăng nhập bằng ai)
#        bash scripts/lsr-login.sh --logout
set -euo pipefail

PLATFORM="${LSR_PLATFORM_URL:-https://platform.34-126-154-135.sslip.io}"
TOKEN_FILE="${LSR_TOKEN_FILE:-$HOME/.lsr/token}"

api() {  # api <path> <json>
  curl -sS -X POST "$PLATFORM$1" -H "Content-Type: application/json" -d "$2"
}
jq_get() { python3 -c "import json,sys; print(json.load(sys.stdin).get('$1','') or '')"; }

case "${1:-}" in
  --logout)
    rm -f "$TOKEN_FILE" && echo "✓ đã đăng xuất (xoá $TOKEN_FILE)"; exit 0 ;;
  --status)
    [ -f "$TOKEN_FILE" ] || { echo "chưa đăng nhập — chạy: bash scripts/lsr-login.sh"; exit 1; }
    curl -sS "$PLATFORM/v1/auth/me" -H "Authorization: Bearer $(cat "$TOKEN_FILE")" \
      | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('Đăng nhập:', d.get('email'), '| quyền platform:', d.get('platform_role') or d.get('default_role'))
ar=d.get('agent_roles') or {}
[print(f'  {k}: {v}') for k,v in ar.items()]
"; exit 0 ;;
esac

LABEL="${LSR_LOGIN_LABEL:-$(hostname -s 2>/dev/null || echo CLI) · Claude Code}"
RES=$(api /v1/auth/device/start "{\"label\":\"$LABEL\"}")
DEVICE_CODE=$(echo "$RES" | jq_get device_code)
USER_CODE=$(echo "$RES" | jq_get user_code)
VERIFY_URL=$(echo "$RES" | jq_get verify_url)
[ -z "$DEVICE_CODE" ] && { echo "✗ không khởi tạo được đăng nhập: $RES"; exit 1; }

cat <<EOF

  ┌──────────────────────────────────────────────┐
     Mở link này và bấm DUYỆT:
     $VERIFY_URL

     Mã xác nhận:  $USER_CODE
  └──────────────────────────────────────────────┘

Đang chờ bạn duyệt (tối đa 15 phút)…
EOF
command -v open >/dev/null && open "$VERIFY_URL" 2>/dev/null || true

for _ in $(seq 1 300); do
  sleep 3
  P=$(api /v1/auth/device/poll "{\"device_code\":\"$DEVICE_CODE\"}")
  ST=$(echo "$P" | jq_get status)
  case "$ST" in
    approved)
      mkdir -p "$(dirname "$TOKEN_FILE")"
      echo "$P" | jq_get token > "$TOKEN_FILE"
      chmod 600 "$TOKEN_FILE"
      echo "✓ Đăng nhập thành công: $(echo "$P" | jq_get email)"
      echo "  Token lưu ở $TOKEN_FILE (hạn $(echo "$P" | jq_get expires_days) ngày, thu hồi được ở Console)."
      echo "  Giờ chạy được: python3 scripts/lsr_adopt.py --id AG-XXX --name \"Tên\""
      exit 0 ;;
    denied)  echo "✗ Bạn đã từ chối phiên đăng nhập này."; exit 1 ;;
    expired) echo "✗ Mã hết hạn — chạy lại lệnh này."; exit 1 ;;
  esac
done
echo "✗ Hết thời gian chờ — chạy lại lệnh này."; exit 1
