"""
AI 数字人 — 启动器（会被 PyInstaller 打包成 AI数字人.exe）

职责：
  1. 首次运行时检查 Python / 依赖 / 模型，缺什么装什么
  2. 拉起数字人服务
  3. 用 Edge 的 --app 模式打开独立窗口（无地址栏、无标签页）

用户视角：双击 exe → 等一会 → 出现数字人窗口。
安装过程有进度提示，不需要看命令行。
"""

import os
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.request
from tkinter import messagebox, ttk

# ── 路径 ──────────────────────────────────────────────────────
# PyInstaller --onefile 会把 --add-data 解包到临时目录（sys._MEIPASS），
# 但用户数据（LiveTalking、venv、.env）必须放在 exe 旁边。
# 所以：打包进去的资产从 _MEIPASS 找，用户数据从 exe 目录找。
if getattr(sys, "frozen", False):
    HERE = os.path.dirname(sys.executable)
    BUNDLE = getattr(sys, "_MEIPASS", HERE)
else:
    HERE = os.path.dirname(os.path.abspath(__file__))
    BUNDLE = HERE

LT = os.path.join(HERE, "LiveTalking")
VENV_PY = os.path.join(HERE, "venv", "Scripts", "python.exe")
SYS_PY = os.path.join(HERE, "Python312", "python.exe")
ENV_FILE = os.path.join(LT, ".env")
CHECK_URL = "http://127.0.0.1:8010/api/admin/config"
PAGE_URL = "http://127.0.0.1:8010/realtime.html"


def find_asset(name):
    """按 exe 目录 → 打包临时目录 → LiveTalking 的顺序找文件。"""
    for base in (HERE, BUNDLE, LT):
        p = os.path.join(base, name)
        if os.path.exists(p):
            return p
    return None

BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ── 进度窗口 ─────────────────────────────────────────────────
class Splash:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AI 数字人")
        self.root.geometry("460x180")
        self.root.resizable(False, False)
        self.root.configure(bg="#0d0d0f")

        tk.Label(self.root, text="AI 数字人", bg="#0d0d0f", fg="#f0b429",
                 font=("Microsoft YaHei UI", 18, "bold")).pack(pady=(28, 6))

        self.msg = tk.Label(self.root, text="正在检查环境…", bg="#0d0d0f",
                            fg="#cccccc", font=("Microsoft YaHei UI", 10))
        self.msg.pack()

        style = ttk.Style()
        style.theme_use("default")
        style.configure("D.Horizontal.TProgressbar", troughcolor="#1e1e22",
                        background="#f0b429", borderwidth=0, thickness=6)
        self.bar = ttk.Progressbar(self.root, length=380, mode="determinate",
                                   style="D.Horizontal.TProgressbar", maximum=100)
        self.bar.pack(pady=20)

        self.root.update()

    def set(self, pct, text=None):
        self.bar["value"] = pct
        if text:
            self.msg.config(text=text)
        self.root.update()

    def close(self):
        try:
            self.root.destroy()
        except Exception:
            pass


# ── 环境检查 ─────────────────────────────────────────────────
def server_ready(timeout=1.0):
    try:
        with urllib.request.urlopen(CHECK_URL, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def python_ok():
    for p in (VENV_PY, SYS_PY):
        if os.path.exists(p):
            try:
                subprocess.run([p, "-c", "import sys"], check=True,
                               creationflags=NO_WINDOW, timeout=20)
                return p
            except Exception:
                pass
    return None


def deps_ok(py):
    try:
        r = subprocess.run(
            [py, "-c", "import torch,aiortc,flask;print(torch.cuda.is_available())"],
            capture_output=True, text=True, creationflags=NO_WINDOW, timeout=180,
        )
        return r.returncode == 0 and "True" in r.stdout
    except Exception:
        return False


def run_install(py, splash):
    """跑 install.bat，实时更新进度。"""
    splash.set(20, "正在安装依赖（首次约 10 分钟）…")
    bat = find_asset("install.bat")
    if not bat:
        return False
    p = subprocess.Popen(["cmd.exe", "/c", bat], cwd=os.path.dirname(bat),
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         creationflags=NO_WINDOW, text=True, errors="ignore")
    pct = 20
    for _ in p.stdout:
        pct = min(pct + 0.25, 92)
        splash.set(pct, "正在安装依赖（首次约 10 分钟）…")
    p.wait()
    return p.returncode == 0


def start_server(splash):
    splash.set(94, "正在启动数字人服务…")
    bat = find_asset("start.bat")
    if not bat:
        return False
    subprocess.Popen(["cmd.exe", "/c", bat], cwd=os.path.dirname(bat),
                     creationflags=NO_WINDOW)
    for _ in range(120):
        time.sleep(0.5)
        if server_ready():
            return True
    return False


def source_ok():
    """确认 LiveTalking 源码在位。"""
    return os.path.isdir(LT) and os.path.exists(os.path.join(LT, "app.py"))


def open_window():
    for exe in BROWSERS:
        if os.path.exists(exe):
            subprocess.Popen([exe, "--app=" + PAGE_URL,
                              "--window-size=1280,760",
                              "--window-position=120,60"])
            return True
    os.startfile(PAGE_URL)
    return True


def ensure_env(splash):
    """没有 .env 就从模板生成，并提示填 key。"""
    if os.path.exists(ENV_FILE):
        return True
    tpl = find_asset(".env.example")
    if not tpl:
        return True
    import shutil
    os.makedirs(LT, exist_ok=True)
    shutil.copy2(tpl, ENV_FILE)
    splash.set(15, "已生成 .env，请填入 StepFun API Key")
    messagebox.showinfo(
        "需要配置",
        "已生成配置文件：\n%s\n\n"
        "请填入你的 StepFun API Key 后重新运行。\n\n"
        "获取地址：https://platform.stepfun.com/interface-key" % ENV_FILE,
    )
    return False


def main():
    splash = Splash()
    try:
        splash.set(5, "正在检查环境…")

        # 已经有服务在跑就直接开窗口
        if server_ready():
            splash.set(100, "服务已就绪")
            time.sleep(0.3)
            splash.close()
            open_window()
            return

        if not source_ok():
            splash.set(100, "缺少程序文件")
            messagebox.showerror(
                "缺少程序文件",
                "没找到 LiveTalking 目录。\n\n"
                "请把本程序放在解压后的完整目录里运行，\n"
                "也就是和 LiveTalking 文件夹、start.bat 放在一起。\n\n"
                "当前目录：%s" % HERE,
            )
            splash.close()
            return

        if not ensure_env(splash):
            splash.close()
            return

        py = python_ok()
        if not py:
            splash.set(100, "未找到 Python 3.12")
            messagebox.showerror(
                "缺少 Python",
                "没有找到 Python 环境。\n\n"
                "请先安装 Python 3.12（勾选 Add to PATH），\n"
                "然后重新运行本程序。\n\n"
                "下载：https://www.python.org/downloads/",
            )
            splash.close()
            return

        splash.set(15, "正在检查依赖…")
        if not deps_ok(py):
            if not run_install(py, splash):
                messagebox.showerror(
                    "安装失败", "依赖安装未成功，请查看 install.bat 的输出。")
                splash.close()
                return

        if not start_server(splash):
            messagebox.showerror(
                "启动失败",
                "服务未能启动。常见原因：\n"
                "• .env 里的 API Key 没填\n"
                "• 显卡驱动过旧\n"
                "• 端口 8010 被占用",
            )
            splash.close()
            return

        splash.set(100, "启动完成")
        time.sleep(0.4)
        splash.close()
        open_window()

    except Exception as e:
        try:
            messagebox.showerror("出错了", str(e))
        except Exception:
            print(e)
        splash.close()


if __name__ == "__main__":
    main()
