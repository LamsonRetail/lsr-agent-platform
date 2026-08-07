#!/usr/bin/env bash
# Kiểm tra thay đổi CHỈ nằm trong phạm vi agent (không chạm core).
# Dùng: bash scripts/check-scope.sh              (kiểm file đang staged)
#       bash scripts/check-scope.sh --vs-main    (kiểm so với main)
# Cùng luật với CI scope-guard. Maintainer bỏ qua kiểm này (chỉ CI mới gác cứng).
set -u

if [ "${1:-}" = "--vs-main" ]; then
  base=$(git merge-base HEAD origin/main 2>/dev/null || git merge-base HEAD main 2>/dev/null || echo "")
  files=$(git diff --name-only "${base:-HEAD~1}" HEAD)
else
  files=$(git diff --cached --name-only)
  [ -z "$files" ] && files=$(git diff --name-only)   # fallback: chưa stage
fi

violations=""
while IFS= read -r f; do
  [ -z "$f" ] && continue
  case "$f" in
    agents/AG-LSR-BRAIN/*|agents/minh-anh/*) violations="$violations $f" ;;   # agent nền tảng = core
    agents/*/*|apps/agents/*/*) : ;;                                          # được phép
    *) violations="$violations $f" ;;                                         # core
  esac
done <<< "$files"

if [ -z "$violations" ]; then
  echo "✅ Thay đổi nằm trong phạm vi agent — OK."
  exit 0
fi

echo "❌ Chạm CORE (không được phép nếu bạn không phải maintainer):"
for v in $violations; do echo "   - $v"; done
cat <<'MSG'

Bạn chỉ được thêm/sửa:
   • agents/<AGENT_ID>/**        (manifest, prompt, test của agent)
   • apps/agents/<AGENT_ID>/**   (backend riêng của agent)
Đổi core (infra/ src/ scripts/ plugins/ apps/platform-web/ .github/ tests/ docs/,
agent nền tảng, rules chung) → nhờ maintainer. Xem .github/CODEOWNERS.
MSG
exit 1
