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
echo [4/6] Chuyen sang branch %BRANCH%...
REM Branch da co tren GitHub thi noi tiep vao no, chua co thi tao tu main.
git rev-parse --verify origin/%BRANCH% >nul 2>&1 && (
  git checkout -B %BRANCH% origin/%BRANCH%
) || (
  git checkout -B %BRANCH% origin/main
)
if errorlevel 1 (echo LOI: khong chuyen duoc branch & exit /b 1)

echo.
REM ---------------------------------------------------------------------
REM  KHONG tu chep workflow vao .github/workflows/ nua.
REM  Ly do: scope-guard chan PR cua nguoi khong phai maintainer neu cham
REM  vao CORE (.github/, infra/, src/, scripts/...). Danh sach maintainer
REM  o .github/maintainers.txt — hien chi co ntranthi va thienquy71.
REM  Ban goc workflow van nam o agents/AG-INVENTORY-DAYS/deploy/ (thuoc
REM  pham vi agent, duoc phep). Maintainer chep ra .github/workflows/ ho.
REM ---------------------------------------------------------------------
if exist ".github\workflows\deploy-ag-inventory-days.yml" (
  echo   Go workflow khoi .github/workflows (scope-guard khong cho nguoi ngoai core sua)
  git rm --quiet --ignore-unmatch ".github/workflows/deploy-ag-inventory-days.yml" >nul 2>&1
  del /Q ".github\workflows\deploy-ag-inventory-days.yml" >nul 2>&1
)

echo [5/6] Commit thu muc AG-INVENTORY-DAYS...
git add agents/AG-INVENTORY-DAYS
REM Workflow deploy cua agent nam ngoai thu muc agent -> phai add rieng,
REM khong thi day len ma CI/CD khong bao gio chay.
git reset -q agents/AG-INVENTORY-DAYS/push_log.txt 2>nul
git rm -r -q --cached --ignore-unmatch agents/AG-INVENTORY-DAYS/src/__pycache__ 2>nul
git status --short agents/AG-INVENTORY-DAYS
git commit -m "docs(AG-INVENTORY-DAYS): them USECASE.md + TESTCASES.md, go workflow khoi core" -m "- USECASE.md + TESTCASES.md: bo sung theo yeu cau cua agent-gate (use case -> test case -> code)." -m "- Go .github/workflows/deploy-ag-inventory-days.yml khoi PR: scope-guard chi cho maintainer cham CORE. Ban goc giu o agents/AG-INVENTORY-DAYS/deploy/ de maintainer chep ra." -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
if errorlevel 1 (echo LOI: commit that bai - doc dong loi phia tren. & exit /b 1)

echo.
echo Commit vua tao:
git log --oneline -1
echo So file trong commit:
git show --stat --oneline HEAD | find /c "|"

echo.
echo [6/6] Push len GitHub...
git push -u origin %BRANCH%
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
