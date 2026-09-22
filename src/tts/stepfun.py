import os
import time
from io import BytesIO

import numpy as np
import requests
import resampy
import soundfile as sf

from utils.logger import logger
from .base_tts import BaseTTS, State
from registry import register

# 阶跃星辰语音合成 (StepFun TTS) — 云端 HTTP 合成
# 文档: https://platform.stepfun.com/docs/zh/api-reference/audio/create-audio
# 音色可以是官方音色 ID，也可以是 /v1/audio/voices 复刻出来的 voice-xxx
DEFAULT_API_BASE = "https://api.stepfun.com/v1"


def _speech_url() -> str:
    """解析合成端点。运行时读取，避免 import 期 .env 尚未加载。"""
    base = os.getenv("STEPFUN_API_BASE", DEFAULT_API_BASE).rstrip("/")
    return os.getenv("STEPFUN_TTS_URL", f"{base}/audio/speech")


@register("tts", "stepfun")
class StepFunTTS(BaseTTS):
    """阶跃星辰 TTS。

    需要设置环境变量 STEPFUN_API_KEY。
    REF_FILE 用作音色 ID（官方音色如 cixingnansheng，或复刻音色 voice-xxx）。
    """

    def __init__(self, opt, parent):
        super().__init__(opt, parent)

        self.api_key = os.getenv("STEPFUN_API_KEY")
        self.voice = opt.REF_FILE or "cixingnansheng"
        self.model = os.getenv("STEPFUN_TTS_MODEL", "stepaudio-2.5-tts")
        # 口型模型要 16k 单声道，直接让云端按 16k 产出，省一次重采样
        self.src_sr = int(getattr(opt, "stepfun_sample_rate", self.sample_rate))
        self.response_format = getattr(opt, "stepfun_format", "wav")
        self.instruction = os.getenv("STEPFUN_TTS_INSTRUCTION", "")

        self.session = requests.Session()

        if not self.api_key:
            logger.warning("StepFunTTS: STEPFUN_API_KEY 未设置，请设置环境变量")

        logger.info(
            f"StepFunTTS init: model={self.model}, voice={self.voice}, "
            f"format={self.response_format}, sample_rate={self.src_sr}, "
            f"url={_speech_url()}"
        )

    def txt_to_audio(self, msg: tuple[str, dict]):
        text, textevent = msg
        if not text or not text.strip():
            return

        tts_cfg = textevent.get("tts", {}) if isinstance(textevent, dict) else {}
        voice = tts_cfg.get("ref_file", tts_cfg.get("voice", self._voice()))
        model = tts_cfg.get("model", self.model)

        audio = self._synthesize(text=text, voice=voice, model=model)
        if audio is None:
            logger.error("StepFunTTS: 合成失败，跳过本条")
            return

        self._push_frames(audio, text, textevent)

    def _voice(self) -> str:
        """音色：页面上的实时配置优先，其次启动参数，最后内置默认。"""
        try:
            from server import persona
            v = persona.get_voice()
            if v:
                return v
        except Exception:
            pass
        return self.voice

    def _speed(self) -> float:
        try:
            from server import persona
            return float(persona.get_speed())
        except Exception:
            return float(os.getenv("STEPFUN_TTS_SPEED", "1.0"))

    # ── API 调用 ──────────────────────────────────────────────

    def _synthesize(self, text: str, voice: str, model: str) -> np.ndarray | None:
        """调用云端合成，返回 16k float32 单声道波形。"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "input": text,
            "voice": voice,
            "response_format": self.response_format,
            "sample_rate": self.src_sr,
            "speed": self._speed(),
        }
        if self.instruction:
            payload["instruction"] = self.instruction

        start = time.perf_counter()
        logger.info(f"StepFunTTS POST voice={voice} text={text[:60]}...")
        try:
            res = self.session.post(
                _speech_url(), headers=headers, json=payload, timeout=60
            )
            if res.status_code != 200:
                logger.error(
                    f"StepFunTTS server error {res.status_code}: {res.text[:300]}"
                )
                return None
            end = time.perf_counter()
            logger.info(f"stepfun tts time: {end - start:.4f}s, {len(res.content)} bytes")
            return self._decode(res.content)
        except requests.exceptions.Timeout:
            logger.error("StepFunTTS request timeout")
        except Exception:
            logger.exception("StepFunTTS synthesize error")
        return None

    def _decode(self, raw: bytes) -> np.ndarray | None:
        """把返回音频解码成 float32 单声道 16k。"""
        if not raw:
            return None

        # pcm 是不带头信息的裸流，直接按 s16le 解析；其余交给 soundfile
        if self.response_format == "pcm":
            stream = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32767.0
            sample_rate = self.src_sr
        else:
            try:
                stream, sample_rate = sf.read(BytesIO(raw), dtype="float32")
            except Exception:
                logger.exception("StepFunTTS: 无法解析返回音频，回退按 pcm 解析")
                stream = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32767.0
                sample_rate = self.src_sr

        stream = np.asarray(stream, dtype=np.float32)
        if stream.ndim > 1:
            stream = stream[:, 0]

        if sample_rate != self.sample_rate and stream.shape[0] > 0:
            stream = resampy.resample(
                x=stream, sr_orig=sample_rate, sr_new=self.sample_rate
            )
        return stream

    # ── 按 20ms 分帧推给渲染层 ────────────────────────────────

    def _push_frames(self, stream: np.ndarray, text: str, textevent: dict):
        streamlen = stream.shape[0]
        idx = 0
        while streamlen >= self.chunk and self.state == State.RUNNING:
            eventpoint = {}
            streamlen -= self.chunk
            if idx == 0:
                eventpoint = {"status": "start", "text": text}
            elif streamlen < self.chunk:
                eventpoint = {"status": "end", "text": text}
            eventpoint.update(**textevent)
            self.parent.put_audio_frame(stream[idx : idx + self.chunk], eventpoint)
            idx += self.chunk

        # 尾部不足一帧时也要发结束标记，否则渲染层一直等
        if idx == 0 or streamlen > 0:
            eventpoint = {"status": "end", "text": text}
            eventpoint.update(**textevent)
            self.parent.put_audio_frame(
                np.zeros(self.chunk, dtype=np.float32), eventpoint
            )

    def stop_tts(self):
        self.session.close()
        logger.info("StepFunTTS session closed")
