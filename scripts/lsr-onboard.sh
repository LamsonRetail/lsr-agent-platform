#!/usr/bin/env bash
# =============================================================================
# LSR Agent — onboard 1 dự án agent vào platform (copy-paste vào repo agent MỚI).
# Tự: tải helper từ platform, đăng ký (self-service), cài hook telemetry + điểm
# chặn runtime, ghi .env.lsr, in link Dashboard + Backend riêng của agent.
# KHÔNG cần GitHub, không cần admin token. Chạy trong thư mục dự án agent của bạn.
# =============================================================================
set -euo pipefail

# ---- 1) SỬA 4 dòng dưới cho agent của bạn ----
AGENT_ID="AG-YOURNAME"          # mã agent, IN HOA, vd AG-SALESBOT
NAME="Ten agent cua ban"        # tên hiển thị
OWNER="ban@hapas.vn"            # email owner (auth dùng subscription của người này)
SQUAD="RETAIL"                  # squad: RETAIL | HAPAS-TL | PLATFORM | ...
BACKEND_URL=""                  # URL backend riêng của agent (nếu đã deploy); rỗng = dùng trang platform

# ---- 2) Hằng số platform (đã điền sẵn — không cần đổi) ----
PLATFORM="https://platform.34-126-154-135.sslip.io"
COLLECTOR="https://collector.34-126-154-135.sslip.io"
APP="https://app.34-126-154-135.sslip.io"
ENROLL_TOKEN="${LSR_ENROLL_TOKEN:-DAN_ENROLL_TOKEN_VAO_DAY}"   # xin admin token

# ---- 3) Tải helper TỪ PLATFORM (repo private nên không dùng raw GitHub) ----
echo "→ Tải helper..."
curl -fsSL "$PLATFORM/bootstrap/lsr_adopt.py" -o lsr_adopt.py
curl -fsSL "$PLATFORM/bootstrap/lsr_trace.py" -o lsr_trace.py

# ---- 4) Đăng ký + cài hook (self-service bằng enroll token) ----
python3 lsr_adopt.py \
  --id "$AGENT_ID" --name "$NAME" --owner "$OWNER" --squad "$SQUAD" \
  --platform "$PLATFORM" --collector "$COLLECTOR" \
  --enroll-token "$ENROLL_TOKEN" --trace-script ./lsr_trace.py \
  ${BACKEND_URL:+--backend-url "$BACKEND_URL"}

# ---- 5) Xong ----
cat <<EOF

✅ Hoàn tất. Bước cuối:
   1) Đăng nhập subscription của bạn:   claude setup-token
   2) Nạp biến môi trường khi chạy agent:   set -a && source .env.lsr && set +a
   3) Chạy agent như bình thường — platform sẽ nắm trace/token + enforce runtime.

🔗 Link riêng của agent (mở bằng trình duyệt, basic-auth user 'lamson'):
   Dashboard: $APP/agent/$AGENT_ID
   Backend:   $APP/agent/$AGENT_ID#backend

Golive: hoàn tất checklist trong Backend rồi báo admin chuyển agent sang 'active'.
EOF
