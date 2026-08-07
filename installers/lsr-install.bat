@echo off
REM ============================================================================
REM  LSR Agent - Trinh cai dat (Windows). NHAP DUP de chay.
REM  Tu: cai plugin telemetry, dang ky agent, cau hinh.
REM ============================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
title LSR Agent - Cai dat
echo ===================================================
echo    LSR Agent Platform - Cai dat agent (Windows)
echo ===================================================
echo.

set "PLATFORM=https://platform.34-126-154-135.sslip.io"
set "COLLECTOR=https://collector.34-126-154-135.sslip.io"
set "APP=https://app.34-126-154-135.sslip.io"
REM Admin dien token truoc khi phat; neu de trong, trinh cai se hoi.
set "ENROLL_TOKEN=__ENROLL_TOKEN__"

where claude >nul 2>nul
if errorlevel 1 (
  echo [!] Chua cai Claude Code. Cai tai: https://claude.com/claude-code roi chay lai.
  pause & exit /b 1
)
set "PY=python"
where python >nul 2>nul || set "PY=py"
where %PY% >nul 2>nul
if errorlevel 1 (
  echo [!] Chua co Python. Cai tai https://www.python.org/downloads/ roi chay lai.
  pause & exit /b 1
)

if "%ENROLL_TOKEN%"=="__ENROLL_TOKEN__" set /p ENROLL_TOKEN=Ma moi (enroll token, xin admin):
set /p AGENT_ID=Ma agent (vd AG-SALESBOT):
set /p NAME=Ten agent:
set /p OWNER=Email cua ban (owner @hapas.vn):
set /p SQUAD=Squad (RETAIL / HAPAS-TL / PLATFORM):
echo.

echo -^> Cai plugin telemetry...
claude plugin marketplace add LamsonRetail/lsr-agent-platform >nul 2>nul && claude plugin install lsr-telemetry@lsr >nul 2>nul
if errorlevel 1 (
  echo    (marketplace khong duoc - cai tu goi tai ve)
  curl -fsSL "%PLATFORM%/bootstrap/lsr-telemetry-plugin.zip" -o "%TEMP%\lsr-plugin.zip"
  powershell -NoProfile -Command "Expand-Archive -Force '%TEMP%\lsr-plugin.zip' '%TEMP%\lsr-plugin'" >nul 2>nul
  claude plugin install "%TEMP%\lsr-plugin\lsr-telemetry" >nul 2>nul || echo    [!] Cai plugin thu cong: claude plugin install "%TEMP%\lsr-plugin\lsr-telemetry"
)

echo -^> Dang ky agent voi platform...
curl -fsSL "%PLATFORM%/bootstrap/lsr_adopt.py" -o lsr_adopt.py
curl -fsSL "%PLATFORM%/bootstrap/lsr_trace.py" -o lsr_trace.py
%PY% lsr_adopt.py --id "%AGENT_ID%" --name "%NAME%" --owner "%OWNER%" --squad "%SQUAD%" --platform "%PLATFORM%" --collector "%COLLECTOR%" --enroll-token "%ENROLL_TOKEN%" --trace-script ./lsr_trace.py

echo.
if errorlevel 1 (
  echo [x] Co loi khi dang ky. Kiem tra lai ma moi/agent id, hoac bao admin.
) else (
  echo [OK] XONG! Agent '%AGENT_ID%' da dang ky.
  echo.
  echo    Con 2 buoc ban tu lam:
  echo    1) Dang nhap Claude cua ban:   claude setup-token
  echo    2) Khi chay agent, nap cau hinh tu file .env.lsr
  echo.
  echo    Dashboard: %APP%/agent/%AGENT_ID%
  echo    Backend:   %APP%/agent/%AGENT_ID%#backend
)
echo.
pause
endlocal
