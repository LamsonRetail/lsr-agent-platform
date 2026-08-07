#!/bin/bash
# =============================================================================
# LSR Agent — Trình cài đặt (macOS). NHẤP ĐÚP để chạy.
# Tự: cài plugin telemetry, đăng ký agent, cấu hình — không cần biết kỹ thuật.
# =============================================================================
cd "$(dirname "$0")" || exit 1
clear
echo "==================================================="
echo "   LSR Agent Platform — Cài đặt agent (macOS)"
echo "==================================================="
echo

PLATFORM="https://platform.34-126-154-135.sslip.io"
COLLECTOR="https://collector.34-126-154-135.sslip.io"
APP="https://app.34-126-154-135.sslip.io"
# Admin điền token trước khi phát; nếu để trống, trình cài sẽ hỏi.
ENROLL_TOKEN="__ENROLL_TOKEN__"

# --- Kiểm tra công cụ cần có ---
if ! command -v claude >/dev/null 2>&1; then
  echo "⚠️  Chưa cài Claude Code. Hãy cài trước tại: https://claude.com/claude-code"
  echo "    Cài xong, chạy lại file này."
  read -n1 -r -p "Nhấn phím bất kỳ để đóng..."; exit 1
fi
PY=python3; command -v python3 >/dev/null 2>&1 || PY=python
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "⚠️  Chưa có Python. Cài tại https://www.python.org/downloads/ rồi chạy lại."
  read -n1 -r -p "Nhấn phím bất kỳ để đóng..."; exit 1
fi

# --- Hỏi thông tin agent ---
[ "$ENROLL_TOKEN" = "__ENROLL_TOKEN__" ] && read -r -p "Mã mời (enroll token, xin admin): " ENROLL_TOKEN
read -r -p "Mã agent (vd AG-SALESBOT): " AGENT_ID
read -r -p "Tên agent: " NAME
read -r -p "Email của bạn (owner @hapas.vn): " OWNER
read -r -p "Squad (RETAIL / HAPAS-TL / PLATFORM): " SQUAD
echo

# --- Cài plugin (thử marketplace, fallback tải zip) ---
echo "→ Cài plugin telemetry..."
if ! (claude plugin marketplace add LamsonRetail/lsr-agent-platform && claude plugin install lsr-telemetry@lsr) >/dev/null 2>&1; then
  echo "  (marketplace không được — cài từ gói tải về)"
  curl -fsSL "$PLATFORM/bootstrap/lsr-telemetry-plugin.zip" -o /tmp/lsr-plugin.zip
  rm -rf /tmp/lsr-plugin && mkdir -p /tmp/lsr-plugin && unzip -oq /tmp/lsr-plugin.zip -d /tmp/lsr-plugin
  claude plugin install /tmp/lsr-plugin/lsr-telemetry >/dev/null 2>&1 || echo "  ⚠️ cài plugin thủ công: claude plugin install /tmp/lsr-plugin/lsr-telemetry"
fi

# --- Tải helper + đăng ký ---
echo "→ Đăng ký agent với platform..."
curl -fsSL "$PLATFORM/bootstrap/lsr_adopt.py" -o lsr_adopt.py
curl -fsSL "$PLATFORM/bootstrap/lsr_trace.py" -o lsr_trace.py
"$PY" lsr_adopt.py --id "$AGENT_ID" --name "$NAME" --owner "$OWNER" --squad "$SQUAD" \
  --platform "$PLATFORM" --collector "$COLLECTOR" \
  --enroll-token "$ENROLL_TOKEN" --trace-script ./lsr_trace.py
RC=$?

echo
if [ $RC -eq 0 ]; then
  echo "✅ XONG! Agent '$AGENT_ID' đã đăng ký."
  echo
  echo "   Còn 2 bước bạn tự làm:"
  echo "   1) Đăng nhập Claude của bạn:   claude setup-token"
  echo "   2) Khi chạy agent, nạp cấu hình: set -a && source .env.lsr && set +a"
  echo
  echo "   📊 Dashboard: $APP/agent/$AGENT_ID"
  echo "   🛠  Backend:   $APP/agent/$AGENT_ID#backend"
else
  echo "✗ Có lỗi khi đăng ký. Kiểm tra lại mã mời/agent id, hoặc báo admin."
fi
echo
read -n1 -r -p "Nhấn phím bất kỳ để đóng cửa sổ này..."
