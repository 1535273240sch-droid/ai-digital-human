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
    # StepFun 实时接口输入侧按 24k 解析（与输出一致）
    CLOUD_IN_SR = 24000

    def __init__(self, avatar_session, on_text=None, on_state=None,
                 voice=None, instructions=None, on_close=None):
        self.avatar = avatar_session
        self.on_text = on_text          # (who, text) -> None
        self.on_state = on_state        # (state) -> None
        self.on_close = on_close        # 云端连接断开时回调（通知前端复位）
        self.voice = voice or os.getenv("STEPFUN_REALTIME_VOICE", "linjiajiejie")
        self.instructions = instructions or ""

        self.ws = None
        self.thread = None
        self.ka_thread = None
        self._stop = threading.Event()
        self._send_lock = threading.Lock()
        self._ready = threading.Event()
        self._session_id = None
        self._closed = False
        self._last_send_t = 0.0

        # 音频重采样残留（24k→16k 会有不足一帧的尾巴）
        self._leftover = None
        # 上行重采样残留（16k→24k）
        self._in_leftover = None

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

        # 空闲保活：StepFun 会因"长时间无操作"掐断连接，这里定期补一点静音
        self.ka_thread = threading.Thread(target=self._keepalive_loop, daemon=True)
        self.ka_thread.start()

        return self

    def _keepalive_loop(self, interval=5.0, idle=15.0):
        """超过 idle 秒没有上行数据就补 100ms 静音，避免云连接被回收。"""
        silent = base64.b64encode(b"\x00" * 4800).decode("ascii")  # 100ms @24k pcm16
        while not self._closed and not self._stop.is_set():
            time.sleep(interval)
            try:
                if self._closed:
                    break
                if time.time() - self._last_send_t >= idle:
                    self._send({
                        "event_id": "evt_ka",
                        "type": "input_audio_buffer.append",
                        "audio": silent,
                    })
            except Exception:
                logger.debug("[Realtime] 保活失败", exc_info=True)

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
                self._last_send_t = time.time()
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
        was_closed = self._closed
        self._closed = True
        logger.info("[Realtime] 连接关闭 code=%s", code)
        # 通知上层（前端需要复位，否则界面还显示"实时对话中"但其实已经哑了）
        if not was_closed and self.on_close:
            try:
                self.on_close()
            except Exception:
                logger.debug("[Realtime] on_close 回调异常", exc_info=True)

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
        """浏览器推来的 16kHz PCM16 → 升采样到 24kHz 再发给实时接口。

        StepFun 实时接口的 input_audio_format=pcm16 是按 24kHz 解析的；
        若直接塞 16k 数据，云端会把话音当慢放/变调处理，导致完全识别不出来。
        """
        if not pcm_bytes or self._closed:
            return
        try:
            samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
        except Exception:
            return
        if samples.size == 0:
            return

        if self.IN_SR != self.CLOUD_IN_SR:
            # 带上上次残余一起重采样，再按重叠量裁掉，避免块边界爆音
            if self._in_leftover is not None and self._in_leftover.size:
                samples = np.concatenate([self._in_leftover, samples])
            up = resampy.resample(samples, self.IN_SR, self.CLOUD_IN_SR)
            keep = int(self.IN_SR * 0.01)                      # 10ms 输入重叠
            drop = int(keep * self.CLOUD_IN_SR / self.IN_SR)   # 对应输出样本数
            out = up[drop:] if up.size > drop else up
            self._in_leftover = samples[-keep:]
        else:
            out = samples

        pcm24 = np.clip(out, -32768, 32767).astype(np.int16).tobytes()
        self._send({
            "event_id": "evt_audio",
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(pcm24).decode("ascii"),
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
