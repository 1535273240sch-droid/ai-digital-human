"""实测 StepFun 各模型延迟，挑最快的对话/合成组合。"""
import json
import os
import time
import urllib.request
from stepfun_env import read_key as _read_key

KEY = _read_key()
BASE = "https://api.stepfun.com/step_plan/v1"
HEAD = {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}


def post(path, body, stream=False, timeout=90):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers=HEAD)
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    return time.perf_counter() - t0, data


print("=== LLM 首字延迟（流式首块） ===")
for model in ["step-3.5-flash", "step-3.5-flash-2603", "step-router-v1", "step-5-preview", "step-3.7-flash"]:
    body = {
        "model": model, "stream": True, "max_tokens": 120,
        "reasoning_effort": "low",
        "messages": [{"role": "user", "content": "用一句话打个招呼"}],
    }
    try:
        req = urllib.request.Request(BASE + "/chat/completions", data=json.dumps(body).encode(), headers=HEAD)
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=60) as r:
            for line in r:
                if b"data:" in line and b'"content"' in line and b'"content":null' not in line:
                    break
        print(f"  {model:22s} first:{time.perf_counter()-t0:.2f}s")
    except Exception as e:
        print(f"  {model:22s} FAIL {e}")

print("=== TTS 合成延迟 ===")
for model in ["stepaudio-2.5-tts", "stepaudio-3-tts"]:
    try:
        dt, data = post("/audio/speech", {
            "model": model, "input": "你好呀，很高兴见到你。", "voice": "linjiajiejie",
            "response_format": "wav", "sample_rate": 16000, "speed": 1.0,
        }, timeout=90)
        print(f"  {model:22s} {dt:.2f}s  {len(data)} bytes")
    except Exception as e:
        print(f"  {model:22s} FAIL {e}")


