"""给 pywebview 的 WebView2 后端打本地补丁（幂等，可重复运行）。

补丁内容（AdditionalBrowserArguments）：
  --no-proxy-server                      绕开系统代理，避免本机 8010 请求被代理挂起
  --autoplay-policy=no-user-gesture-required  允许自动播放她的声音
  --use-fake-ui-for-media-stream         免弹窗授予麦克风权限

重装/升级 pywebview 后重新运行本脚本即可恢复。
"""
import io
import os
import sys

try:
    import webview
except ImportError:
    print("[patch] pywebview 未安装，跳过")
    sys.exit(0)

target = os.path.join(os.path.dirname(webview.__file__), "platforms", "edgechromium.py")
src = io.open(target, encoding="utf-8").read()

NEEDLE = "props.AdditionalBrowserArguments = '--disable-features=ElasticOverscroll'"
BLOCK = NEEDLE + """
        # 小雅本地补丁（由 tools/apply_webview_patch.py 写入）：
        #   1) --no-proxy-server        客户端只访问本机，绕开系统代理避免请求挂起
        #   2) 自动播放声音 + 免弹窗授予麦克风权限
        props.AdditionalBrowserArguments += (
            ' --no-proxy-server'
            ' --autoplay-policy=no-user-gesture-required'
            ' --use-fake-ui-for-media-stream'
        )"""

if "--no-proxy-server" in src and "--use-fake-ui-for-media-stream" in src:
    print("[patch] 补丁已存在，无需重复写入")
    sys.exit(0)

if NEEDLE not in src:
    print("[patch] 未找到目标行，pywebview 版本可能已变化：", target)
    sys.exit(1)

io.open(target, "w", encoding="utf-8").write(src.replace(NEEDLE, BLOCK, 1))
print("[patch] 已写入补丁：", target)
