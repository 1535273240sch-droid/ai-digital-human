"""实时语音桥接 —— 用 StepFun Realtime 实现边说边识别。

和原来的"录音→识别→回答→合成"四步串行不同，这里用一个 WebSocket
同时完成识别、对话、合成，并自带 VAD（自动判断你说完没有），
所以不需要手动点停止，首响也从 4-8 秒降到约 1 秒。

工作方式：
    浏览器麦克风 → WebSocket → 本模块
                                  ↓ 转发 PCM
                          StepFun Realtime
                                  ↓ 返回音频（24kHz PCM16）
                          重采样成 16kHz
                                  ↓
                        推给口型渲染层（avatar_session.put_audio_frame）

文字（用户说的 / 她说的）通过回调推给前端气泡。

注意：StepFun Realtime 输出是 24kHz PCM16，而口型模型要 16kHz，
所以必须重采样。这是接入这块的主要工作量。
"""

import asyncio
import base64
import json
import os
import threading
import time

from utils.logger import logger

try:
    import websocket  # websocket-client
    _HAS_WS = True
except ImportError:
    _HAS_WS = False

try:
    import numpy as np
    import resampy
    _HAS_RESAMPLE = True
except ImportError:
    _HAS_RESAMPLE = False


DEFAULT_API_BASE = "https://api.stepfun.com/v1"


_bootstrapped = False


def _ensure_env():
    """确保 .env / appconfig 已加载（本模块可能在 load_dotenv 之前被导入）。"""
    global _bootstrapped
    if _bootstrapped:
        return
    _bootstrapped = True
    try:
        from server import appconfig
        appconfig.bootstrap()
    except Exception:
        # 退而求其次：自己按绝对路径加载
        try:
            from dotenv import load_dotenv
            here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            p = os.path.join(here, ".env")
            if os.path.exists(p):
                load_dotenv(p)
        except Exception:
            pass


def _api_key():
    _ensure_env()
    return os.getenv("STEPFUN_API_KEY", "")


def _wss_url(model=None):
    """Realtime 的 WebSocket 地址。"""
    _ensure_env()
    base = os.getenv("STEPFUN_API_BASE", DEFAULT_API_BASE).rstrip("/")
    base = base.replace("https://", "wss://").replace("http://", "ws://")
    m = model or os.getenv("STEPFUN_REALTIME_MODEL", "stepaudio-2.5-realtime")
    return f"{base}/realtime?model={m}"


def available() -> bool:
    """实时语音是否可用（有 key 且装了依赖）。"""
    return bool(_api_key()) and _HAS_WS and _HAS_RESAMPLE


class RealtimeSession:
    """一个实时语音会话。

    用法：
        s = RealtimeSession(avatar_session, on_text=..., on_state=...)
        s.start()
        s.send_audio(pcm_bytes)   # 浏览器推来的 16k PCM16
        s.close()
    """

    # StepFun Realtime 的输出采样率（文档只写 pcm16，实测 24k）
    OUT_SR = 24000
    # 口型模型要的采样率
    IN_SR = 16000

    def __init__(self, avatar_session, on_text=None, on_state=None,
                 voice=None, instructions=None):
        self.avatar = avatar_session
        self.on_text = on_text          # (who, text) -> None
        self.on_state = on_state        # (state) -> None
        self.voice = voice or os.getenv("STEPFUN_REALTIME_VOICE", "linjiajiejie")
        self.instructions = instructions or ""

        self.ws = None
        self.thread = None
        self._stop = threading.Event()
        self._send_lock = threading.Lock()
        self._ready = threading.Event()
        self._session_id = None
        self._closed = False

        # 音频重采样残留（24k→16k 会有不足一帧的尾巴）
        self._leftover = None

    # ── 连接与配置 ────────────────────────────────────────────

    def start(self, timeout=20):
        if not available():
            raise RuntimeError(
                "实时语音不可用：需要 STEPFUN_API_KEY 和 websocket-client/resampy"
            )

        url = _wss_url()
        logger.info(f"[Realtime] 连接 {url}")

        self.ws = websocket.WebSocketApp(
            url,
            header=[f"Authorization: Bearer {_api_key()}"],
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self.thread = threading.Thread(target=self.ws.run_forever,
                                       kwargs={"ping_interval": 20},
                                       daemon=True)
        self.thread.start()

        if not self._ready.wait(timeout):
            logger.warning("[Realtime] 会话配置超时，继续尝试")

        return self

    def _on_open(self, ws):
        logger.info("[Realtime] 已连接，发送会话配置")
        cfg = {
            "event_id": "evt_cfg",
            "type": "session.update",
            "session": {
                "modalities": ["audio", "text"],
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "voice": self.voice,
                # VAD：自动判断说完没有，silence_duration_ms 是"静多久算说完"
                "turn_detection": {
                    "type": "server_vad",
                    "silence_duration_ms": int(
                        os.getenv("REALTIME_SILENCE_MS", "700")),
                },
            },
        }
        if self.instructions:
            cfg["session"]["instructions"] = self.instructions
        self._send(cfg)

    def _send(self, obj):
        if not self.ws or self._closed:
            return
        try:
            with self._send_lock:
                self.ws.send(json.dumps(obj, ensure_ascii=False))
        except Exception:
            logger.debug("[Realtime] 发送失败", exc_info=True)

    # ── 接收处理 ──────────────────────────────────────────────

    def _on_message(self, ws, message):
        try:
            d = json.loads(message)
        except Exception:
            return

        et = d.get("type", "")

        if et == "session.created":
            sid = (d.get("session") or {}).get("id")
            if sid:
                self._session_id = sid

        elif et == "session.updated":
            logger.info("[Realtime] 会话已就绪")
            self._ready.set()

        # 用户开始/停止说话（VAD）
        elif et == "input_audio_buffer.speech_started":
            if self.on_state:
                self.on_state("listening")

        elif et == "input_audio_buffer.speech_stopped":
            if self.on_state:
                self.on_state("thinking")

        # 用户说的话（识别结果）
        elif et in ("conversation.item.input_audio_transcription.delta",
                    "conversation.item.input_audio_transcription.completed"):
            txt = d.get("transcript") or d.get("text") or ""
            if txt and self.on_text and et.endswith("completed"):
                self.on_text("me", txt.strip())

        # 她的回复音频
        elif et == "response.audio.delta":
            b64 = d.get("delta") or d.get("audio") or ""
            if b64:
                self._push_audio(b64)

        elif et == "response.audio.done":
            if self.on_state:
                self.on_state("ready")

        # 她说的文字（用于气泡显示）
        elif et == "response.audio_transcript.done":
            txt = (d.get("transcript") or "").strip()
            if txt and self.on_text:
                self.on_text("her", txt)

        elif et == "response.audio_transcript.delta":
            pass  # 分片太碎，等 done 再显示

        elif et == "error":
            err = d.get("error") or {}
            logger.error("[Realtime] 服务端错误: %s", err.get("message", d))

    def _on_error(self, ws, error):
        logger.error("[Realtime] 连接错误: %s", error)

    def _on_close(self, ws, code=None, msg=None):
        self._closed = True
        logger.info("[Realtime] 连接关闭 code=%s", code)

    # ── 音频：24kHz → 16kHz，推给口型 ────────────────────────

    def _push_audio(self, b64: str):
        try:
            raw = base64.b64decode(b64)
        except Exception:
            return

        if not raw:
            return

        try:
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32767.0
        except Exception:
            return

        # 重采样到 16k（口型模型要求）
        if self.OUT_SR != self.IN_SR and samples.size > 0:
            samples = resampy.resample(samples, self.OUT_SR, self.IN_SR)

        # 拼上上次的残余，按 chunk 切分后投喂
        if self._leftover is not None and self._leftover.size:
            samples = np.concatenate([self._leftover, samples])

        chunk = getattr(self.avatar, "chunk", 320)
        n = (samples.size // chunk) * chunk
        if n == 0:
            self._leftover = samples
            return

        for i in range(0, n, chunk):
            try:
                self.avatar.put_audio_frame(samples[i:i + chunk], {})
            except Exception:
                logger.debug("[Realtime] 投喂音频失败", exc_info=True)

        self._leftover = samples[n:]

    # ── 对外接口 ──────────────────────────────────────────────

    def send_audio(self, pcm_bytes: bytes):
        """浏览器推来的 16kHz PCM16，转 base64 发给实时接口。"""
        if not pcm_bytes or self._closed:
            return
        self._send({
            "event_id": "evt_audio",
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(pcm_bytes).decode("ascii"),
        })

    def commit(self):
        """手动提交（VAD 关闭时用）。"""
        self._send({"event_id": "evt_commit",
                    "type": "input_audio_buffer.commit"})

    def cancel(self):
        """打断她说话。"""
        self._send({"event_id": "evt_cancel", "type": "response.cancel"})

    def close(self):
        self._stop.set()
        self._closed = True
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass
