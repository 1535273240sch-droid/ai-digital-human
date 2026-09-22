# AI 数字人（全云端版）

本地实时口型 + 云端语音与大模型。**整机只要约 2GB 显存**，8GB 显卡跑得很宽裕。

> 基于 [LiveTalking](https://github.com/lipku/LiveTalking) 改造，把原方案里三个吃显存的本地模型
> （Qwen3-14B 大脑 / faster-whisper 耳朵 / Qwen3-TTS 嘴巴）换成
> [阶跃星辰 StepFun](https://platform.stepfun.com/) 云端 API，本地只保留 wav2lip256 口型推理。
>
> **17GB → 2GB**，不需要 WSL、不需要重启、不需要下载几十 GB 模型。

---

## 这个仓库是什么

仓库里是**源码和构建配置**，不含模型权重和 Python 环境（那些太大，由脚本自动下载）。

`.exe` **不在本机打包**——推送到 GitHub 后由云端 Windows 机器自动构建。
详见 [自动构建](#自动构建)。

```
ai-digital-human/
├── src/                        改造后的 LiveTalking 源码
│   ├── tts/stepfun.py          新增：StepFun 语音合成插件
│   ├── llm.py                  已改：stepfun provider + 人设热更新
│   ├── server/persona.py       新增：人设/音色/名字运行时配置
│   ├── server/asr_server.py    已改：云端语音识别
│   ├── server/rtc_manager.py   已改：提高 WebRTC 码率
│   ├── avatars/wav2lip/genavatar.py  已改：人脸框改方框裁剪
│   └── web/
│       ├── realtime.html       新增：主界面（语音球）
│       ├── orb.js              新增：液金球（WebGPU）
│       └── orb-shader.wgsl     新增：液金球着色器
├── tools/check_mic.py          麦克风链路自测
├── launcher.py                 启动器（被打包成 exe）
├── selftest.py                 端到端自检
├── install.bat                 装依赖
├── start.bat                   启动服务
├── 独立客户端.bat              独立窗口启动
├── .env.example                配置模板
└── .github/workflows/          自动构建配置
```

---

## 安装（三种方式）

### 方式一：下载发布版 exe（最简单）

1. 到 [Releases](../../releases) 下载 `AI数字人.exe`
2. 放到解压后的完整目录里，**和 `start.bat` 等文件放在一起**
3. 双击运行

首次会自动装依赖（约 10 分钟），之后启动约 30 秒。

### 方式二：从源码手动装

```bat
:: 1. 准备目录：把 src 重命名为 LiveTalking，放到 D:\AI\ 下
::    即 D:\AI\LiveTalking\app.py

:: 2. 装 Python 3.12，创建虚拟环境
D:\AI\Python312\python.exe -m venv D:\AI\venv

:: 3. 装依赖（会下载 torch，约 2.7GB）
D:\AI\install.bat

:: 4. 配置 API Key
copy D:\AI\.env.example D:\AI\LiveTalking\.env
::    编辑 .env，填入 STEPFUN_API_KEY

:: 5. 自检
D:\AI\venv\Scripts\python.exe D:\AI\selftest.py

:: 6. 启动
D:\AI\start.bat
```

### 方式三：独立窗口

双击 `独立客户端.bat` —— 自动拉起服务，用无地址栏、无标签页的独立窗口打开。

---

## 需要下载的模型

模型权重体积大，不进仓库，需手动放好：

| 文件 | 放到 | 大小 | 下载 |
|---|---|---|---|
| `wav2lip.pth` | `LiveTalking/models/` | 205MB | [HuggingFace 镜像](https://huggingface.co/yiliAST/livetalking-assets/resolve/main/models/wav2lip.pth) |
| `s3fd-619a316812.pth` | `LiveTalking/models/hub/checkpoints/` | 86MB | 生成形象时自动下载 |

> `wav2lip.pth` 必须是这个名字，代码里路径写死了。名字不对会报 `FileNotFoundError`。

---

## 配置

复制 `.env.example` 为 `LiveTalking/.env`，填入：

```ini
STEPFUN_API_KEY=你的密钥           # https://platform.stepfun.com/interface-key
STEPFUN_API_BASE=https://api.stepfun.com/step_plan/v1
```

> `.env` 已在 `.gitignore` 里，**不会被提交**。

其余配置（人设、音色、名字、语速）都可以在**软件界面的设置面板**里改，不用碰配置文件。

---

## 自动构建

不用在本机打包。推送到 GitHub 后由云端构建：

**打 tag 自动构建并发布 Release：**
```bash
git tag v1.0.0
git push origin v1.0.0
```

**或手动触发：** 仓库页面 → Actions → Build Windows Launcher → Run workflow

构建产物：`AI数字人.exe`（轻量启动器，几 MB）。

> 只打包启动器而不是整个程序：torch 有 2.7GB，全塞进 exe 会得到一个巨大且脆弱的文件。
> 启动器负责检查环境、装依赖、下模型，然后拉起数字人窗口。

---

## 硬件要求

| 项目 | 要求 |
|---|---|
| 系统 | Windows 10/11 64 位 |
| 显卡 | **NVIDIA，6GB 显存以上**（本地口型推理需要 CUDA） |
| Python | 3.12 |
| 网络 | **必需**（语音识别/大模型/语音合成都在云端） |
| 磁盘 | 约 8GB（含 Python 环境和 torch） |

**关于显卡**：本地只跑 wav2lip 口型模型（约 1.3GB 显存），所以 6GB 就够。
**但没有独显不行**——CPU 跑口型只有 2-3 fps，完全不可用。

---

## 实测结果

在 RTX 5060 (8GB) + Windows 10 上：

| 项目 | 结果 |
|---|---|
| 口型推理帧率 | **25.0 fps**（实时标准 ≥25） |
| 整机显存占用 | 约 2GB（另有 1.3GB 是 Windows 桌面） |
| 云端 ASR | 1.8s 音频 → 2.5s 出结果 |
| 云端 TTS | 首次 4.5s（含握手），后续约 3s |
| 自检 | 7/7 通过 |

> **注意**：`torch` 必须用 **cu128**（CUDA 12.8）。RTX 50 系是 Blackwell 架构（sm_120），
> 用 cu124 会报 `CUDA error: no kernel image is available`。

---

## 使用

启动后打开 http://localhost:8010

| 元素 | 说明 |
|---|---|
| 中间的光球 | 会随她的声音起伏；点它开始/结束说话 |
| 左侧麦克风 | 点一下说话，说完再点一下 |
| 右侧停止 | 打断她 |
| 左下角文字 | 无框对话记录 |
| 右上角齿轮 | 设置：名字、音色、语速、人设 |
| 空格键 | 按住说话 |

**换形象**：打开 `/avatar.html`，上传视频（正面人像、嘴唇闭合、头部动作小、5-10 秒），
Avatar ID 填 `wav2lip256_你的名字`（前缀必须保留），生成后约 30-60 秒完成。

**换音色**：设置面板里有 18 个女声可选，点「试听」当场听。也可以用
[音色复刻](https://platform.stepfun.com/docs/zh/api-reference/audio/create-voice) 克隆自己的声音。

---

## 待办

- [ ] **接入实时语音**（`stepaudio-2.5-realtime`）—— 现在是"录音→识别→回答→合成"串行模式，
      接上实时 API 后可边说边识别，首响从 4-8 秒压到约 1 秒
- [ ] 设置面板补齐：API Key 填写、换形象（选视频直接生成）
- [ ] 显存自适应（启动时检测可用显存，自动调 batch_size）
- [ ] 打包 exe（本仓库已配好自动构建）

---

## 已知限制

- **需要联网**：语音和对话走云端，断网只剩本地口型。
- **口型分辨率 256**：嘴部是 256×256 生成的，靠"暗光侧脸"的构图掩盖画质差距。
  想更清晰要换 MuseTalk（需 12GB 显存，8GB 跑不动）。
- **源视频要求**：正面人像、嘴唇闭合、**头部动作尽量小**。
  实测头部移动 18-24px 时下巴交界会有接缝感，建议控制在 10px 以内。

---

## 致谢

- [LiveTalking](https://github.com/lipku/LiveTalking) — 实时数字人引擎（Apache 2.0）
- [StepFun 开放平台](https://platform.stepfun.com/) — 语音与语言模型
- 原始教程：[零度博客](https://www.freedidi.com/24984.html)
