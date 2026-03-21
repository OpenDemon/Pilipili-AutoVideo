# 🎬 Pilipili-AutoVideo · 噼哩噼哩

### Fully Automated AI Video Agent · Local Deployment · One Sentence to Final Cut

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-18%20passed-brightgreen)](#testing)

[简体中文](README-CN.md) · [English](README.md) · [繁體中文](README-TW.md) · [日本語](README-JA.md) · [한국어](README-KO.md)

---

> 📹 **Demo** — *Replace this line with a GIF or video recording of the full workflow: topic input → scene review → final video output.*
> `docs/demo.gif` (to be recorded — see [Contributing](#contributing))

---

## 📖 Overview

**Pilipili-AutoVideo (噼哩噼哩)** is a fully local, end-to-end AI video agent. Describe your video in one sentence — the system automatically handles script planning → keyframe image generation → TTS voiceover → video clip generation → FFmpeg assembly → subtitle burning, delivering a complete MP4 with subtitles and a CapCut/JianYing draft project for final human touch-ups.

Key differentiators from similar tools (LibTV, Huobao Drama):

- **Absolute Audio-Video Sync**: TTS voiceover is generated first and its exact millisecond duration is measured, then used to control video `duration` — audio and video are always perfectly aligned
- **Keyframe Lock Strategy**: Nano Banana generates a 4K keyframe image first, then Image-to-Video (I2V) produces the clip — ensuring consistently high visual quality with no subject drift
- **Digital Twin Memory**: Mem0-powered memory system learns your style preferences over time, injecting your creative habits into every new generation
- **Skill Integration**: The entire workflow is packaged as a standard Skill, callable by any AI Agent

---

## 🎯 Core Features

- 🤖 **Natural Language Driven**: One sentence → full video, no manual node operations required
- 🎨 **Premium Visual Quality**: Nano Banana keyframe lock + Kling 3.0 / Seedance 1.5 dual-engine, exceptional subject consistency
- 🔊 **Perfect Audio-Video Sync**: Measure voiceover duration first, control video duration accordingly — never misaligned
- ✂️ **CapCut/JianYing Draft Export**: AI handles 90%, you fine-tune the last 10% in CapCut
- 🧠 **Gets Smarter Over Time**: Mem0 memory system learns your aesthetic preferences with every project
- 🔌 **Agent-Callable**: Packaged as a standard Skill, seamlessly integrates into larger automation workflows

---

## 🛠️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Pilipili-AutoVideo Architecture             │
├─────────────────────────────────────────────────────────────┤
│  Frontend    React 19 + TailwindCSS · 3-panel Studio · WS   │
├─────────────────────────────────────────────────────────────┤
│  API Layer   FastAPI · WebSocket · REST · LangGraph Workflow │
├──────────────┬──────────────┬──────────────┬────────────────┤
│  Brain Layer │  Vision Layer│  Motion Layer│  Voice Layer   │
│  DeepSeek    │  Nano Banana │  Kling 3.0   │  MiniMax TTS   │
│  Kimi        │  (Gemini 3   │  Seedance    │  Speech 2.8 HD │
│  MiniMax LLM │   Pro Image) │  1.5 Pro     │                │
│  Gemini      │              │              │                │
├──────────────┴──────────────┴──────────────┴────────────────┤
│  Assembly    Python + FFmpeg · xfade transitions · WhisperX  │
├─────────────────────────────────────────────────────────────┤
│  Draft Layer pyJianYingDraft · Auto CapCut/JianYing Draft    │
├─────────────────────────────────────────────────────────────┤
│  Memory      Mem0 · Local SQLite · Style Preference Twin     │
└─────────────────────────────────────────────────────────────┘
```

| Layer | Technology | Description |
| :--- | :--- | :--- |
| Brain (LLM) | DeepSeek / Kimi / MiniMax / Gemini | Script generation, scene breakdown, metadata |
| Vision (Image) | Nano Banana (Gemini 3 Pro Image) | 4K keyframe lock, subject consistency foundation |
| Motion (Video) | Kling 3.0 / Seedance 1.5 Pro | Dual-engine smart routing, I2V generation |
| Voice (TTS) | MiniMax Speech 2.8 HD | Best-in-class Chinese TTS, voice cloning support |
| Assembly | Python + FFmpeg + WhisperX | xfade transitions + subtitle burning + audio mix |
| Draft | pyJianYingDraft | Auto-generate CapCut/JianYing draft projects |
| Memory | Mem0 (local SQLite / cloud sync) | Style preference digital twin |
| Backend | Python 3.10+ + FastAPI + LangGraph | Async workflow orchestration, WebSocket push |
| Frontend | React 19 + TailwindCSS + Wouter | 3-panel studio, no mock data |

---

## 🚀 Quick Start

### 📋 Requirements

| Software | Version | Notes |
| :--- | :--- | :--- |
| **Python** | 3.10+ | Backend runtime |
| **Node.js** | 18+ | Frontend build |
| **FFmpeg** | 4.0+ | Video assembly (**required**) |
| **Docker** | 20.0+ | Container deployment (optional) |

### Install FFmpeg

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu / Debian:**
```bash
sudo apt update && sudo apt install ffmpeg
```

**Windows:** Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH. Verify:
```bash
ffmpeg -version
```

### Clone & Install

```bash
# 1. Clone the repository
git clone https://github.com/OpenDemon/Pilipili-AutoVideo.git
cd Pilipili-AutoVideo

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Copy config template
cp configs/config.example.yaml configs/config.yaml
```

### Configure API Keys

Edit `configs/config.yaml`:

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
  # mem0_api_key: "m0-xxxx"  # Fill in for cloud sync
```

> 💡 You can also configure API keys visually at `http://localhost:3000/settings` — no YAML editing required.

### Option 1: CLI (Recommended for debugging)

```bash
# Basic usage
python cli/main.py run --topic "Cyberpunk Mars colony, 60 seconds, cold color palette"

# Specify engine
python cli/main.py run \
  --topic "Ancient palace romance story" \
  --engine seedance \
  --duration 90 \
  --add-subtitles

# List past projects
python cli/main.py list

# Help
python cli/main.py --help
```

### Option 2: Web UI (Recommended for daily use)

```bash
# Start backend
python cli/main.py server

# In another terminal, start frontend
cd frontend
pnpm install && pnpm dev

# Visit http://localhost:3000
```

### Option 3: Docker Compose (Recommended for production)

```bash
# Copy environment variables
cp .env.example .env
# Edit .env with your API keys

# Start all services
docker-compose up -d

# Visit http://localhost:3000
```

---

## 📦 Project Structure

```
Pilipili-AutoVideo/
├── api/
│   └── server.py           # FastAPI backend + WebSocket
├── cli/
│   └── main.py             # Click CLI entrypoint
├── core/
│   └── config.py           # Global config (Pydantic Settings)
├── modules/
│   ├── llm.py              # LLM script generation (multi-provider)
│   ├── image_gen.py        # Nano Banana keyframe generation
│   ├── tts.py              # MiniMax TTS + duration measurement
│   ├── video_gen.py        # Kling 3.0 / Seedance 1.5 I2V
│   ├── assembler.py        # FFmpeg assembly + subtitle burning
│   ├── jianying_draft.py   # CapCut/JianYing draft generation
│   └── memory.py           # Mem0 memory system
├── frontend/               # React 19 frontend (3-panel studio)
├── skills/
│   └── SKILL.md            # Skill packaging spec
├── configs/
│   ├── config.example.yaml # Config template
│   └── config.yaml         # Local config (gitignored)
├── tests/
│   └── test_pipeline.py    # Unit tests (18 test cases)
├── data/
│   ├── outputs/            # Generated videos and drafts
│   └── memory/             # Memory database
├── docker-compose.yml
├── Dockerfile.backend
├── requirements.txt
└── pyproject.toml
```

---

## 🎬 Workflow Deep Dive

The core workflow is orchestrated by **LangGraph** in the following stages:

```
User Input
  │
  ▼
① Script Generation (LLM)
  │  DeepSeek/Kimi expands one sentence into a structured storyboard
  │  Each scene: voiceover text, visual description, motion description,
  │              duration, transition, camera motion
  │
  ▼
② Scene Review (optional human step)
  │  Web UI shows scene list; user can edit each scene before confirming
  │  CLI mode: auto-approved
  │
  ▼
③ Parallel Generation (Keyframe Images + TTS Voiceover)
  │  Nano Banana generates 4K keyframe images for each scene in parallel
  │  MiniMax TTS generates voiceover for each scene, measuring exact ms duration
  │
  ▼
④ Video Generation (Image-to-Video)
  │  Uses keyframe as first frame, voiceover duration as video duration
  │  Kling 3.0 (action/product) or Seedance 1.5 (narrative/multi-character)
  │
  ▼
⑤ Assembly (FFmpeg)
  │  xfade transitions + background music mixing + WhisperX subtitle burning
  │
  ▼
⑥ Draft Export (CapCut/JianYing)
  │  Auto-generates draft project preserving all scene assets and timeline
  │
  ▼
⑦ Memory Update (Mem0)
     After user rating, system learns style preferences for future generations
```

---

## 🆚 Comparison

| Dimension | LibTV | Huobao Drama | **Pilipili** |
| :--- | :---: | :---: | :---: |
| Interaction | Node canvas, manual trigger | Form-based, step-by-step | **Natural language, one sentence** |
| Audio-Video Sync | Manual editing | Not explicitly supported | **Measure TTS duration → control video duration** |
| Subject Consistency | Prompt guidance | Reference image upload | **Nano Banana keyframe lock + Kling Reference API** |
| Final Delivery | Manual import to CapCut | MP4 export | **Auto CapCut draft + MP4 dual output** |
| Memory System | None | None | **Mem0 digital twin, learns your style** |
| Agent Integration | None | None | **Standard Skill, callable by any Agent** |
| Deployment | Cloud SaaS | Cloud SaaS | **Local deployment, full data ownership** |

---

## 🧪 Testing

```bash
# Run all unit tests (no API keys required)
python -m pytest tests/test_pipeline.py -v -m "not api and not e2e"

# Run API integration tests (real API keys required)
python -m pytest tests/test_pipeline.py -v -m "api"

# Run full E2E tests
python -m pytest tests/test_pipeline.py -v -m "e2e"
```

Current test coverage: **18 unit tests, all passing**.

---

## 🔌 Skill Integration

Pilipili-AutoVideo is packaged as a standard Skill, callable by any AI Agent:

```markdown
# In an Agent session
Please generate a 60-second science explainer video about "The History of AI Chips",
blue-purple tech aesthetic.
```

The Agent will automatically read `skills/SKILL.md` and invoke Pilipili to complete the entire workflow.

---

## 📝 FAQ

**Q: FFmpeg not found?**  
A: Ensure FFmpeg is installed and in your PATH. Run `ffmpeg -version` to verify.

**Q: Video generation is slow — is that normal?**  
A: Video generation relies on cloud APIs (Kling/Seedance), typically 2-5 minutes per scene. This is an API-side constraint, not a local performance issue.

**Q: How do I switch LLM providers?**  
A: Edit `llm.provider` in `configs/config.yaml`, or use the Settings page in the Web UI.

**Q: Where is the CapCut/JianYing draft?**  
A: After generation, the draft project is at `data/outputs/{project_id}/draft/`. Copy the entire folder to CapCut's draft directory to open it.

**Q: What aspect ratios are supported?**  
A: `9:16` (portrait, TikTok/Reels), `16:9` (landscape, YouTube), `1:1` (square, Instagram).

---

## 🤝 Contributing

Issues and Pull Requests are welcome!

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'feat: add amazing feature'`
4. Push the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

<p align="center">
  <b>Pilipili-AutoVideo · 噼哩噼哩</b> · Local Deployment · Fully Automated AI Video Agent<br/>
  If this project helps you, please give it a ⭐ Star!
</p>
