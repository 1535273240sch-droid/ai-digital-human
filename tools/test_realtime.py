"""端到端测试实时语音链路（不需要真人说话）。

流程：连上 /api/realtime → 等 ready → 推 16k PCM16 用户语音 → 收识别/回复，
统计「说完 → 她开口」的延迟。
"""
import asyncio
import io
import json
import time
import urllib.request
from stepfun_env import read_key as _read_key

import soundfile as sf
import websockets

from cdp_util import get_page_sessionid_async

KEY = _read_key()
BASE = "https://api.stepfun.com/step_plan/v1"
QUESTION = "小雅，你能听到我说话吗？简单回我一句"


def make_user_audio() -> bytes:
    body = json.dumps({
        "model": "stepaudio-2.5-tts", "input": QUESTION, "voice": "linjiajiejie",
        "response_format": "wav", "sample_rate": 16000, "speed": 1.0,
    }).encode()
    req = urllib.request.Request(BASE + "/audio/speech", data=body, headers={
        "Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    data, sr = sf.read(io.BytesIO(raw), dtype="int16")
    print(f"[准备] 用户语音 {len(data)} 样本 @ {sr}Hz = {len(data)/sr:.2f}s")
    return data.tobytes()


async def main():
    sid = await get_page_sessionid_async()
    if not sid:
        print("拿不到 sessionid（客户端页面没连上？）")
        return
    print("[会话] sessionid =", sid)

    url = f"ws://127.0.0.1:8010/api/realtime?sessionid={sid}"
    async with websockets.connect(url, max_size=2 ** 23) as ws:
        t0 = time.perf_counter()
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=30)
            if isinstance(raw, bytes):
                continue
            m = json.loads(raw)
            print(f"[{time.perf_counter()-t0:5.2f}s] {json.dumps(m, ensure_ascii=False)[:120]}")
            if m.get("type") == "ready":
                break

        pcm = make_user_audio()
        chunk = 3200
        for i in range(0, len(pcm), chunk):
            await ws.send(pcm[i:i + chunk])
            await asyncio.sleep(0.1)
        silence = b"\x00" * 48000
        for i in range(0, len(silence), chunk):
            await ws.send(silence[i:i + chunk])
            await asyncio.sleep(0.1)
        t_sent = time.perf_counter()
        print(f"[发送] 推送完成（音频 {len(pcm)/32000:.2f}s + 静音 1.5s），等待回应…")

        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=40)
                if isinstance(raw, bytes):
                    continue
                m = json.loads(raw)
                t = m.get("type")
                dt = time.perf_counter() - t_sent
                if t == "text":
                    print(f"[{dt:5.2f}s] {m.get('who')}: {m.get('text')}")
                    if m.get("who") not in ("user", "你"):
                        print(f"==> 实时延迟（说完 → 她开口）：{dt:.2f}s")
                        break
                else:
                    print(f"[{dt:5.2f}s] {json.dumps(m, ensure_ascii=False)[:120]}")
        except asyncio.TimeoutError:
            print("等待超时（40s）")
        finally:
            try:
                await ws.send(json.dumps({"type": "close"}))
            except Exception:
                pass


asyncio.run(main())




