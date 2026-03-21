# 🎬 噼哩噼哩 · Pilipili-AutoVideo

### 全自动 AI 视频代理 · 本地部署 · 一句话生成成片

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-18%20passed-brightgreen)](#测试)

[简体中文](README-CN.md) · [English](README.md) · [繁體中文](README-TW.md) · [日本語](README-JA.md) · [한국어](README-KO.md)

---

> 📹 **演示 Demo** — *将此处替换为完整工作流的 GIF 录屏：输入主题 → 分镇审核 → 成片交付*
> `docs/demo.gif`（待录制——参见 [贡献指南](#贡献指南)）

---

## 📖 项目简介

**噼哩噼哩（Pilipili-AutoVideo）** 是一个完全部署在本地的全自动 AI 视频代理系统。输入一句话，系统自动完成脚本策划 → 首帧图像生成 → TTS 配音 → 视频片段生成 → FFmpeg 拼接成片 → 字幕烧录，最终输出带字幕的 MP4 成品视频，并同步生成剪映草稿工程，供人类在剪映里进行最后 10% 的微调。

与同类产品（LibTV、火宝短剧）相比，噼哩噼哩的核心差异在于：

- **音画绝对同步**：先生成 TTS 配音并精确测量毫秒级时长，再以此控制视频 `duration`，彻底告别音画错位
- **首帧锁定策略**：先用 Nano Banana 生成 4K 关键帧图像，再用图生视频（I2V），画质下限极高，主体不漂移
- **数字孪生记忆**：Mem0 驱动的记忆系统，自动学习你的风格偏好，每次生成都会注入历史创作习惯
- **Skill 封装**：整个工作流被封装为标准 Skill，可被任意 AI Agent 直接调用

---

## 🎯 核心价值

- 🤖 **自然语言驱动**：一句话描述，AI 自动完成全部工作，无需手动操作任何节点
- 🎨 **顶级画质下限**：Nano Banana 首帧锁定 + Kling 3.0 / Seedance 1.5 双引擎，主体一致性极强
- 🔊 **音画绝对同步**：先测配音时长，再控视频时长，永远不会出现"配音还没说完视频就结束了"
- ✂️ **剪映草稿输出**：自动生成 CapCut/剪映草稿工程，AI 完成 90%，人类在剪映里微调 10%
- 🧠 **越用越懂你**：Mem0 记忆系统自动学习风格偏好，每次生成都更贴合你的审美
- 🔌 **Agent 可调用**：封装为标准 Skill，可被任意 Agent 直接调用，无缝集成到更大的自动化工作流

---

## 🛠️ 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                    噼哩噼哩 系统架构                           │
├─────────────────────────────────────────────────────────────┤
│  前端层   React 19 + TailwindCSS · 三栏工作台 · WebSocket 实时 │
├─────────────────────────────────────────────────────────────┤
│  API 层   FastAPI · WebSocket · REST · LangGraph 工作流编排   │
├──────────────┬──────────────┬──────────────┬────────────────┤
│  大脑层       │  视觉层       │  动态层       │  配音层         │
│  DeepSeek    │  Nano Banana │  Kling 3.0   │  MiniMax TTS   │
│  Kimi        │  (Gemini 3   │  Seedance    │  Speech 2.8 HD │
│  MiniMax LLM │   Pro Image) │  1.5 Pro     │                │
│  Gemini      │              │              │                │
├──────────────┴──────────────┴──────────────┴────────────────┤
│  组装层   Python + FFmpeg · xfade 转场 · WhisperX 字幕烧录    │
├─────────────────────────────────────────────────────────────┤
│  草稿层   pyJianYingDraft · 自动生成剪映/CapCut 草稿工程        │
├─────────────────────────────────────────────────────────────┤
│  记忆层   Mem0 · 本地 SQLite · 风格偏好数字孪生                 │
└─────────────────────────────────────────────────────────────┘
```

| 层级 | 技术选型 | 说明 |
| :--- | :--- | :--- |
| 大脑层 (LLM) | DeepSeek / Kimi / MiniMax / Gemini | 脚本生成、分镜拆解、Metadata 生成 |
| 视觉层 (生图) | Nano Banana (Gemini 3 Pro Image) | 4K 首帧锁定，主体一致性基础 |
| 动态层 (视频) | Kling 3.0 / Seedance 1.5 Pro | 双引擎智能路由，I2V 图生视频 |
| 配音层 (TTS) | MiniMax Speech 2.8 HD | 中文自然度业界领先，支持声音克隆 |
| 组装层 | Python + FFmpeg + WhisperX | xfade 转场 + 字幕烧录 + 音频混合 |
| 草稿层 | pyJianYingDraft | 自动生成剪映/CapCut 草稿工程 |
| 记忆层 | Mem0 (本地 SQLite / 云端同步) | 风格偏好数字孪生，越用越懂你 |
| 后端 | Python 3.10+ + FastAPI + LangGraph | 异步工作流编排，WebSocket 实时推送 |
| 前端 | React 19 + TailwindCSS + Wouter | 三栏工作台，无 Mock 数据 |

---

## 🚀 快速开始

### 📋 环境要求

| 软件 | 版本要求 | 说明 |
| :--- | :--- | :--- |
| **Python** | 3.10+ | 后端运行环境 |
| **Node.js** | 18+ | 前端构建环境 |
| **FFmpeg** | 4.0+ | 视频拼接（**必需**） |
| **Docker** | 20.0+ | 容器部署（可选） |

### 安装 FFmpeg

**macOS：**
```bash
brew install ffmpeg
```

**Ubuntu / Debian：**
```bash
sudo apt update && sudo apt install ffmpeg
```

**Windows：** 从 [FFmpeg 官网](https://ffmpeg.org/download.html) 下载并配置环境变量，验证：
```bash
ffmpeg -version
```

### 克隆与安装

```bash
# 1. 克隆项目
git clone https://github.com/OpenDemon/Pilipili-AutoVideo.git
cd Pilipili-AutoVideo

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 复制配置文件
cp configs/config.example.yaml configs/config.yaml
```

### 配置 API Keys

编辑 `configs/config.yaml`，填入你的 API Keys：

```yaml
llm:
  provider: deepseek          # deepseek | kimi | minimax | gemini
  api_key: "sk-xxxx"

image_gen:
  provider: nano_banana
  api_key: "AIzaSy-xxxx"      # Google AI Studio Key

video_gen:
  default_engine: kling       # kling | seedance | auto
  kling:
    api_key: "xxxx"
    api_secret: "xxxx"
  seedance:
    api_key: "xxxx"

tts:
  provider: minimax
  api_key: "xxxx"
  group_id: "xxxx"

memory:
  provider: local             # local | mem0_cloud
  # mem0_api_key: "m0-xxxx"  # 云端同步时填写
```

> 💡 也可以通过 Web UI（`http://localhost:3000/settings`）可视化配置，无需手动编辑 YAML。

### 方式一：CLI 运行（推荐调试）

```bash
# 基础用法
python cli/main.py run --topic "赛博朋克火星殖民，60秒，冷色调"

# 指定引擎
python cli/main.py run \
  --topic "古装宫廷爱情故事" \
  --engine seedance \
  --duration 90 \
  --add-subtitles

# 查看历史项目
python cli/main.py list

# 查看帮助
python cli/main.py --help
```

### 方式二：Web UI（推荐日常使用）

```bash
# 启动后端
python cli/main.py server

# 另开终端启动前端
cd frontend
pnpm install && pnpm dev

# 访问 http://localhost:3000
```

### 方式三：Docker Compose（推荐生产部署）

```bash
# 复制环境变量
cp .env.example .env
# 编辑 .env 填入 API Keys

# 一键启动
docker-compose up -d

# 访问 http://localhost:3000
```

---

## 📦 项目结构

```
Pilipili-AutoVideo/
├── api/
│   └── server.py           # FastAPI 后端 + WebSocket
├── cli/
│   └── main.py             # Click CLI 入口
├── core/
│   └── config.py           # 全局配置（Pydantic Settings）
├── modules/
│   ├── llm.py              # LLM 脚本生成（多 Provider）
│   ├── image_gen.py        # Nano Banana 首帧生图
│   ├── tts.py              # MiniMax TTS 配音 + 时长测量
│   ├── video_gen.py        # Kling 3.0 / Seedance 1.5 生视频
│   ├── assembler.py        # FFmpeg 拼接 + 字幕烧录
│   ├── jianying_draft.py   # 剪映草稿自动生成
│   └── memory.py           # Mem0 记忆系统
├── frontend/               # React 19 前端（三栏工作台）
├── skills/
│   └── SKILL.md            # Skill 封装说明
├── configs/
│   ├── config.example.yaml # 配置文件模板
│   └── config.yaml         # 本地配置（gitignore）
├── tests/
│   └── test_pipeline.py    # 单元测试（18 个测试用例）
├── data/
│   ├── outputs/            # 生成的视频和草稿
│   └── memory/             # 记忆数据库
├── docker-compose.yml      # Docker Compose 配置
├── Dockerfile.backend      # 后端 Dockerfile
├── requirements.txt        # Python 依赖
└── pyproject.toml          # 项目元数据 + CLI 安装配置
```

---

## 🎬 工作流详解

噼哩噼哩的核心工作流由 **LangGraph** 编排，分为以下阶段：

```
用户输入
  │
  ▼
① 脚本生成（LLM）
  │  DeepSeek/Kimi 将一句话扩展为结构化分镜脚本
  │  每个分镜包含：旁白文案、画面描述、运动描述、时长、转场
  │
  ▼
② 分镜审核（人工可选）
  │  Web UI 展示分镜列表，用户可逐一编辑后确认
  │  CLI 模式下自动跳过
  │
  ▼
③ 并行生成（首帧图像 + TTS 配音）
  │  Nano Banana 并行生成每个分镜的 4K 关键帧图像
  │  MiniMax TTS 并行生成每个分镜的配音，精确测量毫秒级时长
  │
  ▼
④ 视频生成（图生视频 I2V）
  │  以关键帧为首帧，以配音时长为 duration
  │  Kling 3.0（动作/产品类）或 Seedance 1.5（叙事/多角色类）
  │
  ▼
⑤ 拼接成片（FFmpeg）
  │  xfade 转场 + 背景音乐混合 + WhisperX 字幕烧录
  │
  ▼
⑥ 草稿导出（剪映/CapCut）
  │  自动生成草稿工程，保留所有分镜素材和时间轴
  │
  ▼
⑦ 记忆更新（Mem0）
     用户评分后，系统自动学习本次创作的风格偏好
```

---

## 🆚 与同类产品对比

| 对比维度 | LibTV | 火宝短剧 | **噼哩噼哩** |
| :--- | :---: | :---: | :---: |
| 交互范式 | 节点画布，手动触发 | 表单填写，按步操作 | **自然语言对话，一句话驱动** |
| 音画同步 | 手动剪辑对齐 | 未明确支持 | **先测配音时长，再控视频 duration** |
| 主体一致性 | 提示词引导 | 参考图上传 | **Nano Banana 首帧锁定 + Kling Reference API** |
| 最终交付 | 手动下载导入剪映 | 压制 MP4 | **自动生成剪映草稿 + MP4 双输出** |
| 记忆系统 | 无 | 无 | **Mem0 数字孪生，越用越懂你** |
| Agent 调用 | 无 | 无 | **封装为标准 Skill，可被任意 Agent 调用** |
| 部署方式 | 云端 SaaS | 云端 SaaS | **本地部署，数据完全自主** |

---

## 🧪 测试

```bash
# 运行所有单元测试（无需 API Key）
python -m pytest tests/test_pipeline.py -v -m "not api and not e2e"

# 运行 API 集成测试（需要真实 API Key）
python -m pytest tests/test_pipeline.py -v -m "api"

# 运行完整 E2E 测试
python -m pytest tests/test_pipeline.py -v -m "e2e"
```

当前测试覆盖：

| 测试模块 | 测试数量 | 说明 |
| :--- | :---: | :--- |
| 脚本解析 | 3 | JSON 解析、字段验证、边界情况 |
| TTS 工具 | 2 | 时长更新、格式验证 |
| 字幕工具 | 4 | SRT 时间格式、长文本分割、转场映射 |
| 配置系统 | 2 | 默认值、环境变量覆盖 |
| 记忆系统 | 3 | 本地存储、程序记忆、上下文管理 |
| 视频路由 | 3 | Kling/Seedance 智能路由 |
| 剪映草稿 | 1 | EDL 降级回退 |

---

## 🔌 Skill 调用

噼哩噼哩已封装为标准 Skill，可被任意 AI Agent 直接调用：

```markdown
# 在 Agent 中调用
请帮我生成一个关于"AI 芯片发展史"的 60 秒科普视频，蓝紫色科技风格。
```

Agent 会自动读取 `skills/SKILL.md` 并调用噼哩噼哩完成全部工作。

---

## 📝 常见问题

**Q: FFmpeg 未安装或找不到？**  
A: 确保 FFmpeg 已安装并在 PATH 中。运行 `ffmpeg -version` 验证。

**Q: 视频生成很慢，正常吗？**  
A: 视频生成依赖云端 API（Kling/Seedance），通常每个分镜需要 2-5 分钟。整个工作流的瓶颈在视频生成阶段，这是 API 侧的限制，与本地性能无关。

**Q: 如何切换 LLM 提供商？**  
A: 编辑 `configs/config.yaml` 中的 `llm.provider` 字段，或在 Web UI 设置页面切换。

**Q: 剪映草稿在哪里？**  
A: 生成完成后，草稿工程位于 `data/outputs/{project_id}/draft/`，将整个文件夹复制到剪映的草稿目录即可打开。

**Q: 支持哪些视频比例？**  
A: 目前支持 `9:16`（竖屏，抖音/快手）、`16:9`（横屏，B站/YouTube）、`1:1`（方形，微信视频号）。

**Q: 记忆系统的数据存在哪里？**  
A: 默认存储在 `data/memory/pilipili_memory.db`（本地 SQLite）。如果配置了 Mem0 Cloud API Key，会同步到云端。

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/amazing-feature`
3. 提交更改：`git commit -m 'feat: add amazing feature'`
4. 推送分支：`git push origin feature/amazing-feature`
5. 提交 Pull Request

---

## 📄 开源协议

本项目基于 [MIT License](LICENSE) 开源。

---

<p align="center">
  <b>噼哩噼哩 Pilipili-AutoVideo</b> · 本地部署 · 全自动 AI 视频代理<br/>
  如果这个项目对你有帮助，请给一个 ⭐ Star！
</p>
