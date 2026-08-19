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
REM Workflow deploy cua agent duoc GIU trong thu muc agent (ban goc), va chep
REM ra .github/workflows/ khi push. Ly do: giu tat ca thu cua agent o mot cho,
REM ai clone ve cung co day du, khong phai di xin file roi.
set WF_SRC=agents\AG-INVENTORY-DAYS\deploy\deploy-ag-inventory-days.yml
set WF_DST=.github\workflows\deploy-ag-inventory-days.yml
if exist "%WF_SRC%" (
  if not exist ".github\workflows" mkdir ".github\workflows"
  copy /Y "%WF_SRC%" "%WF_DST%" >nul
  echo   Da cap nhat %WF_DST%
) else (
  echo   !! Khong thay %WF_SRC% — CI/CD se khong tu deploy agent len VM.
)
echo [5/6] Commit thu muc AG-INVENTORY-DAYS + workflow deploy...
git add agents/AG-INVENTORY-DAYS
REM Workflow deploy cua agent nam ngoai thu muc agent -> phai add rieng,
REM khong thi day len ma CI/CD khong bao gio chay.
if exist ".github\workflows\deploy-ag-inventory-days.yml" git add .github/workflows/deploy-ag-inventory-days.yml
git reset -q agents/AG-INVENTORY-DAYS/push_log.txt 2>nul
git rm -r -q --cached --ignore-unmatch agents/AG-INVENTORY-DAYS/src/__pycache__ 2>nul
git status --short agents/AG-INVENTORY-DAYS
git commit -m "feat(AG-INVENTORY-DAYS): noi Lark Base + tu dong deploy len VM" -m "- src/lark_base.py: doc ton kho thang tu Base QL KE HOACH HANG HOA thay cho file Excel. Cache 15 phut, Base loi thi dung lai so cu thay vi bao chua co du lieu." -m "- bot_poll.py: them --base, --refresh-minutes, khoa 1 tien trinh (truoc day chay 2 ban thi moi cau tra loi 2 lan)." -m "- coc.py: sua trich nguon sai (heading kieu 8 buoc bi doc thanh muc 8); uu tien muc/dong CO CON SO khi cau hoi la may ngay/bao nhieu." -m "- qa.py: sua _strip_accents khong xu ly duoc chu d (duoc -> duoc), lam hong moi tu khoa co chu d; them cau tra loi tu gioi thieu." -m "- knowledge: Code of Conduct v3 (75 muc) them luan chuyen kho, ghep/tach combo, van hoa LSR." -m "- .github/workflows/deploy-ag-inventory-days.yml: tu deploy agent len VM, co cong chan test va verify bot da chay." -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
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
