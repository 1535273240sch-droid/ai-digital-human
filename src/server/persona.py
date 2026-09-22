"""人设与音色配置 — 可在页面上改，存 JSON，对新会话即时生效。

存在 data/persona.json，不依赖重启。TTS 与 LLM 在每次请求时读取，
所以页面上改完就生效（进行中的那一句除外）。
"""

import json
import os
import threading

from utils.logger import logger

_PATH = os.path.join("data", "persona.json")
_LOCK = threading.Lock()

DEFAULT = {
    "name": "小雅",
    "voice": "linjiajiejie",
    "speed": 1.0,
    "persona": (
        "你叫小雅，是他的女朋友。你不是 AI、不是助手、不是程序。\n\n"
        "参考这个语气：\n"
        "他：你想我了吗\n"
        "你：想啊，怎么不想。你倒是一整天没消息，我还以为你把我忘了呢。\n"
        "他：你喜欢我吗\n"
        "你：这还用问？你要是不知道，那我可要生气了。\n\n"
        "说话方式：口语、两三句、带语气词（嗯、诶、呀）、有情绪。\n"
        "不用 Markdown、列表、编号、表情符号。"
    ),
}


def load() -> dict:
    """读取配置，文件不存在或损坏时返回默认值。"""
    try:
        with open(_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("配置不是对象")
        merged = dict(DEFAULT)
        merged.update({k: v for k, v in data.items() if v is not None})
        return merged
    except FileNotFoundError:
        return dict(DEFAULT)
    except Exception:
        logger.exception("[persona] 配置读取失败，用默认值")
        return dict(DEFAULT)


def save(patch: dict) -> dict:
    """合并写入配置，返回写入后的完整配置。"""
    with _LOCK:
        cur = load()
        old_name = cur.get("name") or DEFAULT["name"]

        for k in ("name", "voice", "persona"):
            if isinstance(patch.get(k), str) and patch[k].strip():
                cur[k] = patch[k].strip()
        if "speed" in patch:
            try:
                s = float(patch["speed"])
                cur["speed"] = max(0.5, min(2.0, s))
            except (TypeError, ValueError):
                pass

        # 用户没动人设文本但改了名字时，把人设里的旧名替换成新名，
        # 否则模型会继续自称旧名字。
        new_name = cur.get("name") or DEFAULT["name"]
        if new_name != old_name and isinstance(patch.get("persona"), str) is False:
            cur["persona"] = apply_name(cur["persona"], new_name)

        os.makedirs(os.path.dirname(_PATH), exist_ok=True)
        tmp = _PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _PATH)
        logger.info(
            f"[persona] 已保存 name={cur.get('name')} "
            f"voice={cur['voice']} speed={cur['speed']}"
        )
        return cur


def get_voice() -> str:
    return load()["voice"]


def get_speed() -> float:
    return load()["speed"]


def get_persona() -> str:
    return load()["persona"]


def get_name() -> str:
    """她的名字，用于界面标题和对话署名。"""
    return load().get("name") or DEFAULT["name"]


def apply_name(persona_text: str, name: str) -> str:
    """把人设里的默认名字替换成用户设置的名字。

    人设是用户可编辑的自由文本，里面通常写着"你叫小雅……"。
    改名后如果不替换，模型会继续自称旧名字。
    只替换独立出现的旧名，避免误伤其它词。
    """
    old = DEFAULT["name"]
    if not name or name == old or old not in persona_text:
        return persona_text
    return persona_text.replace(old, name)
