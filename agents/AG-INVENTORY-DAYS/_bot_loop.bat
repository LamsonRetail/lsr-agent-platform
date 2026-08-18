@echo off
REM ============================================================
REM  File noi bo — KHONG bam truc tiep. Dung bot_nen_START.vbs.
REM  Chay bot va tu khoi dong lai neu no chet.
REM ============================================================
set CHAT_ID=oc_618134792f49a95d2f455314261c0215
set DRY_RUN=false

set ROOT=%~dp0
if exist "%ROOT%bot.stop" del "%ROOT%bot.stop"

echo. >> "%ROOT%bot_log.txt"
echo ==== BAT DAU %DATE% %TIME% (chay nen) ==== >> "%ROOT%bot_log.txt"

:loop
if exist "%ROOT%bot.stop" goto end
cd /d "%ROOT%src"
python -u bot_poll.py --chat-id %CHAT_ID% >> "%ROOT%bot_log.txt" 2>&1
if exist "%ROOT%bot.stop" goto end
echo [%DATE% %TIME%] bot thoat bat thuong — khoi dong lai sau 10s >> "%ROOT%bot_log.txt"
timeout /t 10 /nobreak >nul
goto loop

:end
echo [%DATE% %TIME%] da dung theo yeu cau >> "%ROOT%bot_log.txt"
del "%ROOT%bot.stop" >nul 2>&1
