@echo off
chcp 65001 >nul
setlocal

REM ─────────────────────────────────────────────────────────────
REM  AI 数字人 — 启动服务（全云端版）
REM  StepFun 云端：语音识别 + 大模型 + 语音合成（含音色复刻）
REM  本地：仅 wav2lip256 口型推理（约 1.3GB 显存）
REM
REM  本窗口就是运行日志，出错时看这里。
REM  想同时存一份日志：start.bat > server.log 2>&1
REM ─────────────────────────────────────────────────────────────

set ROOT=D:\AI
set PY=%ROOT%\venv\Scripts\python.exe
set LT=%ROOT%\LiveTalking

if not exist "%PY%" (
    echo [错误] 找不到 Python: %PY%
    echo        请先运行 install.bat
    pause
    exit /b 1
)

REM 默认形象与音色，可用环境变量覆盖
if "%AVATAR_ID%"=="" set AVATAR_ID=wav2lip256_522
if "%VOICE_ID%"==""  set VOICE_ID=linjiajiejie

cd /d "%LT%"

echo ============================================================
echo   AI 数字人服务启动中
echo.
echo   主界面（语音球 + 对话）: http://localhost:8010/realtime.html
echo   生成自己的形象:         http://localhost:8010/avatar.html
echo.
echo   当前形象: %AVATAR_ID%
echo   当前音色: %VOICE_ID%
echo ============================================================
echo.
echo   下方滚动的是运行日志；关闭本窗口即停止服务
echo.
echo   注：界面右下角可能盖住了源视频自带的水印。若换了无水印的视频，
echo       可删掉 realtime.html 里的 ^<div id="wmMask"^> 那一行。
echo.

"%PY%" -X utf8 -u app.py --transport webrtc --model wav2lip --avatar_id "%AVATAR_ID%" --tts stepfun --REF_FILE "%VOICE_ID%" --llm_provider stepfun --stun "stun:stun.l.google.com:19302" --listenport 8010

echo.
echo [服务已停止]
pause
