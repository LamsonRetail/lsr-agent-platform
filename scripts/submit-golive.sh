#!/usr/bin/env bash
# Nộp golive checklist của agent → platform. Đủ 28 mục là hệ thống TỰ trình admin duyệt.
#
# Dùng (chạy ở gốc repo):
#   bash scripts/lsr-login.sh                      # 1 lần, nếu chưa đăng nhập
#   bash scripts/submit-golive.sh AG-HARRY         # đọc agents/AG-HARRY/golive.json
#
# Không có file? Copy mẫu: cp templates/golive.example.json agents/<ID>/golive.json
set -euo pipefail

AID="${1:?cần agent id, vd: AG-HARRY}"
FILE="${2:-agents/$AID/golive.json}"
PLATFORM="${LSR_PLATFORM_URL:-https://platform.34-126-154-135.sslip.io}"
TOKEN_FILE="${LSR_TOKEN_FILE:-$HOME/.lsr/token}"

[ -f "$FILE" ] || { echo "✗ không thấy $FILE"; echo "  Tạo bằng: cp templates/golive.example.json $FILE"; exit 1; }
[ -f "$TOKEN_FILE" ] || { echo "✗ chưa đăng nhập platform. Chạy: bash scripts/lsr-login.sh"; exit 1; }
python3 -c "import json,sys; json.load(open('$FILE'))" || { echo "✗ $FILE không phải JSON hợp lệ"; exit 1; }

BODY=$(python3 - "$FILE" <<'PY'
import json, sys
p = json.load(open(sys.argv[1]))
p = {k: v for k, v in p.items() if not k.startswith("_")}   # bỏ ghi chú
print(json.dumps({"payload": p}, ensure_ascii=False))
PY
)
RES=$(curl -sS -X POST "$PLATFORM/v1/agents/$AID/golive-checklist" \
  -H "Authorization: Bearer $(cat "$TOKEN_FILE")" \
  -H "Content-Type: application/json" -d "$BODY")

echo "$RES" | python3 - <<'PY'
import json, sys
d = json.load(sys.stdin)
if d.get("detail"):
    print("✗ platform từ chối:", d["detail"]); raise SystemExit(1)
if d.get("complete"):
    print("✅ Checklist ĐỦ — đã trình admin duyệt golive.")
    if d.get("approval_request_id"):
        print(f"   Mã đề xuất: #{d['approval_request_id']} (admin duyệt ở Console → Duyệt việc)")
    print("   Chờ admin bấm Duyệt là agent chạy kênh thật. Owner sẽ được nhắn khi xong.")
else:
    miss = d.get("missing") or []
    print(f"⚠️  Còn thiếu {len(miss)} mục — bổ sung rồi chạy lại lệnh này:")
    for m in miss:
        print("   -", m)
    raise SystemExit(2)
PY
