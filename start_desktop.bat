@echo off
chcp 65001 >nul
REM XiaoYa - frameless desktop client launcher
REM 1) re-apply pywebview patch (idempotent)  2) start server if needed  3) show frameless window
cd /d D:\AI
"D:\AI\venv\Scripts\python.exe" "D:\AI\tools\apply_webview_patch.py" >nul 2>&1
start "" "D:\AI\venv\Scripts\pythonw.exe" "D:\AI\desktop_client.py"
exit /b 0
