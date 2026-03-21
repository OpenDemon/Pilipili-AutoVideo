# Pilipili-AutoVideo Skill

## 概述

噼哩噼哩 Pilipili-AutoVideo 是一个全自动 AI 视频生成代理，可将自然语言主题转化为完整的短视频（含配音、字幕、转场），并自动生成剪映草稿文件。

## 能力

- 从自然语言主题自动生成结构化分镜脚本（LLM 双层架构：生成 + Reflection）
- 并行生成高质量关键帧图片（Nano Banana / Gemini Image Generation）
- 并行生成 TTS 配音（MiniMax Speech-02-HD），精确测量时长
- 图生视频（Kling 3.0 / Seedance 1.5），智能路由引擎选择
- FFmpeg 自动拼接视频、混合音频、烧录字幕
- 生成剪映草稿文件（支持 pyJianYingDraft 或 EDL 回退）
- Mem0 记忆系统：越用越聪明，自动学习用户风格偏好
- 人工审核关卡：脚本生成后暂停，等待用户确认后再调用付费 API

## 使用方法

### 方式一：CLI（推荐，快速上手）

```bash
# 安装依赖
pip install -r requirements.txt

# 初始化配置
python cli/main.py config --init
# 编辑 configs/config.yaml，填入 API Keys

# 生成视频
python cli/main.py run --topic "AI 改变世界" --style "科技感，蓝紫色调"
python cli/main.py run --topic "西藏旅行" --duration 90 --engine seedance
python cli/main.py run --topic "美食探店" --no-review  # 跳过人工审核

# 仅生成脚本（不调用付费 API）
python cli/main.py script --topic "AI 改变世界" --output script.json
```

### 方式二：Web UI（可视化操作）

```bash
# Docker 一键启动
docker-compose up -d

# 访问 Web UI
open http://localhost:3000
```

### 方式三：Python API（程序集成）

```python
from core.config import get_config
from modules.llm import generate_script_sync
from modules.image_gen import generate_all_keyframes_sync
from modules.tts import generate_all_voiceovers_sync, update_scene_durations
from modules.video_gen import generate_all_video_clips_sync
from modules.assembler import assemble_video, AssemblyPlan
from modules.jianying_draft import generate_jianying_draft

config = get_config()

# 1. 生成脚本
script = generate_script_sync(topic="AI 改变世界", duration_hint=60, config=config)

# 2. 并行生成关键帧 + TTS
keyframes = generate_all_keyframes_sync(script.scenes, "output/keyframes", config=config)
audio = generate_all_voiceovers_sync(script.scenes, "output/audio", config=config)

# 3. 更新分镜时长（基于 TTS 实际时长）
script.scenes = update_scene_durations(script.scenes, audio)
audio_paths = {sid: path for sid, (path, _) in audio.items()}

# 4. 图生视频
clips = generate_all_video_clips_sync(script.scenes, keyframes, "output/clips", config=config)

# 5. 组装成片
plan = AssemblyPlan(
    scenes=script.scenes,
    video_clips=clips,
    audio_clips=audio_paths,
    output_path="output/final.mp4",
    temp_dir="output/temp",
)
assemble_video(plan)

# 6. 生成剪映草稿
generate_jianying_draft(script, clips, audio_paths, "output/draft")
```

## 配置说明

配置文件位于 `configs/config.yaml`（从 `config.example.yaml` 复制）。

支持的 LLM 提供商（选一个配置 API Key 即可）：
- DeepSeek（推荐，性价比高）
- Kimi（月之暗面）
- MiniMax
- 智谱 GLM-4
- Gemini
- OpenAI
- Ollama（本地，无需 API Key）

所有 API Keys 也可通过环境变量设置：
```bash
export DEEPSEEK_API_KEY="your-key"
export GEMINI_API_KEY="your-key"      # 同时用于图像生成
export MINIMAX_API_KEY="your-key"     # 同时用于 TTS
export KLING_API_KEY="your-key"
export KLING_API_SECRET="your-secret"
```

## 输出文件结构

```
data/outputs/{project_id}/
├── script.json          # 结构化分镜脚本
├── keyframes/           # 关键帧图片（PNG）
├── audio/               # TTS 配音（MP3）
├── clips/               # 视频片段（MP4）
├── output/
│   ├── {title}.mp4      # 最终成品视频
│   └── 剪映草稿/
│       ├── {title}.draft       # 剪映草稿（需 pyJianYingDraft）
│       ├── {title}.edl         # EDL 格式（Premiere/DaVinci）
│       ├── {title}.srt         # 字幕文件
│       └── {title}_project.json
└── temp/                # 临时文件（可删除）
```

## 注意事项

1. 首次运行前必须配置 API Keys
2. 视频生成（Kling/Seedance）耗时较长（每段约 1-3 分钟），请耐心等待
3. 支持断点续传：已生成的文件不会重复生成
4. 记忆系统数据存储在 `data/memory/mem0.db`，可随项目迁移
