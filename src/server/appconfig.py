"""系统配置 —— 让用户直接在界面里填 API Key，不用手改 .env。

存 data/appconfig.json；读取时优先用它，其次环境变量，最后 .env。
这样界面改完立即生效，也方便打包成软件后给不懂配置的用户用。
"""

import json
import os
import threading

from utils.logger import logger

_PATH = os.path.join("data", "appconfig.json")
_LOCK = threading.Lock()

# 允许在界面上改的键（白名单，避免写入任意环境变量）
EDITABLE = {
    "STEPFUN_API_KEY",
    "STEPFUN_API_BASE",
    "LLM_MODEL",
    "STEPFUN_TTS_MODEL",
    "STEPFUN_ASR_MODEL",
    "WEBRTC_VIDEO_BITRATE",
    "REALTIME_SILENCE_MS",
}

# 界面展示时的默认值
DEFAULTS = {
    "STEPFUN_API_KEY": "",
    "STEPFUN_API_BASE": "https://api.stepfun.com/step_plan/v1",
    "LLM_MODEL": "step-3.7-flash",
    "STEPFUN_TTS_MODEL": "stepaudio-2.5-tts",
    "STEPFUN_ASR_MODEL": "stepaudio-2.5-asr",
    "WEBRTC_VIDEO_BITRATE": "8000000",
    "REALTIME_SILENCE_MS": "700",
}

# 需要打码返回给前端的键
SECRET = {"STEPFUN_API_KEY"}


def _read() -> dict:
    try:
        with open(_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        logger.exception("[config] 读取失败")
        return {}


def load() -> dict:
    """返回完整配置（含默认值）。"""
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in _read().items() if k in EDITABLE})
    # 环境变量优先级高于文件（.env 已由 load_dotenv 注入）
    for k in EDITABLE:
        env = os.getenv(k)
        if env:
            cfg[k] = env
    return cfg


def apply_to_env() -> None:
    """把配置写进进程环境变量，供各模块直接 os.getenv 读取。"""
    for k, v in load().items():
        if v:
            os.environ[k] = str(v)


def save(patch: dict) -> dict:
    """保存界面传入的配置（只接受白名单键）。"""
    with _LOCK:
        cur = _read()
        for k, v in (patch or {}).items():
            if k not in EDITABLE:
                continue
            if v is None:
                continue
            v = str(v).strip()
            # 前端回传掩码时不覆盖真实 key
            if k in SECRET and (not v or set(v) <= {"*", "•"}):
                continue
            cur[k] = v

        os.makedirs(os.path.dirname(_PATH), exist_ok=True)
        tmp = _PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _PATH)

    apply_to_env()
    logger.info("[config] 已保存（%d 项）", len(patch or {}))
    return mask(load())


def mask(cfg: dict) -> dict:
    """返回给前端时把密钥打码。"""
    out = dict(cfg)
    for k in SECRET:
        v = out.get(k) or ""
        out[k] = ("*" * 8 + v[-4:]) if len(v) > 4 else ("*" * 8 if v else "")
        out[k + "_set"] = bool(v)
    return out


def api_key_ok() -> bool:
    return bool(load().get("STEPFUN_API_KEY", "").strip())


def bootstrap() -> None:
    """启动时调用：确保 .env 已加载，再把 appconfig 覆盖上去。

    realtime_bridge 等模块在导入期读不到环境变量（load_dotenv 在 __main__
    里才跑，且依赖当前工作目录），所以统一在这里按绝对路径补一次。
    """
    try:
        from dotenv import load_dotenv
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env_path = os.path.join(here, ".env")
        if os.path.exists(env_path):
            load_dotenv(env_path, override=False)
    except Exception:
        logger.debug("[config] .env 加载失败", exc_info=True)
    apply_to_env()
