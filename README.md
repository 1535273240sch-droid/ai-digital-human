# AI 数字人（全云端轻量版 · LiveTalking-StepFun）

<div align="center">

![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011%20(64--bit)-blue?style=flat-square&logo=windows)
![Version](https://img.shields.io/badge/version-1.1.0-green?style=flat-square)
![VRAM](https://img.shields.io/badge/VRAM-MuseTalk%20~10GB%20%7C%20wav2lip%20~2GB-brightgreen?style=flat-square)
![GPU](https://img.shields.io/badge/GPU-NVIDIA%20(6GB%2B)-green?style=flat-square&logo=nvidia)
![Cloud Engine](https://img.shields.io/badge/Cloud%20AI-StepFun%20(ASR%20%2B%20LLM%20%2B%20TTS%20%2B%20Realtime)-blueviolet?style=flat-square)
![CUDA](https://img.shields.io/badge/CUDA-12.8%20(sm__120%20Ready)-76B900?style=flat-square&logo=nvidia)
![License](https://img.shields.io/badge/License-Apache%202.0-yellow?style=flat-square)

<p align="center">
  <b>本地实时口型推理 + 云端全流程多模态大脑（ASR / LLM / TTS / 实时语音）</b><br>
  默认 <b>MuseTalk 1.5 高清整脸重绘</b>，也可一键回退 <b>wav2lip256 轻量档（约 2GB 显存）</b>
</p>

</div>

---

## 更新日志

### v1.1.0（本次更新）
- **口型模型升级 MuseTalk 1.5**：整脸重绘，画质明显优于 wav2lip256；`config.yaml` / `start.bat` 默认 `--model musetalk`（显存约 10GB，RTX 5070 实测稳跑 25fps），可一键回退轻量档
- **新增无框桌面客户端**：`desktop_client.py` + `start_desktop.bat`（双击即用）——无边框悬浮窗、顶部栏拖动、📌置顶 / ─最小化 / ✕关闭；自带 WebView2 补丁（`tools/apply_webview_patch.py`），修复**系统代理导致本地请求挂起**与**自动播放 / 麦克风权限**问题
- **实时语音链路修复**（点麦克风即走的 `stepaudio-2.5-realtime`）：
  - 上行音频 **16k→24k 升采样**：原实现直接推 16k，云端按 24k 解析 → 表现为"开麦她听不到"
  - **空闲保活**：15 秒无上行补 100ms 静音，避免云连接因"长时间无操作"被回收
  - **断线通知前端**：云端断开时关闭浏览器连接并提示，界面不再停留在"实时对话中"却已失效
- **页面自动重连**：客户端模式下每 5 秒检查连接状态，断开自动重连（服务冷启动慢也不会停在"未连接"）
- **素材处理工具**：`pick_stable_frames.py`（自动挑"闭嘴 + 头部稳定"片段）、`pick_best_static_frame.py`（挑最优单帧做静态底图）、`make_avatar_from_video.py`（视频 → 形象）
- **自检脚本同步**：`selftest.py` 的模型文件检查项改为 MuseTalk 权重
- 新增 `tools/test_realtime.py`：无需真人说话即可端到端验证实时语音链路

---

## 💡 项目设计理念

本项目基于优质开源项目 [LiveTalking](https://github.com/lipku/LiveTalking) 进行全流程云原生化重构：

- **痛点**：传统开源数字人方案本地同时加载三个重型模型（Qwen3-14B 大脑 + Faster-Whisper 耳朵 + Qwen3-TTS 嘴巴），显存消耗高达 **17GB+**，普通显卡极易爆显存（OOM）。
- **破局**：把感知与思考全链路交给 [阶跃星辰 StepFun](https://platform.stepfun.com/) 云端 API，**本地显卡 100% 专供口型渲染**。
- **两条路线**：

  | 档位 | 模型 | 显存 | 说明 |
  |---|---|---|---|
  | **高清（默认）** | MuseTalk 1.5 | ~10GB | 整脸重绘，自然度高，推荐 RTX 3060Ti / 4060Ti 以上 |
  | 轻量 | wav2lip256 | ~2GB | 只重绘嘴部，速度最快，6GB 显存可用 |

---

## 🏗️ 系统拓扑架构

```
                     ┌──────────────────────────────────────────────┐
                     │          云端服务：阶跃星辰 (StepFun)          │
                     │  1. 实时语音 stepaudio-2.5-realtime（边说边识别）│
                     │  2. 语音识别 (ASR)  ·  认知思考 (LLM)          │
                     │  3. 语音合成 (TTS)  ·  音色复刻                │
                     └──────────────────────▲───────────────────────┘
                                            │ 音频流 (PCM16)
                                            ▼
┌──────────────────┐  WebRTC 信令   ┌──────────────────────────────────────────────┐
│   客户端展示层    │ ────────────> │              本地实时音视频引擎               │
│  - 无框悬浮窗/浏览器│              │  - LiveTalking 视频处理管线                  │
│  - WebGPU 液金球  │ <──────────── │  - MuseTalk 1.5 / wav2lip256 口型推理        │
│  - 实时对话字幕    │  WebRTC 视频流 └──────────────────────────────────────────────┘
└──────────────────┘
```

---

## 📂 项目工程结构

```
ai-digital-human/
├── VERSION                        # 版本号
├── desktop_client.py              # 无框悬浮桌面客户端（pywebview）
├── start_desktop.bat              # 双击启动：重放补丁 → 起服务 → 弹无框窗口
├── 独立客户端.bat                 # 备选：Edge/Chrome --app 独立窗口
├── 功能说明与修复记录.md           # 修复根因与详细使用说明
├── src/                           # 核心服务源码（LiveTalking 云原生化）
│   ├── tts/stepfun.py             # 阶跃星辰 TTS 适配器
│   ├── llm.py                     # StepFun 对话模型
│   ├── server/persona.py          # 人设 / 音色 / 名字动态管理
│   ├── server/realtime_bridge.py  # 实时语音桥接（16k→24k 升采样 / 保活 / 断线通知）
│   ├── server/asr_server.py       # 云端语音识别中继
│   ├── server/rtc_manager.py      # WebRTC 动态码率自适应
│   ├── avatars/musetalk/          # MuseTalk 形象生成与推理
│   └── web/
│       ├── realtime.html          # 沉浸式前端（液金球 + 无框窗口增强）
│       └── orb.js / orb-shader.wgsl
├── tools/                         # 实用工具
│   ├── check_mic.py               # 麦克风拾音自检
│   ├── apply_webview_patch.py     # 给 pywebview 打本地补丁（幂等）
│   ├── make_avatar_from_video.py  # 视频 / 图片 → 数字人形象
│   ├── pick_stable_frames.py      # 自动挑"闭嘴 + 头部稳定"帧
│   ├── pick_best_static_frame.py  # 挑最优单帧（静态底图，最稳）
│   ├── test_realtime.py           # 实时语音链路端到端测试
│   └── bench_models.py            # 各模型延迟实测
├── launcher.py                    # 轻量启动引导器（可编译为 exe）
├── selftest.py                    # 端到端自检脚本
├── install.bat                    # 自动化环境依赖安装
└── start.bat                      # 一键启动服务
```

---

## 🚀 快速上手

### 1. 环境

```bat
:: 假定工作目录为 D:\AI
cd /d D:\AI
python -m venv D:\AI\venv
D:\AI\install.bat
```

> ⚠️ **RTX 50 系（Blackwell 架构）必须装 CUDA 12.8 (cu128)**，cu124 会触发 `CUDA kernel image missing`。

### 2. 准备模型权重

| 权重 | 放置路径 | 大小 |
|---|---|---|
| `unet.pth` + `musetalk.json` | `src/models/musetalkV15/` | 3.2GB |
| `diffusion_pytorch_model.safetensors` + `config.json` | `src/models/sd-vae/` | 319MB |
| `pytorch_model.bin` / `config.json` / `preprocessor_config.json` | `src/models/whisper/` | 145MB |
| `dw-ll_ucoco_384.pth` | `src/models/dwpose/` | 388MB |
| `79999_iter.pth` + `resnet18-5c106cde.pth` | `src/models/face-parse-bisent/` | 96MB |
| `s3fd-619a316812.pth` | `src/models/hub/checkpoints/` | 86MB |
| `wav2lip.pth`（轻量档可选） | `src/models/` | 205MB |

### 3. 配置密钥

```bat
copy .env.example LiveTalking\.env
```
```ini
STEPFUN_API_KEY=你的密钥        # https://platform.stepfun.com/interface-key
STEPFUN_API_BASE=https://api.stepfun.com/step_plan/v1
```

### 4. 生成形象

```bat
:: 用 5~10 秒正面视频（嘴唇微闭、头部稳定）生成高清形象
D:\AI\venv\Scripts\python.exe tools\make_avatar_from_video.py 你的视频.mp4 musetalk_avatar

:: 素材若在"说话"（唇缝微张），先自动挑最稳片段 / 最优单帧
D:\AI\venv\Scripts\python.exe tools\pick_stable_frames.py
D:\AI\venv\Scripts\python.exe tools\pick_best_static_frame.py
```

### 5. 自检与启动

```bat
D:\AI\venv\Scripts\python.exe selftest.py     :: 7 项自检
start.bat                                     :: 浏览器方式 http://localhost:8010/realtime.html
:: 或
start_desktop.bat                             :: 无框悬浮桌面版（推荐，双击即用）
```

---

## ⚙️ 硬件要求

| 档位 | 显存 | 实测 |
|---|---|---|
| MuseTalk 1.5（默认） | ~10GB | RTX 5070 稳跑 25fps |
| wav2lip256（轻量） | ~2GB | RTX 5060 8GB 稳跑 25fps |
| 无独显 | — | 仅 2-3fps，不可用 |

硬盘预留约 8GB（虚拟环境 + 运行库）+ 模型权重 4~5GB。

---

## 🎮 交互控制

启动后访问 `http://localhost:8010/realtime.html`（桌面版直接弹无框窗口）：

| 交互部件 | 功能说明 |
|---|---|
| **中央 WebGPU 液金球** | 随声音起伏；点击开始 / 终止会话 |
| **麦克风按钮** | 单击进入**实时语音**（边说边识别，秒回）；再点结束 |
| **空格快捷键** | 按住说话（Push-to-Talk），松开即发送 |
| **右侧停止按钮** | 实时打断她当前话语 |
| **右上 ⚙️ 面板** | 人设 Prompt、音色试听、语速；「实时对话」开关 |
| **形象更换** | `http://localhost:8010/avatar.html` 上传 5~10 秒视频生成新形象 |

无框桌面版额外提供：顶部拖动栏、📌 置顶开关、─ 最小化、✕ 关闭。

---

## 📌 技术边界与注意事项

1. **必须联网**：识别、思考、合成、实时语音全部在 StepFun 云端执行；
2. **素材规范（直接决定口型质量）**：请用**正面人像、嘴唇自然微闭、头部基本不动**的 5~10 秒片段。
   若素材本身在"说话"（唇缝全程微张），多帧底图会出现嘴部轻微抖动，此时建议：
   - `tools/pick_stable_frames.py` 挑最稳片段（保留眨眼等自然动作）；或
   - `tools/pick_best_static_frame.py` 挑**单帧静态底图**（最稳、从原理上不抖，代价是不眨眼）
3. **延迟**：实时语音 `stepaudio-2.5-realtime` 说完约 1 秒内接话；文字链路（ASR→LLM→TTS）约 5~10 秒；
4. **系统代理**：无框客户端已强制 `--no-proxy-server` 直连本地服务；用浏览器方式且开着代理时，请把 `127.0.0.1` 加入代理绕过列表，否则页面请求会被挂起。

---

## 🤝 致谢与开源生态

- [LiveTalking](https://github.com/lipku/LiveTalking) — 优秀的开源实时流媒体数字人框架
- [MuseTalk](https://github.com/TMElyralab/MuseTalk) — 实时高质量口型同步
- [StepFun 开放平台](https://platform.stepfun.com/) — 多模态大模型与语音合成基座

---

## 📄 许可证

本项目基于 [Apache License 2.0](LICENSE) 协议开源。
