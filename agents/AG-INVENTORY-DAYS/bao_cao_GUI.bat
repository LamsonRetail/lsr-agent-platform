@echo off
REM ============================================================
REM  Dung anh bao cao KHHH tu Base va GUI VAO NHOM LARK
REM  (hien duoi ten bot PLANNING' ASSISTANT).
REM  Bam doi chuot vao file nay.
REM ============================================================
setlocal
set CHAT_ID=oc_618134792f49a95d2f455314261c0215
set LOG=%~dp0bao_cao_log.txt

call :run > "%LOG%" 2>&1
type "%LOG%"
echo.
echo ============================================================
echo  Log day du: %LOG%
echo  Anh vua dung: %~dp0bao_cao_khhh.png
echo ============================================================
pause >nul
exit /b 0

:run
echo ==== %DATE% %TIME% ====
cd /d "%~dp0src"

echo [1/2] Cai thu vien (lan dau hoi lau)...
python -m pip install --quiet --disable-pip-version-check requests pyyaml python-dotenv matplotlib pillow
if errorlevel 1 (echo LOI: cai thu vien that bai. & exit /b 1)

echo.
echo [2/2] Doc Base, dung anh, gui vao nhom...
python khhh_report.py --chat-id %CHAT_ID% --out "%~dp0bao_cao_khhh.png"
if errorlevel 1 (
  echo.
  echo LOI. Doc dong loi phia tren:
  echo  - "Doc Base that bai ... 91402/403"  = thieu scope bitable:app:readonly,
  echo                                         hoac chua them bot lam cong tac vien cua Base
  echo  - "Upload anh that bai"              = thieu scope im:resource
  echo  Sau khi them scope tren Developer Console nho PUBLISH VERSION moi.
  exit /b 1
)
echo.
echo ==== DA GUI XONG ====
exit /b 0
