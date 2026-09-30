# AI 数字人（全云端轻量版 · LiveTalking-StepFun）

<div align="center">

![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011%20(64--bit)-blue?style=flat-square&logo=windows)
![VRAM](https://img.shields.io/badge/VRAM-~2GB%20Minimal-brightgreen?style=flat-square)
![GPU](https://img.shields.io/badge/GPU-NVIDIA%20(6GB+)-green?style=flat-square&logo=nvidia)
![Cloud Engine](https://img.shields.io/badge/Cloud%20AI-StepFun%20(ASR%20%2B%20LLM%20%2B%20TTS)-blueviolet?style=flat-square)
![CUDA](https://img.shields.io/badge/CUDA-12.8%20(sm__120%20Ready)-76B900?style=flat-square&logo=nvidia)
![License](https://img.shields.io/badge/License-Apache%202.0-yellow?style=flat-square)

<p align="center">
  <b>本地实时口型推理 + 云端全流程多模态大脑（ASR / LLM / TTS）</b><br>
  整机显存开销仅需约 <b>2GB</b>，彻底突破消费级 8GB 显卡运行门槛，告别 17GB 本地大模型臃肿配置。
</p>

</div>

---

## 💡 项目设计理念

本项目基于优质开源项目 [LiveTalking](https://github.com/lipku/LiveTalking) 进行全流程云原生化重构：

- **痛点**：传统开源数字人方案本地同时加载三个重型模型（Qwen3-14B 大脑 + Faster-Whisper 耳朵 + Qwen3-TTS 嘴巴），显存消耗高达 **17GB+**，需要强劲多卡或高昂算力，普通显卡极易爆显存（OOM）。
- **破局**：将感知与思考全链路委托给 [阶跃星辰 StepFun](https://platform.stepfun.com/) 云端高并发 API，**本地显卡 100% 专供 `wav2lip256` 实时口型渲染**。
- **成果**：显存开销从 **17GB 暴降至 2GB**，无需配置复杂的 WSL 容器，免去数十 GB 权重下载，8GB 显卡也能宽裕跑满 25 FPS 实时流。

---

## 🏗️ 系统拓扑架构

```
                     ┌──────────────────────────────────────────────┐
                     │          云端服务：阶跃星辰 (StepFun)          │
                     │  1. 语音识别 (ASR)  ·  实时端点检测 (VAD)      │
                     │  2. 认知思考 (LLM)  ·  人设角色热更           │
                     │  3. 语音合成 (TTS)  ·  18 款超拟真音色/克隆     │
                     └──────────────────────▲───────────────────────┘
                                            │ 音频流 (WAV/PCM)
                                            ▼
┌──────────────────┐  WebRTC 信令   ┌──────────────────────────────────────────────┐
│   客户端展示层    │ ────────────> │              本地实时音视频引擎               │
│  - WebGPU 液金球 │               │  - LiveTalking 视频处理管线                  │
│  - 独立透明悬浮窗 │ <──────────── │  - Wav2Lip 256 口型推理 (本地 ~1.3GB 显存)    │
│  - 实时对话字幕   │  WebRTC 视频流 └──────────────────────────────────────────────┘
```

---

## 📂 项目工程结构

```
ai-digital-human/
├── src/                           # 核心服务源码
│   ├── tts/stepfun.py             # 阶跃星辰 (StepFun) 语音合成适配器
│   ├── llm.py                     # StepFun Provider 与系统角色设定热更新
│   ├── server/persona.py          # 运行时人设 / 音色 / 名字动态管理器
│   ├── server/asr_server.py       # 云端语音识别中继与分发服务
│   ├── server/rtc_manager.py      # WebRTC 动态码率自适应管理
│   ├── avatars/wav2lip/genavatar.py # 人脸检测与方框自适应裁剪算法
│   └── web/
│       ├── realtime.html          # 沉浸式前端界面（含声波交互球）
│       ├── orb.js                 # WebGPU 液金球动态流体渲染
│       └── orb-shader.wgsl        # 液金球 WGSL 着色器源码
├── tools/check_mic.py             # 本地麦克风拾音全链路自检工具
├── launcher.py                    # 轻量启动引导器（可编译为独立 exe）
├── selftest.py                    # 端到端 7 项核心功能自检脚本
├── install.bat                    # 自动化环境依赖安装脚本
├── start.bat                      # 一键式后台与服务启动器
├── 独立客户端.bat                 # 极简无边框悬浮应用窗口
└── .env.example                   # 全局环境变量模板
```

---

## 🚀 快速上手部署

### 方式一：下载预编译发布版（最省心）
1. 访问本仓库 [Releases 页面](../../releases) 下载最新版 `AI数字人.exe`；
2. 解压后将 exe 与项目内的 `start.bat` 等脚本置于同一目录；
3. 双击 `AI数字人.exe`，启动器将自动完成环境校验与初始化引导。

---

### 方式二：源码环境手动安装

#### 1. 创建 Python 虚拟环境 (推荐 Python 3.12)
```bat
:: 假定工作目录为 D:\AI
cd /d D:\AI
python -m venv D:\AI\venv
```

#### 2. 安装 CUDA 依赖与 PyTorch
> ⚠️ **RTX 50 系（Blackwell 架构）特别提醒**：必须安装 **CUDA 12.8 (cu128)** 版本，cu124 会触发 `CUDA error: no kernel image is available`。

```bat
:: 安装核心环境
D:\AI\install.bat
```

#### 3. 准备预训练口型权重
请下载以下模型文件并放置在对应路径中：

| 权重文件 | 放置路径 | 大小 | 来源说明 |
|---|---|---|---|
| `wav2lip.pth` | `LiveTalking/models/` | 205MB | [HuggingFace 镜像下载](https://huggingface.co/yiliAST/livetalking-assets/resolve/main/models/wav2lip.pth) |
| `s3fd-619a316812.pth` | `LiveTalking/models/hub/checkpoints/` | 86MB | 初次生成形象时自动拉取 |

*注：`wav2lip.pth` 文件名已被代码锁定，请勿随意重命名。*

#### 4. 配置 API Key
复制配置模板并填入您的 StepFun 密钥：
```bat
copy .env.example LiveTalking\.env
```
编辑 `LiveTalking\.env`：
```ini
STEPFUN_API_KEY=你的密钥           # 获取地址：https://platform.stepfun.com/interface-key
STEPFUN_API_BASE=https://api.stepfun.com/step_plan/v1
```

#### 5. 运行环境自检与启动
```bat
:: 运行自动化端到端测试 (确保 7 项自测全部通过)
D:\AI\venv\Scripts\python.exe selftest.py

:: 启动主服务
start.bat

:: 或启动极简独立悬浮窗口
独立客户端.bat
```

---

## ⚙️ 硬件要求与实机基准测试

### 最低配置要求
- **操作系统**：Windows 10 / 11 (64 位)
- **显卡（GPU）**：NVIDIA 独立显卡，**6GB 显存以上**（本地口型推理依赖 CUDA 加速，无独显 CPU 仅 2-3 fps）
- **硬盘空间**：预留约 8GB（含 Python 虚拟环境与 PyTorch 运行库）

### 实机测试数据 (RTX 5060 8GB + Windows 10)
| 监控指标 | 实测表现 | 行业参考基准 |
|---|---|---|
| **口型推理帧率** | **25.0 FPS** (稳帧) | >= 25.0 FPS (广播级实时流畅) |
| **运行时整机显存** | **~2.0 GB** | 传统本地方案常驻 17GB+ |
| **云端 ASR 响应** | 1.8s 音频 $\rightarrow$ **2.5s** 返回文本 | 低延迟流式响应 |
| **云端 TTS 延迟** | 首次约 **4.5s**（含 TLS 握手），后续约 **3.0s** | 广播级拟真音色 |
| **端到端综合自检** | **7 / 7 全部通过** | 生产级稳定性 |

---

## 🎮 交互控制与玩法

启动后访问本地面板 `http://localhost:8010`：

| 交互部件 | 功能说明 |
|---|---|
| **中央 WebGPU 液金球** | 动态流体光球，随数字人声音起伏律动；点击可开始/终止会话 |
| **麦克风按钮** | 单击开始拾音说话，再次点击完成录音下发 |
| **空格快捷键 (Space)** | 按住说话（Push-to-Talk 模式），松开即发送 |
| **右侧停止按钮** | 实时打断数字人当前话语 |
| **右上角 ⚙️ 面板** | 在线调整人设 Prompt、测试试听 18 种女声、语速微调 |
| **形象更换 (`/avatar.html`)** | 上传 5~10 秒正面微动闭嘴视频，30 秒快速合成全新角色 |

---

## 📌 技术边界与注意事项

1. **必须保持网络通畅**：ASR 识别、大模型思维推理与 TTS 语音合成均在 StepFun 云端执行；
2. **底模素材规范**：制作新形象时，请务必保证视频为**正面人像、嘴唇自然微闭、身体头部移动在 10px 以内**，避免因过度晃动造成下巴接缝拉扯；
3. **分辨率策略**：Wav2Lip 嘴部生成为 256×256 分辨率，建议采用微暗光或正面固定视角以获得最佳融合观感。

---

## 🤝 致谢与开源生态

- [LiveTalking](https://github.com/lipku/LiveTalking) — 优秀的开源实时流媒体数字人框架
- [StepFun 开放平台](https://platform.stepfun.com/) — 强大的多模态大模型与语音合成基座
- [零度博客](https://www.freedidi.com/24984.html) — 原始实践灵感与教程指导

---

## 📄 许可证

本项目基于 [Apache License 2.0](LICENSE) 协议开源。
