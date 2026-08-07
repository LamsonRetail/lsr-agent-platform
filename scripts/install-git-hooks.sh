#!/usr/bin/env bash
# Cài git pre-commit hook chặn commit chạm CORE (chạy scripts/check-scope.sh).
# Dùng 1 lần sau khi clone: bash scripts/install-git-hooks.sh
set -eu
root=$(git rev-parse --show-toplevel)
hook="$root/.git/hooks/pre-commit"
cat > "$hook" <<'HOOK'
#!/usr/bin/env bash
# LSR scope guard (local). Bỏ qua: git commit --no-verify (maintainer khi sửa core).
exec bash "$(git rev-parse --show-toplevel)/scripts/check-scope.sh"
HOOK
chmod +x "$hook"
echo "✅ Đã cài pre-commit hook → chặn commit chạm core. (maintainer sửa core: git commit --no-verify)"
