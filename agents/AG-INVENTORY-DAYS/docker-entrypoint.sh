#!/bin/sh
# Dựng tham số cho bot_poll.py từ biến môi trường (docker compose không truyền
# được mảng, nên CHAT_IDS là danh sách cách nhau bởi dấu phẩy).
set -e

ARGS=""

for cid in $(echo "${CHAT_IDS:-}" | tr ',' ' '); do
  [ -n "$cid" ] && ARGS="$ARGS --chat-id $cid"
done

[ -n "${EXCEL_PATH:-}" ] && ARGS="$ARGS --excel $EXCEL_PATH"
[ "${ANSWER_ALL:-false}" = "true" ] && ARGS="$ARGS --answer-all"
[ -n "${POLL_INTERVAL:-}" ] && ARGS="$ARGS --interval $POLL_INTERVAL"

echo "==> python bot_poll.py$ARGS  (DRY_RUN=${DRY_RUN:-true})"
exec python -u bot_poll.py $ARGS
