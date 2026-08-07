#!/bin/bash
# Entrypoint agent runner. Env truyền vào: CLAUDE_CODE_OAUTH_TOKEN (owner),
# LSR_AGENT_ID, LSR_COLLECTOR, LSR_TELEMETRY_API_KEY, AGENT_REPO (tuỳ chọn),
# AGENT_START_CMD (lệnh chạy agent; mặc định giữ container sống).
set -u

echo "[lsr-agent] khởi động agent ${LSR_AGENT_ID:-?} (owner subscription)"

if [ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
  echo "[lsr-agent] ⚠️ thiếu CLAUDE_CODE_OAUTH_TOKEN (token subscription owner) — agent không xác thực được."
fi

# Lấy code agent nếu có repo
if [ -n "${AGENT_REPO:-}" ]; then
  echo "[lsr-agent] clone ${AGENT_REPO}"
  git clone --depth 1 "${AGENT_REPO}" /agent/src 2>/dev/null && cd /agent/src || cd /agent
fi

# Cài plugin telemetry cho phiên claude (best-effort)
claude plugin install /opt/lsr-telemetry >/dev/null 2>&1 || true

# Chạy lệnh agent; mặc định giữ sống để container không thoát (đổi bằng AGENT_START_CMD)
exec bash -lc "${AGENT_START_CMD:-echo '[lsr-agent] chưa đặt AGENT_START_CMD — container giữ sống, cấu hình sau'; tail -f /dev/null}"
