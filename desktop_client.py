"""小雅 · 桌面无框悬浮客户端

- 无边框窗口加载本地服务界面（realtime.html）
- 顶部栏可拖动，右侧有 置顶 / 最小化 / 关闭 按钮
- 默认窗口置顶（用原生 SetWindowPos 实现，避开 pywebview 的置顶递归 bug）
- 服务未启动时自动拉起 start.bat 并等待就绪
- --selfcheck / --debug 时开启 WebView2 调试端口 9222，便于外部自检
"""
import ctypes
import os
import socket
import subprocess
import sys
import time
import urllib.request

import webview

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 8010
URL = f"http://127.0.0.1:{PORT}/realtime.html?client=1"
SERVER_BAT = os.path.join(ROOT, "start.bat")

WIN_W, WIN_H = 1000, 680
HWND_TOPMOST = -1
SWP_NOMOVE, SWP_NOSIZE = 0x0002, 0x0001


def port_open(port=PORT, timeout=0.4):
    with socket.socket() as s:
        s.settimeout(timeout)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_ready(timeout=150):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if port_open():
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{PORT}/realtime.html", timeout=2
                ) as r:
                    if r.status == 200:
                        return True
            except Exception:
                pass
        time.sleep(1.5)
    return False


def start_server():
    subprocess.Popen(
        ["cmd", "/c", SERVER_BAT],
        cwd=ROOT,
        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
    )


class Api:
    def __init__(self):
        self.window = None
        self.on_top = True
        self.hwnd = None

    def close(self):
        self.window.destroy()

    def minimize(self):
        self.window.minimize()

    def _set_topmost(self, on):
        try:
            if self.hwnd is None:
                # pywebview: window.native 是 WinForms 窗体，Handle 即 HWND
                self.hwnd = int(self.window.native.Handle.ToInt64())
            ctypes.windll.user32.SetWindowPos(
                self.hwnd, HWND_TOPMOST if on else -2,
                0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE,
            )
        except Exception as e:
            print("[置顶] 设置失败:", e)

    def toggle_top(self):
        self.on_top = not self.on_top
        self._set_topmost(self.on_top)
        return self.on_top


def main():
    debug = ("--selfcheck" in sys.argv) or ("--debug" in sys.argv)
    if debug:
        webview.settings["REMOTE_DEBUGGING_PORT"] = 9222

    if not port_open():
        print("[客户端] 服务未运行，正在启动（首次加载模型约 30 秒）…")
        start_server()
        if not wait_ready():
            print("[客户端] 服务启动超时，请查看服务窗口里的日志。")
            return

    api = Api()
    api.window = webview.create_window(
        "小雅",
        URL,
        width=WIN_W,
        height=WIN_H,
        frameless=True,
        easy_drag=False,
        background_color="#0d0d0f",
        js_api=api,
    )

    def after_start():
        time.sleep(4)
        api._set_topmost(True)   # 建立窗口后再置顶，避开 pywebview 内部路径
        print("[客户端] 已置顶。调试端口:", 9222 if debug else "关闭")

    webview.start(func=after_start)


if __name__ == "__main__":
    main()
