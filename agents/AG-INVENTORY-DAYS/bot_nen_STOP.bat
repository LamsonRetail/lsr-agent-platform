@echo off
REM  Dung bot dang chay nen.
echo stop > "%~dp0bot.stop"
powershell -NoProfile -Command ^
  "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*bot_poll.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" 2>nul
timeout /t 3 /nobreak >nul
powershell -NoProfile -Command ^
  "Get-CimInstance Win32_Process -Filter \"Name='cmd.exe'\" | Where-Object { $_.CommandLine -like '*_bot_loop.bat*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" 2>nul
echo Da dung bot.
timeout /t 2 /nobreak >nul
