"""用 aiohttp 客户端验证 /api/asr（贴近浏览器行为）。"""

import asyncio
import io
import json
import os
import time

import aiohttp
import requests
import soundfile as sf
from dotenv import load_dotenv

load_dotenv(r"D:\AI\LiveTalking\.env", override=True)


async def main():
    sf_base = os.getenv("STEPFUN_API_BASE").rstrip("/")
    key = os.getenv("STEPFUN_API_KEY")

    # 造一段"用户说话"的音频
    t = requests.post(
        sf_base + "/audio/speech",
        headers={"Authorization": "Bearer " + key},
        json={
            "model": "stepaudio-2.5-tts",
            "input": "今天天气怎么样？",
            "voice": "cixingnansheng",
            "response_format": "wav",
            "sample_rate": 16000,
        },
        timeout=60,
    )
    t.raise_for_status()
    data, sr = sf.read(io.BytesIO(t.content), dtype="int16")
    if data.ndim > 1:
        data = data[:, 0]
    pcm = data.tobytes()
    print(f"[1] 音频: {len(pcm)} bytes, {sr}Hz, {len(pcm)/2/sr:.2f}s")

    async with aiohttp.ClientSession() as sess:
        async with sess.ws_connect("http://127.0.0.1:8010/api/asr") as ws:
            print("[2] websocket 已连接")
            await ws.send_str(json.dumps({
                "chunk_size": [5, 10, 5], "wav_name": "h5",
                "is_speaking": True, "mode": "2pass", "itn": True,
            }))

            CHUNK = 960
            for i in range(0, len(pcm), CHUNK):
                await ws.send_bytes(pcm[i:i + CHUNK])
                await asyncio.sleep(0.005)

            t0 = time.perf_counter()
            await ws.send_str(json.dumps({"is_speaking": False, "mode": "2pass"}))
            print("[3] 推送完毕，等待识别...")

            msg = await asyncio.wait_for(ws.receive(), timeout=60)
            lat = time.perf_counter() - t0

            if msg.type == aiohttp.WSMsgType.TEXT:
                resp = json.loads(msg.data)
                text = resp.get("text", "")
                print(f"[4] 识别结果 ({lat:.2f}s): {text!r}")
                if not text:
                    print("[FAIL] 识别为空")
                    return 1
                if "天气" not in text:
                    print(f"[WARN] 结果与预期不符（预期含'天气'）")
                print()
                print("[OK] 麦克风 -> 云端ASR 链路正常")
                print("     (浏览器里 web/asr/main.js 收到文本后会自动 POST /human 驱动数字人)")
                return 0
            print(f"[FAIL] 非文本消息: {msg.type}")
            return 1


raise SystemExit(asyncio.run(main()))
