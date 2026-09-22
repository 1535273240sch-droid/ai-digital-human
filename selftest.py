"""端到端自检：不启动服务，直接验证云端三个接口 + 本地组件是否就绪。

用法：
    D:\\AI\\venv\\Scripts\\python.exe D:\\AI\\selftest.py
"""

import os
import sys
import base64
import io
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "LiveTalking"))
os.chdir(os.path.join(ROOT, "LiveTalking"))

try:
    from dotenv import load_dotenv
    # 显式指定路径 —— load_dotenv() 默认从调用文件所在目录向上找，
    # 而本脚本在 D:\AI，.env 在 D:\AI\LiveTalking，默认找不到。
    load_dotenv(os.path.join(ROOT, "LiveTalking", ".env"), override=True)
except ImportError:
    pass

import requests

OK = "  [ok]"
BAD = "  [FAIL]"
results = []


def check(name, fn):
    try:
        detail = fn()
        results.append((True, name, detail))
        print(f"{OK} {name}" + (f" — {detail}" if detail else ""))
    except Exception as e:
        results.append((False, name, f"{type(e).__name__}: {e}"))
        print(f"{BAD} {name} — {type(e).__name__}: {e}")


def env_summary():
    key = os.getenv("STEPFUN_API_KEY", "")
    base = os.getenv("STEPFUN_API_BASE", "https://api.stepfun.com/v1")
    if not key:
        raise RuntimeError("STEPFUN_API_KEY 未设置（检查 LiveTalking/.env）")
    return f"base={base}, key=...{key[-6:]}"


def llm_test():
    from openai import OpenAI
    client = OpenAI(
        api_key=os.getenv("STEPFUN_API_KEY"),
        base_url=os.getenv("STEPFUN_API_BASE", "https://api.stepfun.com/v1"),
    )
    model = os.getenv("LLM_MODEL", "step-3.7-flash")
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "1024"))
    effort = os.getenv("LLM_REASONING_EFFORT", "low")
    t0 = time.perf_counter()
    r = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "用五个字打个招呼"}],
        max_tokens=max_tokens,
        reasoning_effort=effort,
    )
    dt = time.perf_counter() - t0
    text = (r.choices[0].message.content or "").strip()
    if not text:
        raise RuntimeError(
            f"内容为空，token 被推理阶段吃光（max_tokens={max_tokens}），调大 LLM_MAX_TOKENS"
        )
    return f"{model} {dt:.1f}s -> {text[:30]}"


def tts_test():
    base = os.getenv("STEPFUN_API_BASE", "https://api.stepfun.com/v1").rstrip("/")
    t0 = time.perf_counter()
    r = requests.post(
        f"{base}/audio/speech",
        headers={"Authorization": f"Bearer {os.getenv('STEPFUN_API_KEY')}"},
        json={
            "model": os.getenv("STEPFUN_TTS_MODEL", "stepaudio-2.5-tts"),
            "input": "自检通过，我是你的数字人助手。",
            "voice": os.getenv("STEPFUN_TTS_VOICE", "cixingnansheng"),
            "response_format": "wav",
            "sample_rate": 16000,
        },
        timeout=60,
    )
    dt = time.perf_counter() - t0
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    if r.content[:4] != b"RIFF":
        raise RuntimeError(f"返回的不是 WAV（前4字节 {r.content[:4]!r}）")
    return f"{len(r.content)//1024} KB, {dt:.1f}s"


def asr_test():
    """用 TTS 合成的音频回灌 ASR，形成闭环。"""
    import soundfile as sf
    base = os.getenv("STEPFUN_API_BASE", "https://api.stepfun.com/v1").rstrip("/")

    # 先合成一句
    t = requests.post(
        f"{base}/audio/speech",
        headers={"Authorization": f"Bearer {os.getenv('STEPFUN_API_KEY')}"},
        json={
            "model": os.getenv("STEPFUN_TTS_MODEL", "stepaudio-2.5-tts"),
            "input": "今天天气真不错。",
            "voice": os.getenv("STEPFUN_TTS_VOICE", "cixingnansheng"),
            "response_format": "wav",
            "sample_rate": 16000,
        },
        timeout=60,
    )
    t.raise_for_status()

    buf = io.BytesIO()
    data, sr = sf.read(io.BytesIO(t.content), dtype="int16")
    sf.write(buf, data, sr, format="WAV", subtype="PCM_16")

    t0 = time.perf_counter()
    r = requests.post(
        f"{base}/audio/asr/sse",
        headers={
            "Authorization": f"Bearer {os.getenv('STEPFUN_API_KEY')}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        json={
            "audio": {
                "data": base64.b64encode(buf.getvalue()).decode(),
                "input": {
                    "transcription": {
                        "language": "zh",
                        "model": os.getenv("STEPFUN_ASR_MODEL", "stepaudio-2.5-asr"),
                        "enable_itn": True,
                    },
                    "format": {"type": "wav"},
                },
            }
        },
        timeout=60,
    )
    dt = time.perf_counter() - t0
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")

    # text/event-stream 会被 requests 按 ISO-8859-1 解码，必须显式指定 UTF-8
    r.encoding = "utf-8"

    text = ""
    for line in r.text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        import json as _json
        body = line[5:].strip()
        if not body or body == "[DONE]":
            continue
        evt = _json.loads(body)
        if evt.get("type") == "transcript.text.done":
            text = (evt.get("text") or "").strip()
    if not text:
        raise RuntimeError("未收到识别结果")
    # 终端装不下中文，写文件供核对
    with io.open(os.path.join(ROOT, "asr_verify.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    good = "今天天气真不错" in text
    return f"{dt:.1f}s, {len(text)}字, 内容{'正确' if good else '异常(' + text + ')'}"


def torch_test():
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA 不可用")
    cap = torch.cuda.get_device_capability(0)
    name = torch.cuda.get_device_name(0)
    # 真正跑一次 kernel，确认 sm 架构有对应实现
    a = torch.randn(64, 64, device="cuda")
    b = torch.randn(64, 64, device="cuda")
    c = (a @ b).sum().item()
    return f"{name} sm_{cap[0]}{cap[1]}, torch {torch.__version__}, matmul ok ({c:.1f})"


def model_files_test():
    need = {
        r"models\wav2lip.pth": 100,
        r"models\hub\checkpoints\s3fd-619a316812.pth": 50,
    }
    missing = []
    for rel, min_mb in need.items():
        p = os.path.join(os.getcwd(), rel)
        if not os.path.exists(p):
            missing.append(f"{rel} 缺失")
        elif os.path.getsize(p) / 1e6 < min_mb:
            missing.append(f"{rel} 只有 {os.path.getsize(p)//1024//1024}MB，疑似下载不全")
    if missing:
        raise RuntimeError("; ".join(missing))
    return "wav2lip.pth + s3fd 就位"


def avatar_test():
    import glob
    ids = [
        d for d in os.listdir("./data/avatars")
        if os.path.isdir(os.path.join("./data/avatars", d))
    ]
    if not ids:
        return "尚无形象，需在 avatar.html 生成（不影响其它检查）"
    ready = []
    for a in ids:
        base = os.path.join("./data/avatars", a)
        if all(
            os.path.exists(os.path.join(base, x))
            for x in ("coords.pkl",)
        ) and glob.glob(os.path.join(base, "full_imgs", "*")):
            ready.append(a)
    return f"已生成: {ready}" if ready else f"目录有 {ids} 但未生成完整，需重新生成"


print("=" * 62)
print("  AI 数字人 自检")
print("=" * 62)
print()

# 终端默认编码可能装不下中文，切到 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

check("配置 (.env)", env_summary)
check("依赖: torch + GPU", torch_test)
check("模型文件", model_files_test)
check("云端 LLM", llm_test)
check("云端 TTS", tts_test)
check("云端 ASR (闭环)", asr_test)
check("数字人形象", avatar_test)

print()
passed = sum(1 for ok, _, _ in results if ok)
print(f"结果: {passed}/{len(results)} 项通过")
if passed < len(results):
    print("\n未通过项:")
    for ok, name, detail in results:
        if not ok:
            print(f"  - {name}: {detail}")
    sys.exit(1)
print("全部通过，可以运行 start.bat 启动服务")
