"""从无框客户端页面读取当前 sessionid（走 CDP）。"""
import asyncio
import json
import urllib.request

import websockets


async def get_page_sessionid_async(port: int = 9222):
    targets = json.loads(
        urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=5).read()
    )
    pages = [t for t in targets if t.get("type") == "page"]
    if not pages:
        return None
    tgt = next((t for t in pages if "realtime.html" in (t.get("url") or "")), pages[0])
    return await _eval(tgt["webSocketDebuggerUrl"], "String(sessionid || '')")


def get_page_sessionid(port: int = 9222):
    return asyncio.run(get_page_sessionid_async(port))


async def _eval(ws_url, expr):
    async with websockets.connect(ws_url, max_size=2 ** 22) as ws:
        await ws.send(json.dumps({
            "id": 1, "method": "Runtime.evaluate",
            "params": {"expression": expr, "awaitPromise": True, "returnByValue": True},
        }))
        while True:
            msg = json.loads(await ws.recv())
            if msg.get("id") == 1:
                res = msg.get("result", {}).get("result", {})
                return res.get("value")


if __name__ == "__main__":
    print(get_page_sessionid())
