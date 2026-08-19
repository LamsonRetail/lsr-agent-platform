#!/usr/bin/env bash
# Chạy TRƯỚC khi mở PR. Kiểm ba thứ hay làm CI đỏ:
#
#   bash agents/AG-FINANCE/scripts/pre-pr-check.sh
#
#   1. Nhánh có chậm so với main không  ← nguyên nhân bị scope-guard chặn OAN
#   2. Thay đổi có nằm trong phạm vi agent không
#   3. Test có pass không
set -uo pipefail

root="$(git rev-parse --show-toplevel)"
cd "$root"
AGENT_DIR="agents/AG-FINANCE"
fail=0

echo "==> 1/3 So nhánh với origin/main"
git fetch origin main --quiet 2>/dev/null || echo "    (không fetch được, dùng bản origin/main đang có ở local)"
base=$(git merge-base origin/main HEAD 2>/dev/null || echo "")
if [ -z "$base" ]; then
  echo "    ⚠️  không xác định được merge-base, bỏ qua bước này"
else
  behind=$(git rev-list --count "$base"..origin/main)
  if [ "$behind" -gt 0 ]; then
    # scope-guard.yml của platform dùng `git diff base head` (HAI chấm) nên nó liệt kê cả
    # thay đổi mà main có sau điểm nhánh, rồi chặn với thông báo "bạn chạm vào CORE" —
    # nghe như mình làm sai trong khi mình chỉ sửa trong folder agent. Merge main vào là hết.
    echo "    ✗ nhánh chậm $behind commit so với origin/main."
    echo "      scope-guard SẼ CHẶN OAN và báo là bạn chạm vào core. Không phải bạn sai."
    echo "      Sửa:  git merge origin/main"
    fail=1
  else
    echo "    ✓ nhánh đã theo kịp origin/main"
  fi
fi

echo "==> 2/3 Kiểm phạm vi thay đổi so với origin/main"
if [ -z "$base" ]; then
  # Không có merge-base thì không so được. Nói rõ là BỎ QUA, đừng im lặng — im lặng trông
  # giống như đã kiểm và thấy sạch.
  echo "    ⚠️  không có merge-base nên bỏ qua. Clone nông (--depth) hay gặp;"
  echo "        chữa bằng: git fetch --unshallow"
else
  outside=$(git diff --name-only "$base"...HEAD | grep -v "^$AGENT_DIR/" || true)
  if [ -n "$outside" ]; then
    echo "    ✗ có file ngoài $AGENT_DIR/:"
    echo "$outside" | sed 's/^/        /'
    fail=1
  else
    echo "    ✓ chỉ chạm $AGENT_DIR/"
  fi
fi

echo "==> 3/3 Chạy test"
if [ -x "$AGENT_DIR/.venv/bin/python" ]; then
  if (cd "$AGENT_DIR" && .venv/bin/python -m pytest tests/ -q >/tmp/prepr-test.log 2>&1); then
    echo "    ✓ $(tail -1 /tmp/prepr-test.log)"
  else
    echo "    ✗ test đỏ:"
    tail -15 /tmp/prepr-test.log | sed 's/^/        /'
    fail=1
  fi
else
  echo "    ⚠️  chưa có .venv — chạy scripts/setup-dev.sh trước"
  fail=1
fi

echo "────────────────────────────────────────────────────────────"
if [ "$fail" -eq 0 ]; then
  echo "✅ Mở PR được."
else
  echo "❌ Sửa các mục ✗ ở trên rồi chạy lại. Mở PR bây giờ thì CI sẽ đỏ."
fi
exit "$fail"
