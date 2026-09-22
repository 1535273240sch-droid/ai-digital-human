@echo off
chcp 65001 >nul
REM ─────────────────────────────────────────────────────────────
REM  AI 数字人 — 独立窗口启动（无地址栏、无标签页，像独立软件）
REM  首次启动要加载模型，约 30 秒
REM ─────────────────────────────────────────────────────────────

set "BROWSER_EXE="
if exist "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" set "BROWSER_EXE=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if "%BROWSER_EXE%"=="" if exist "C:\Program Files\Microsoft\Edge\Application\msedge.exe" set "BROWSER_EXE=C:\Program Files\Microsoft\Edge\Application\msedge.exe"
if "%BROWSER_EXE%"=="" if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" set "BROWSER_EXE=C:\Program Files\Google\Chrome\Application\chrome.exe"
if "%BROWSER_EXE%"=="" if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" set "BROWSER_EXE=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

REM 服务没起就拉起（start.bat 会开一个最小化窗口跑服务，日志在里面）
netstat -ano | findstr ":8010 " >nul
if %errorlevel% neq 0 (
    echo [客户端] 服务未运行，正在启动...
    start "AI数字人服务" /min cmd /c "D:\AI\start.bat"
    echo [客户端] 等待服务就绪（首次加载模型约 30 秒）...
    timeout /t 25 /nobreak >nul
)

REM --app 模式：去掉地址栏和标签页，视觉上就是独立软件
if not "%BROWSER_EXE%"=="" (
    start "" "%BROWSER_EXE%" --app="http://127.0.0.1:8010/realtime.html" --window-size=1280,760 --window-position=120,60
) else (
    echo [客户端] 未找到 Edge/Chrome，用默认浏览器打开
    start "" "http://127.0.0.1:8010/realtime.html"
)
