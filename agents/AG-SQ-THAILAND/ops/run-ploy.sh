#!/usr/bin/env bash
# Chạy Ploy (consumer) — dùng cho launchd/systemd hoặc chạy tay.
# Đọc .env cùng thư mục agent (KHÔNG in token ra log).
set -u
cd "$(dirname "$0")/.." || exit 1

if [ ! -f .env ]; then
  echo "$(date '+%F %T') ✗ thiếu .env (copy .env.example rồi điền LSR_AGENT_TOKEN)" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
. ./.env
set +a

echo "$(date '+%F %T') ▶ khởi động Ploy (DRY_RUN=${DRY_RUN:-true} MODEL=${LSR_MODEL_MODE:-off})"
exec python3 -u consumer.py
