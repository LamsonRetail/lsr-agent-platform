#!/usr/bin/env bash
# Chuyển console sang domain mới (chạy TRÊN VM /opt/lsr-platform).
#
# Vì sao cần script chứ không sửa .env tay: đổi CONSOLE_BASE_URL là đổi redirect_uri
# của Lark OAuth. Lark CHỈ nhận redirect_uri đã đăng ký trong console app — nếu chưa
# đăng ký, mọi người MẤT ĐĂNG NHẬP ngay lập tức (và cả luồng authorize C8). Script này
# kiểm 3 điều kiện TRƯỚC khi đổi, và không đổi gì nếu một điều kiện không đạt.
#
# Dùng:  bash scripts/switch-console-domain.sh agent.hapas-ai.tech
#        bash scripts/switch-console-domain.sh agent.hapas-ai.tech --kiem-tra   (chỉ kiểm)
set -euo pipefail

DOMAIN="${1:?cần domain, vd agent.hapas-ai.tech}"
CHI_KIEM="${2:-}"
ROOT="${LSR_ROOT:-/opt/lsr-platform}"
VM_IP="${VM_IP:-34.126.154.135}"
cd "$ROOT"

NEW="https://$DOMAIN"
ok=0; fail=0
b() { printf "  %-52s %s\n" "$1" "$2"; }

echo "== Kiểm trước khi đổi (không đổi gì nếu có mục ✗) =="

# 1) DNS phải trỏ về VM này, nếu không Let's Encrypt không cấp được cert.
IPS=$(dig +short "$DOMAIN" A 2>/dev/null | tr '\n' ' ')
if printf '%s' "$IPS" | grep -q "$VM_IP"; then b "DNS $DOMAIN -> $VM_IP" "✓"; ok=$((ok+1))
else b "DNS $DOMAIN -> $VM_IP" "✗ (đang: ${IPS:-không có record})"; fail=$((fail+1)); fi

# 2) HTTPS đã có cert thật (Caddy đã xin xong).
# curl tự in 000 khi không kết nối được; đừng thêm `|| echo 000` nữa (thành 000000).
CODE=$(curl -sS -o /dev/null -w '%{http_code}' "$NEW/login" 2>/dev/null) || true
if [ "$CODE" = "200" ]; then b "HTTPS $NEW/login" "✓ http 200"; ok=$((ok+1))
else b "HTTPS $NEW/login" "✗ http $CODE (chờ Caddy cấp cert)"; fail=$((fail+1)); fi

# 3) redirect_uri mới đã đăng ký trong Lark app chưa. Cách kiểm: dựng đúng URL
#    authorize và xem Lark có trả invalid_request không — URI lạ thì trả lỗi này.
APP_ID=$(grep -m1 '^LARK_NOTIFY_APP_ID=' .env | cut -d= -f2 | tr -d '\r')
RU=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1],safe=''))" "$NEW/api/auth/lark/callback")
U="https://accounts.larksuite.com/open-apis/authen/v1/authorize?app_id=$APP_ID&redirect_uri=$RU&state=kiemtra"
ERR=$(curl -sS -L "$U" 2>/dev/null | grep -oE 'error=[^"&]*' | head -1 || true)
if [ -z "$ERR" ]; then b "Lark đã đăng ký redirect_uri của $DOMAIN" "✓"; ok=$((ok+1))
else b "Lark đã đăng ký redirect_uri của $DOMAIN" "✗ ($ERR)"; fail=$((fail+1))
     echo "     → Lark Developer Console > app $APP_ID > Security Settings > Redirect URLs"
     echo "       thêm: $NEW/api/auth/lark/callback   (GIỮ luôn URL cũ trong lúc chuyển)"; fi

echo
if [ "$fail" -gt 0 ]; then
  echo "✗ Còn $fail mục chưa đạt — KHÔNG đổi gì. Xong các mục trên rồi chạy lại."
  exit 1
fi
[ "$CHI_KIEM" = "--kiem-tra" ] && { echo "✓ Đủ điều kiện. Bỏ --kiem-tra để đổi thật."; exit 0; }

echo "== Đổi .env =="
sudo cp .env "/root/.env.bak-truoc-doi-domain-$(date +%s)" 2>/dev/null || true
for K in CONSOLE_BASE_URL LSR_APP_PUBLIC; do
  sudo sed -i "/^$K=/d" .env
  echo "$K=$NEW" | sudo tee -a .env >/dev/null
  echo "  $K=$NEW"
done

echo "== Dựng lại platform_api + web =="
sudo docker compose up -d platform_api web >/dev/null
sleep 12

echo "== Kiểm sau khi đổi =="
b "console $NEW/login" "http $(curl -sS -o /dev/null -w '%{http_code}' "$NEW/login")"
b "console cũ vẫn sống" "http $(curl -sS -o /dev/null -w '%{http_code}' https://app.34-126-154-135.sslip.io/login)"
RU_NOW=$(sudo docker compose exec -T platform_api printenv CONSOLE_BASE_URL | tr -d '\r')
b "CONSOLE_BASE_URL trong container" "$RU_NOW"
echo
echo "Việc còn lại: đăng nhập thử trên $NEW (Lark OAuth) và kiểm /v1/lark/user/authorize/start."
echo "Phiên cũ trên domain cũ KHÔNG mất — cookie theo từng domain, mọi người đăng nhập lại là xong."
