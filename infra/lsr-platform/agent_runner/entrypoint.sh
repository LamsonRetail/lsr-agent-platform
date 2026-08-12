#!/bin/bash
# Entrypoint agent runner (P2: Model Auth ladder).
# Thay vì token cứng, runner LEASE credential từ broker mỗi lần chạy:
#   subscription riêng → pool → API (litellm). Broker trả REF (đường dẫn file trong
#   /secrets, mount read-only) — secret KHÔNG bao giờ đi qua HTTP/log.
# Fallback: nếu broker không có credential mà env đã có CLAUDE_CODE_OAUTH_TOKEN thì dùng luôn.
set -u

PLATFORM="${LSR_PLATFORM_URL:-http://platform_api:8090}"
ATOKEN="${LSR_TELEMETRY_API_KEY:-${LSR_AGENT_TOKEN:-}}"
CREDENTIAL_ID=""

jval() { python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('$1','') or '')" 2>/dev/null; }

lease_credential() {
  [ -z "$ATOKEN" ] && { echo "[lsr-agent] thiếu agent token — bỏ lease, dùng env sẵn có"; return; }
  local resp mode ref envvar base model
  resp=$(curl -s -X POST "$PLATFORM/v1/self/model-auth/lease" -H "Authorization: Bearer $ATOKEN")
  mode=$(echo "$resp"   | jval mode)
  ref=$(echo "$resp"    | jval secret_ref)
  envvar=$(echo "$resp" | jval env_var)
  CREDENTIAL_ID=$(echo "$resp" | jval credential_id)
  if [ -z "$ref" ] || [ ! -f "/secrets/$ref" ]; then
    echo "[lsr-agent] lease chưa có credential khả dụng (mode='${mode:-none}') — dùng env fallback nếu có"
    return
  fi
  local val; val=$(cat "/secrets/$ref")
  export "$envvar=$val"
  echo "[lsr-agent] leased credential=$CREDENTIAL_ID mode=$mode → \$$envvar (từ /secrets/$ref)"
  if [ "$mode" = "api" ]; then
    base=$(echo "$resp" | jval base_url); model=$(echo "$resp" | jval model)
    [ -n "$base" ]  && export ANTHROPIC_BASE_URL="$base"
    [ -n "$model" ] && export ANTHROPIC_MODEL="$model"
    echo "[lsr-agent] chế độ API qua litellm base=$base model=$model"
  fi
}

report_limit() {
  [ -z "$CREDENTIAL_ID" ] && return
  curl -s -X POST "$PLATFORM/v1/self/model-auth/report" -H "Authorization: Bearer $ATOKEN" \
    -H "Content-Type: application/json" -d "{\"credential_id\":\"$CREDENTIAL_ID\",\"reason\":\"limit\"}" >/dev/null
  echo "[lsr-agent] đã báo limit cho credential=$CREDENTIAL_ID → chuyển account khác"
}

echo "[lsr-agent] khởi động agent ${LSR_AGENT_ID:-?}"
lease_credential
if [ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "[lsr-agent] ⚠️ chưa có credential nào (lease trống + không env) — agent không xác thực được."
fi

# Lấy code agent nếu có repo
if [ -n "${AGENT_REPO:-}" ]; then
  echo "[lsr-agent] clone ${AGENT_REPO}"
  git clone --depth 1 "${AGENT_REPO}" /agent/src 2>/dev/null && cd /agent/src || cd /agent
fi

claude plugin install /opt/lsr-telemetry >/dev/null 2>&1 || true

CMD="${AGENT_START_CMD:-echo '[lsr-agent] chưa đặt AGENT_START_CMD — giữ sống'; tail -f /dev/null}"

# Vòng chạy: nếu agent thoát vì rate-limit → báo broker → lease account khác → chạy lại.
MAX_RELEASE=5
for i in $(seq 1 $MAX_RELEASE); do
  set +e
  out=$(bash -lc "$CMD" 2>&1); code=$?
  set -e
  echo "$out"
  if echo "$out" | grep -qiE "rate.?limit|status 429|usage limit|quota exceeded"; then
    report_limit
    lease_credential
    continue
  fi
  exit $code
done
echo "[lsr-agent] hết lượt đổi credential ($MAX_RELEASE) — dừng."
