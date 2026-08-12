#!/usr/bin/env bash
# Thêm/sửa credential app Lark cho gateway đa app (chạy TRÊN VM /opt/lsr-platform).
#
# Khác dán tay vào .env: script VALIDATE secret với Lark TRƯỚC khi ghi —
# sai là báo ngay tại chỗ, không để gateway lặp lỗi "app secret invalid".
# Tự làm sạch ký tự thừa khi copy/paste (\r, khoảng trắng, dấu nháy) và chống trùng dòng.
#
# Dùng:
#   bash scripts/add-lark-app.sh <PREFIX> <app_id> [service...]
# Ví dụ:
#   bash scripts/add-lark-app.sh SAWADEE cli_aaf6d2b3a5b8ded3 event_gateway_sawadee
#   bash scripts/add-lark-app.sh SOURCING cli_aaf6ce7c8d38deed event_gateway_sourcing
#   bash scripts/add-lark-app.sh DATA cli_xxx event_gateway_data
#
# Lưu ý: chạy qua ssh phải có -t (cần TTY để nhập ẩn):
#   ssh -t lsr-gcp "cd /opt/lsr-platform && bash scripts/add-lark-app.sh SAWADEE cli_... event_gateway_sawadee"
set -euo pipefail

PREFIX="${1:?cần prefix env (vd SAWADEE, SOURCING, DATA)}"
APP_ID="${2:?cần app_id (cli_...)}"
shift 2
SERVICES=("$@")
ROOT="${LSR_ROOT:-/opt/lsr-platform}"
DOMAIN="${LARK_DOMAIN:-https://open.larksuite.com}"
cd "$ROOT"

echo -n "Dán App Secret cho $APP_ID (dùng NÚT COPY trong Lark Developer Console) rồi Enter (ẩn): "
read -r -s SECRET; echo
# Làm sạch: bỏ \r (paste từ Windows/Lark web), khoảng trắng và dấu nháy bao quanh.
SECRET=$(printf '%s' "$SECRET" | tr -d '\r\n' | sed -e "s/^[[:space:]\"']*//" -e "s/[[:space:]\"']*\$//")
[ -z "$SECRET" ] && { echo "✗ secret rỗng — huỷ"; exit 1; }
echo "→ độ dài sau làm sạch: ${#SECRET} ký tự (App Secret chuẩn thường 32)"

# Validate với Lark TRƯỚC khi ghi. Secret truyền qua env (không lộ trong ps/history).
RESULT=$(LSR_TMP_SECRET="$SECRET" python3 - "$APP_ID" "$DOMAIN" <<'PY'
import json, os, sys, urllib.request
app_id, domain = sys.argv[1], sys.argv[2]
body = json.dumps({"app_id": app_id, "app_secret": os.environ["LSR_TMP_SECRET"]}).encode()
req = urllib.request.Request(domain + "/open-apis/auth/v3/tenant_access_token/internal",
                             data=body, headers={"Content-Type": "application/json"})
try:
    d = json.loads(urllib.request.urlopen(req, timeout=10).read())
    print(f"{d.get('code')}|{d.get('msg')}")
except Exception as e:
    print(f"-1|{e}")
PY
)
CODE="${RESULT%%|*}"; MSG="${RESULT#*|}"
if [ "$CODE" != "0" ]; then
  echo "✗ Lark TỪ CHỐI (code=$CODE: $MSG) — KHÔNG ghi .env."
  echo "  Kiểm tra: đúng app? copy đúng ô App Secret (bấm nút Copy, đừng bôi đen)?"
  exit 1
fi
echo "✓ Lark xác nhận secret HỢP LỆ."

# Ghi .env: xoá mọi dòng cũ của prefix (chống trùng) rồi thêm cặp mới.
sed -i "/^${PREFIX}_LARK_APP_ID=/d; /^${PREFIX}_LARK_APP_SECRET=/d" .env
printf '%s_LARK_APP_ID=%s\n%s_LARK_APP_SECRET=%s\n' \
  "$PREFIX" "$APP_ID" "$PREFIX" "$SECRET" >> .env
unset SECRET
echo "✓ đã ghi .env (${PREFIX}_LARK_APP_ID/SECRET)."

if [ ${#SERVICES[@]} -gt 0 ]; then
  echo "→ khởi động lại: platform_api ${SERVICES[*]}"
  sudo docker compose up -d platform_api "${SERVICES[@]}"
  sleep 5
  for s in "${SERVICES[@]}"; do
    echo "--- log $s (phải thấy 'connected to wss') ---"
    sudo docker compose logs --tail 4 "$s" 2>/dev/null | tail -4
  done
fi
