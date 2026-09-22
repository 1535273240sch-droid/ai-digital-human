@echo off
chcp 65001 >nul
setlocal

REM ─────────────────────────────────────────────────────────────
REM  AI 数字人 — 依赖安装（只需运行一次）
REM  全部装到 D:\AI（C 盘会还原，所以不装系统盘）
REM ─────────────────────────────────────────────────────────────

set ROOT=D:\AI
set LT=%ROOT%\LiveTalking
set PY=%ROOT%\venv\Scripts\python.exe
set DL=%ROOT%\downloads
set PROXY=http://127.0.0.1:7897

if not exist "%PY%" (
    echo [错误] 找不到虚拟环境: %PY%
    pause
    exit /b 1
)

cd /d "%LT%"

echo === [1/4] 安装 PyTorch 2.9.1 + CUDA 12.8 ===
echo     (CUDA 12.8 是 RTX 50 系 Blackwell 的必要条件)
"%PY%" -m pip install "%DL%\torch-2.9.1+cu128-cp312-cp312-win_amd64.whl"
if errorlevel 1 goto fail

echo.
echo === [2/4] 安装 torchvision / torchaudio ===
"%PY%" -m pip install "%DL%\torchvision-0.24.1+cu128-cp312-cp312-win_amd64.whl" "%DL%\torchaudio-2.9.1+cu128-cp312-cp312-win_amd64.whl"
if errorlevel 1 goto fail

echo.
echo === [3/4] 安装 LiveTalking 依赖 ===
"%PY%" -m pip install -r requirements.txt --proxy %PROXY%
if errorlevel 1 goto fail

echo.
echo === [4/4] 验证 GPU ===
"%PY%" -c "import torch; print('torch', torch.__version__); print('cuda available:', torch.cuda.is_available()); print('device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A'); print('compute capability:', torch.cuda.get_device_capability(0) if torch.cuda.is_available() else 'N/A')"

echo.
echo ============================================================
echo   安装完成，双击 start.bat 启动服务
echo ============================================================
pause
exit /b 0

:fail
echo.
echo [错误] 安装失败，请检查上方输出
pause
exit /b 1
