#!/usr/bin/env bash
# Chặn commit chạm file NGOÀI agents/AG-FINANCE/.
#
# Đây là lớp chặn LOCAL — báo lỗi ngay lúc commit, trước khi mất công push rồi bị CI
# (.github/workflows/scope-guard.yml) đánh trượt. Hai lớp này kiểm cùng một luật.
#
# Cài: bash agents/AG-FINANCE/scripts/setup-dev.sh
# Bỏ qua một lần (chỉ khi maintainer chủ ý sửa core): git commit --no-verify

set -euo pipefail

ALLOW_PREFIX="agents/AG-FINANCE/"
root="$(git rev-parse --show-toplevel)"
cd "$root"

# --cached: chỉ xét file đang staged. -z + read -d: an toàn với tên file có khoảng trắng.
violations=()
while IFS= read -r -d '' f; do
  [[ "$f" == "$ALLOW_PREFIX"* ]] || violations+=("$f")
done < <(git diff --cached --name-only -z --diff-filter=ACMRT)

if [ ${#violations[@]} -eq 0 ]; then
  exit 0
fi

cat >&2 <<MSG

────────────────────────────────────────────────────────────
❌ COMMIT BỊ CHẶN — có file nằm ngoài phạm vi dự án Finance.

Dự án AG-FINANCE chỉ được thêm/sửa file trong:
    ${ALLOW_PREFIX}

Các file vi phạm:
MSG
for v in "${violations[@]}"; do printf '    %s\n' "$v" >&2; done
cat >&2 <<MSG

Vì sao: mọi thứ ngoài thư mục trên là CORE của platform (infra/, src/, scripts/,
plugins/, apps/platform-web/, .github/, tests/, docs/, agent nền tảng). Sửa vào đó sẽ
bị CI scope-guard chặn và cần review của maintainer.

Cách xử lý:
  • Bỏ file ra khỏi commit:      git restore --staged <file>
  • Bỏ hẳn thay đổi ngoài scope: git checkout -- <file>
  • Thật sự cần đổi core:        mở issue nhờ maintainer (xem .github/CODEOWNERS)
────────────────────────────────────────────────────────────

MSG
exit 1
