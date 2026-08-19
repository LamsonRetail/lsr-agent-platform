#!/usr/bin/env bash
# Cài môi trường dev cho dự án AG-FINANCE. Chạy MỘT LẦN sau khi clone repo.
#
#   bash agents/AG-FINANCE/scripts/setup-dev.sh
#
# Script này chỉ ghi vào .git/hooks (local, không phải file của repo) và thư mục
# agents/AG-FINANCE/ — không chạm core.

set -euo pipefail

root="$(git rev-parse --show-toplevel)"
cd "$root"
AGENT_DIR="agents/AG-FINANCE"

echo "==> 1/3 Cài git hook chặn commit ngoài phạm vi"
hook="$(git rev-parse --git-path hooks/pre-commit)"
mkdir -p "$(dirname "$hook")"
if [ -e "$hook" ] && ! grep -q "AG-FINANCE/scripts/precommit-scope.sh" "$hook"; then
  cp "$hook" "$hook.bak.$(date +%s)"
  echo "    (đã sao lưu pre-commit cũ thành $hook.bak.*)"
fi
cat > "$hook" <<'HOOK'
#!/usr/bin/env sh
exec bash "$(git rev-parse --show-toplevel)/agents/AG-FINANCE/scripts/precommit-scope.sh"
HOOK
chmod +x "$hook"
chmod +x "$AGENT_DIR/scripts/"*.sh
echo "    ✓ hook đã cài: $hook"

echo "==> 2/3 Tạo virtualenv + cài thư viện"
if [ ! -d "$AGENT_DIR/.venv" ]; then
  python3 -m venv "$AGENT_DIR/.venv"
fi
"$AGENT_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$AGENT_DIR/.venv/bin/pip" install --quiet -r "$AGENT_DIR/requirements.txt"
echo "    ✓ xong. Kích hoạt: source $AGENT_DIR/.venv/bin/activate"

echo "==> 3/3 Tạo file .env"
if [ -f "$AGENT_DIR/.env" ]; then
  echo "    (.env đã có, giữ nguyên)"
else
  cp "$AGENT_DIR/.env.example" "$AGENT_DIR/.env"
  echo "    ✓ đã tạo $AGENT_DIR/.env — MỞ RA ĐIỀN TOKEN trước khi chạy"
fi

cat <<'MSG'

────────────────────────────────────────────────────────────
✅ Xong. Việc tiếp theo:

  1. Đọc  agents/AG-FINANCE/ONBOARDING.md
  2. Điền agents/AG-FINANCE/.env
  3. Chạy test: cd agents/AG-FINANCE && .venv/bin/python -m pytest tests/ -q

Nhắc: chỉ sửa file trong agents/AG-FINANCE/. Hook vừa cài sẽ chặn nếu lỡ chạm
ra ngoài. Đó là chủ ý, không phải lỗi.
────────────────────────────────────────────────────────────

MSG
