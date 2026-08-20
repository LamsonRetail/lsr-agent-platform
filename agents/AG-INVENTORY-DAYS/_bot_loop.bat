@echo off
REM ============================================================
REM  File noi bo — KHONG bam truc tiep. Dung bot_nen_START.vbs.
REM  Chay bot va tu khoi dong lai neu no chet.
REM ============================================================
REM DE TRONG = phuc vu MOI nhom bot duoc add vao, tu bat nhom moi sau ~1 phut.
REM Dien 1 chat_id = ghim cung vao nhom do, nhom khac se KHONG duoc nghe.
REM   oc_2659fb0822ebf7de6291f11c1f5ce37c = KHHH noi bo
REM   oc_618134792f49a95d2f455314261c0215 = test AI
REM   oc_e521377bc4d63c0516f825bb79eab59f = Sharing ai thich hoc cai moi
set CHAT_ID=
set DRY_RUN=false
REM 1 = doc ton kho tu Lark Base (so lieu luon moi)
set USE_BASE=1

set ROOT=%~dp0
if exist "%ROOT%bot.stop" del "%ROOT%bot.stop"

echo. >> "%ROOT%bot_log.txt"
echo ==== BAT DAU %DATE% %TIME% (chay nen) ==== >> "%ROOT%bot_log.txt"

:loop
if exist "%ROOT%bot.stop" goto end
cd /d "%ROOT%src"
REM CHAT_ID de trong -> khong truyen --chat-id -> bot tu quet moi nhom.
set ARGS=
if not "%CHAT_ID%"=="" set ARGS=--chat-id %CHAT_ID%
if "%USE_BASE%"=="1" set ARGS=%ARGS% --base
python -u bot_poll.py %ARGS% >> "%ROOT%bot_log.txt" 2>&1
if exist "%ROOT%bot.stop" goto end
echo [%DATE% %TIME%] bot thoat bat thuong — khoi dong lai sau 10s >> "%ROOT%bot_log.txt"
ping -n 11 127.0.0.1 >nul
goto loop

:end
echo [%DATE% %TIME%] da dung theo yeu cau >> "%ROOT%bot_log.txt"
del "%ROOT%bot.stop" >nul 2>&1
