@echo off
REM ============================================================
REM  Chay bot ANN_KHHH (AG-INVENTORY-DAYS) tra loi trong nhom Lark.
REM  Bam doi chuot vao file nay la chay.
REM
REM  Lan dau: script tu cai thu vien can thiet.
REM  Muon tra ca ton kho: sua dong SET EXCEL= ben duoi tro tro toi file excel.
REM ============================================================
setlocal

REM --- Nhom Lark bot se phuc vu. ---
REM   oc_2659fb0822ebf7de6291f11c1f5ce37c = KHHH noi bo (nhom that)
REM   oc_618134792f49a95d2f455314261c0215 = test AI
set CHAT_ID=oc_618134792f49a95d2f455314261c0215

REM --- De trong = chi tra loi cau hoi quy trinh (Code of Conduct). ---
set EXCEL=

REM --- false = tra loi that vao nhom. true = chi in ra man hinh de test. ---
set DRY_RUN=false

cd /d "%~dp0src"

echo [1/3] Kiem tra Python...
python --version >nul 2>&1
if errorlevel 1 (
  echo   !! Khong tim thay Python. Tai tai https://www.python.org/downloads/
  echo      Nho tich "Add python.exe to PATH" khi cai.
  pause
  exit /b 1
)
python --version

echo [2/3] Cai thu vien...
python -m pip install --quiet --disable-pip-version-check requests pyyaml python-dotenv openpyxl
if errorlevel 1 (
  echo   !! Cai thu vien that bai. Kiem tra ket noi mang.
  pause
  exit /b 1
)

echo [3/3] Kiem tra tra cuu Code of Conduct...
python ..\tests\test_coc.py
if errorlevel 1 (
  echo   !! Test tra cuu that bai — dung lai de khong chay ban loi.
  pause
  exit /b 1
)

echo.
echo === Bot dang chay. Go cau hoi vao nhom Lark de thu. ===
echo === Vi du: "chot PR ngay nao" / "nguong ton kho cua hang" ===
echo === Bam Ctrl+C de dung. ===
echo.

if "%EXCEL%"=="" (
  python bot_poll.py --chat-id %CHAT_ID%
) else (
  python bot_poll.py --chat-id %CHAT_ID% --excel "%EXCEL%"
)

pause
