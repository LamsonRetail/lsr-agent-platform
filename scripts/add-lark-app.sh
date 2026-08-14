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
#   bash scripts/add-lark-app.sh NOTIFY cli_aaff13891ff85ee6 platform_api
#     ↑ PREFIX đặc biệt NOTIFY = Admin App của platform (OAuth đăng nhập console,
#       notify admin, bot broker mặc định) → ghi LARK_NOTIFY_APP_ID/SECRET.
#
# Lưu ý: chạy qua ssh phải có -t (cần TTY để nhập ẩn):
#   ssh -t lsr-gcp "cd /opt/lsr-platform && bash scripts/add-lark-app.sh SAWADEE cli_... event_gateway_sawadee"
set -euo pipefail

PREFIX="${1:?cần prefix env (vd SAWADEE, SOURCING, DATA, NOTIFY)}"
APP_ID="${2:?cần app_id (cli_...)}"
shift 2
SERVICES=("$@")
# NOTIFY = Admin App platform: tên biến chuẩn LARK_NOTIFY_APP_ID/SECRET (không có hậu tố _LARK_).
if [ "$PREFIX" = "NOTIFY" ]; then K_ID="LARK_NOTIFY_APP_ID"; K_SEC="LARK_NOTIFY_APP_SECRET"
else K_ID="${PREFIX}_LARK_APP_ID"; K_SEC="${PREFIX}_LARK_APP_SECRET"; fi
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

# Ghi .env: xoá mọi dòng cũ của cặp biến (chống trùng) rồi thêm cặp mới.
sed -i "/^${K_ID}=/d; /^${K_SEC}=/d" .env
printf '%s=%s\n%s=%s\n' "$K_ID" "$APP_ID" "$K_SEC" "$SECRET" >> .env
unset SECRET
echo "✓ đã ghi .env (${K_ID}/${K_SEC})."

if [ ${#SERVICES[@]} -gt 0 ]; then
  echo "→ khởi động lại: platform_api ${SERVICES[*]}"
  sudo docker compose up -d platform_api "${SERVICES[@]}"
  sleep 5
  for s in "${SERVICES[@]}"; do
    echo "--- log $s (phải thấy 'connected to wss') ---"
    sudo docker compose logs --tail 4 "$s" 2>/dev/null | tail -4
  done
fi
