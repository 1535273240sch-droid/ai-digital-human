import json
import time
import os
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from avatars.base_avatar import BaseAvatar
from utils.logger import logger

# Built-in LLM providers. Each exposes an OpenAI-compatible chat completions
# endpoint; the active one is selected with --llm_provider (default: dashscope).
LLM_PROVIDERS = {
    "dashscope": {
        "api_key_env": "DASHSCOPE_API_KEY",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
    },
    "orcarouter": {
        "api_key_env": "ORCAROUTER_API_KEY",
        "base_url": "https://api.orcarouter.ai/v1",
        "default_model": "orcarouter/auto",
    },
    "stepfun": {
        "api_key_env": "STEPFUN_API_KEY",
        "base_url": "https://api.stepfun.com/v1",
        "default_model": "step-3.7-flash",
    },
}
# 人设。语音场景下必须约束成口语短句，Markdown/列表/emoji 会被 TTS 逐字念出来。
# 注意：这里不能缓存 os.getenv 的结果 —— load_dotenv() 在 app.py 的 __main__
# 中才执行，而本模块更早被 import，import 期读到的会是空值。
_FALLBACK_SYSTEM_PROMPT = (
    "你是一个数字人助手。回答要口语化、简短，每次两三句话，"
    "带自然的语气词。不要使用 Markdown、列表、编号或表情符号。"
)


def _env_base_url(provider: str, cfg: dict) -> str:
    """Resolve the provider base URL, honoring per-provider env overrides."""
    if provider == "stepfun":
        return os.getenv("STEPFUN_API_BASE", cfg["base_url"]).rstrip("/")
    return cfg["base_url"]


def _llm_provider(opt) -> str:
    """Return the configured provider name, defaulting to dashscope."""
    return getattr(opt, 'llm_provider', 'dashscope') or 'dashscope'


def _llm_client(opt):
    """Create the OpenAI-compatible client for the configured provider."""
    from openai import OpenAI
    provider = _llm_provider(opt)
    cfg = LLM_PROVIDERS.get(provider, LLM_PROVIDERS['dashscope'])
    return OpenAI(
        api_key=os.getenv(cfg['api_key_env']),
        base_url=os.getenv('LLM_BASE_URL', '') or _env_base_url(provider, cfg),
    )


def _llm_model(opt) -> str:
    """Resolve the model name, falling back to the provider default."""
    cfg = LLM_PROVIDERS.get(_llm_provider(opt), LLM_PROVIDERS['dashscope'])
    return getattr(opt, 'llm_model', '') or os.getenv('LLM_MODEL', '') or cfg['default_model']


def _system_prompt(opt) -> str:
    """Resolve the persona: 页面配置 > CLI arg > env var > built-in default。

    人设里通常写着"你叫小雅……"，如果用户在界面上改了名字，
    这里把旧名字替换掉，否则模型会继续自称旧名。
    """
    try:
        from server import persona
        p = persona.get_persona()
        if p:
            return persona.apply_name(p, persona.get_name())
    except Exception:
        pass
    return (
        getattr(opt, 'llm_system_prompt', '')
        or os.getenv("LLM_SYSTEM_PROMPT", "")
        or _FALLBACK_SYSTEM_PROMPT
    )



def llm_response(message,avatar_session:'BaseAvatar',datainfo:dict={}):
    try:
        opt = avatar_session.opt
        start = time.perf_counter()
        client = _llm_client(opt)
        model = _llm_model(opt)
        end = time.perf_counter()
        logger.info(f"llm Time init: {end-start}s,{message}")

        # StepFun 的模型都带推理阶段，思考内容走 reasoning_content 字段（不会被
        # TTS 念到），但同样消耗 token 预算。max_tokens 给小了会出现"思考完没
        # 预算说正文"，表现为 content 为空、数字人张不开嘴。这里给足余量。
        max_tokens = int(os.getenv("LLM_MAX_TOKENS", "1024"))
        reasoning_effort = os.getenv("LLM_REASONING_EFFORT", "low")

        create_kwargs = dict(
            model=model,
            messages=[{'role': 'system', 'content': _system_prompt(opt)},
                    {'role': 'user', 'content': message}],
            stream=True,
            max_tokens=max_tokens,
            # Display token usage in the last line of the streamed response.
            stream_options={"include_usage": True},
        )
        if reasoning_effort:
            create_kwargs["reasoning_effort"] = reasoning_effort

        completion = client.chat.completions.create(**create_kwargs)
        result=""
        full_reply=""      # 完整回复，用于推送到前端气泡
        first = True
        for chunk in completion:
            if len(chunk.choices)>0:
                msg = chunk.choices[0].delta.content
                # 只取正文。推理内容在 delta.reasoning_content 里，忽略即可。
                if not msg:
                    continue
                if first:
                    end = time.perf_counter()
                    logger.info(f"llm Time to first content: {end-start}s")
                    first = False
                full_reply += msg
                lastpos=0
                for i, char in enumerate(msg):
                    if char in ",.!;:，。！？：；" :
                        result = result+msg[lastpos:i+1]
                        lastpos = i+1
                        if len(result)>10:
                            logger.info(result)
                            avatar_session.put_msg_txt(result,datainfo)
                            result=""
                result = result+msg[lastpos:]
        end = time.perf_counter()
        logger.info(f"llm Time to last chunk: {end-start}s")
        if result:
            avatar_session.put_msg_txt(result,datainfo)

        # 把完整回复推给前端，用于显示"她说"的气泡
        if full_reply.strip():
            try:
                avatar_session.send_msg(json.dumps(
                    {"type": "reply", "text": full_reply.strip()},
                    ensure_ascii=False,
                ))
            except Exception:
                logger.debug("推送回复气泡失败", exc_info=True)
        elif first:
            # 一个正文 chunk 都没收到 —— 通常是 max_tokens 被推理阶段吃光
            logger.warning(
                f"llm 没有产出正文（model={model}, max_tokens={max_tokens}）"
                "。推理模型会把 token 先用思考，调大 LLM_MAX_TOKENS 或"
                "调低 LLM_REASONING_EFFORT"
            )

    except Exception as e:
        logger.exception('llm exceptiopn:')
        return
