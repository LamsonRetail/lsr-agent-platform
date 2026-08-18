@echo off
REM ============================================================
REM  Day AG-INVENTORY-DAYS len GitHub tren 1 branch moi.
REM  Moi thu ghi ra push_log.txt de xem lai neu cua so dong mat.
REM ============================================================
setlocal enabledelayedexpansion
set BRANCH=PLANNING
set LOG=%~dp0push_log.txt

call :run > "%LOG%" 2>&1
type "%LOG%"
echo.
echo ============================================================
echo  Log day du: %LOG%
echo ============================================================
echo Bam phim bat ky de dong...
pause >nul
exit /b 0

:run
echo ==== BAT DAU %DATE% %TIME% ====
cd /d "%~dp0..\.."
echo Thu muc repo: %CD%

echo.
echo [1/6] Git...
git --version || (echo LOI: chua cai Git - tai tai https://git-scm.com/download/win & exit /b 1)

echo.
echo [2/6] Khai bao danh tinh git (chi trong repo nay)...
git config user.name  >nul 2>&1 || git config user.name "Hoang Thi Mai Thao"
git config user.email >nul 2>&1 || git config user.email "hoangmaithao252@gmail.com"
echo   user.name  = & git config user.name
echo   user.email = & git config user.email
echo.
echo Trang thai hien tai...
git status --short
git branch --show-current

echo.
echo [3/6] Lay ban moi nhat tu GitHub...
git fetch origin || (echo LOI: khong ket noi duoc GitHub & exit /b 1)

echo.
echo [4/6] Tao branch %BRANCH% tu origin/main...
git checkout -B %BRANCH% origin/main || (echo LOI: khong tao duoc branch & exit /b 1)

echo.
echo [5/6] Commit thu muc AG-INVENTORY-DAYS...
git add agents/AG-INVENTORY-DAYS
git reset -q agents/AG-INVENTORY-DAYS/push_log.txt 2>nul
git rm -r -q --cached --ignore-unmatch agents/AG-INVENTORY-DAYS/src/__pycache__ 2>nul
git status --short agents/AG-INVENTORY-DAYS
git commit -m "feat(AG-INVENTORY-DAYS): Code of Conduct KHHH lam kien thuc nen + deploy docker" -m "Agent tra loi duoc cau hoi quy trinh van hanh phong KHHH, khong chi ton kho." -m "- knowledge/CODE_OF_CONDUCT_KHHH.md: so tay van hanh 50 muc" -m "- src/coc.py: tra cuu bang tu khoa co trong so IDF, tra loi kem so muc" -m "- Chi tra loi khi duoc @mention hoac tra ra dap an chac chan" -m "- tests/test_coc.py: khoa hanh vi hoi-gi-ra-muc-nao va ca phai im lang" -m "- Dockerfile + docker-compose.yml + DEPLOY.md: chay 24/7 tren VM" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
if errorlevel 1 (echo LOI: commit that bai - doc dong loi phia tren. & exit /b 1)

echo.
echo Commit vua tao:
git log --oneline -1
echo So file trong commit:
git show --stat --oneline HEAD | find /c "|"

echo.
echo [6/6] Push len GitHub...
git push -u origin %BRANCH% --force-with-lease
if errorlevel 1 (
  echo.
  echo LOI: push that bai. Doc ky dong loi ngay phia tren.
  echo  - "Authentication failed"  = can dang nhap lai GitHub
  echo  - "403"                    = tai khoan khong co quyen ghi vao repo
  exit /b 1
)

echo.
echo ==== XONG ====
echo Tao Pull Request tai:
echo https://github.com/LamsonRetail/lsr-agent-platform/compare/%BRANCH%?expand=1
exit /b 0
