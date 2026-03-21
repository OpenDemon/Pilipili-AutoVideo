# 🎬 噼哩噼哩 · Pilipili-AutoVideo

### 全自動 AI 影片代理 · 本地部署 · 一句話生成成片

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-18%20passed-brightgreen)](#測試)

[简体中文](README-CN.md) · [English](README.md) · [繁體中文](README-TW.md) · [日本語](README-JA.md) · [한국어](README-KO.md)

---

## 📖 專案簡介

**噼哩噼哩（Pilipili-AutoVideo）** 是一個完全部署在本地的全自動 AI 影片代理系統。輸入一句話，系統自動完成腳本策劃 → 首幀圖像生成 → TTS 配音 → 影片片段生成 → FFmpeg 拼接成片 → 字幕燒錄，最終輸出帶字幕的 MP4 成品影片，並同步生成剪映草稿工程，供人類在剪映裡進行最後 10% 的微調。

與同類產品相比，噼哩噼哩的核心差異在於：

- **音畫絕對同步**：先生成 TTS 配音並精確測量毫秒級時長，再以此控制影片 `duration`，徹底告別音畫錯位
- **首幀鎖定策略**：先用 Nano Banana 生成 4K 關鍵幀圖像，再用圖生影片（I2V），畫質下限極高，主體不漂移
- **數位孿生記憶**：Mem0 驅動的記憶系統，自動學習你的風格偏好，每次生成都會注入歷史創作習慣
- **Skill 封裝**：整個工作流被封裝為標準 Skill，可被任意 AI Agent 直接呼叫

---

## 🎯 核心價值

- 🤖 **自然語言驅動**：一句話描述，AI 自動完成全部工作，無需手動操作任何節點
- 🎨 **頂級畫質下限**：Nano Banana 首幀鎖定 + Kling 3.0 / Seedance 1.5 雙引擎，主體一致性極強
- 🔊 **音畫絕對同步**：先測配音時長，再控影片時長，永遠不會出現「配音還沒說完影片就結束了」
- ✂️ **剪映草稿輸出**：自動生成 CapCut/剪映草稿工程，AI 完成 90%，人類在剪映裡微調 10%
- 🧠 **越用越懂你**：Mem0 記憶系統自動學習風格偏好，每次生成都更貼合你的審美
- 🔌 **Agent 可呼叫**：封裝為標準 Skill，可被任意 Agent 直接呼叫，無縫整合到更大的自動化工作流

---

## 🛠️ 技術架構

| 層級 | 技術選型 | 說明 |
| :--- | :--- | :--- |
| 大腦層 (LLM) | DeepSeek / Kimi / MiniMax / Gemini | 腳本生成、分鏡拆解、Metadata 生成 |
| 視覺層 (生圖) | Nano Banana (Gemini 3 Pro Image) | 4K 首幀鎖定，主體一致性基礎 |
| 動態層 (影片) | Kling 3.0 / Seedance 1.5 Pro | 雙引擎智慧路由，I2V 圖生影片 |
| 配音層 (TTS) | MiniMax Speech 2.8 HD | 中文自然度業界領先，支援聲音複製 |
| 組裝層 | Python + FFmpeg + WhisperX | xfade 轉場 + 字幕燒錄 + 音訊混合 |
| 草稿層 | pyJianYingDraft | 自動生成剪映/CapCut 草稿工程 |
| 記憶層 | Mem0 (本地 SQLite / 雲端同步) | 風格偏好數位孿生，越用越懂你 |
| 後端 | Python 3.10+ + FastAPI + LangGraph | 非同步工作流編排，WebSocket 即時推送 |
| 前端 | React 19 + TailwindCSS + Wouter | 三欄工作台，無 Mock 資料 |

---

## 🚀 快速開始

### 📋 環境需求

| 軟體 | 版本需求 | 說明 |
| :--- | :--- | :--- |
| **Python** | 3.10+ | 後端執行環境 |
| **Node.js** | 18+ | 前端建置環境 |
| **FFmpeg** | 4.0+ | 影片拼接（**必需**） |
| **Docker** | 20.0+ | 容器部署（可選） |

### 安裝 FFmpeg

**macOS：**
```bash
brew install ffmpeg
```

**Ubuntu / Debian：**
```bash
sudo apt update && sudo apt install ffmpeg
```

**Windows：** 從 [FFmpeg 官網](https://ffmpeg.org/download.html) 下載並設定環境變數，驗證：
```bash
ffmpeg -version
```

### 複製與安裝

```bash
# 1. 複製專案
git clone https://github.com/OpenDemon/Pilipili-AutoVideo.git
cd Pilipili-AutoVideo

# 2. 安裝 Python 相依套件
pip install -r requirements.txt

# 3. 複製設定檔
cp configs/config.example.yaml configs/config.yaml
```

### 設定 API Keys

編輯 `configs/config.yaml`，填入你的 API Keys：

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
```

> 💡 也可以透過 Web UI（`http://localhost:3000/settings`）視覺化設定，無需手動編輯 YAML。

### 方式一：CLI 執行（推薦除錯）

```bash
# 基本用法
python cli/main.py run --topic "賽博龐克火星殖民，60秒，冷色調"

# 指定引擎
python cli/main.py run \
  --topic "古裝宮廷愛情故事" \
  --engine seedance \
  --duration 90 \
  --add-subtitles

# 查看歷史專案
python cli/main.py list
```

### 方式二：Web UI（推薦日常使用）

```bash
# 啟動後端
python cli/main.py server

# 另開終端啟動前端
cd frontend
pnpm install && pnpm dev

# 訪問 http://localhost:3000
```

### 方式三：Docker Compose（推薦生產部署）

```bash
cp .env.example .env
# 編輯 .env 填入 API Keys
docker-compose up -d
# 訪問 http://localhost:3000
```

---

## 🎬 工作流詳解

```
使用者輸入
  │
  ▼
① 腳本生成（LLM）
  │  DeepSeek/Kimi 將一句話擴展為結構化分鏡腳本
  │
  ▼
② 分鏡審核（人工可選）
  │  Web UI 展示分鏡列表，使用者可逐一編輯後確認
  │
  ▼
③ 並行生成（首幀圖像 + TTS 配音）
  │  Nano Banana 並行生成每個分鏡的 4K 關鍵幀圖像
  │  MiniMax TTS 並行生成每個分鏡的配音，精確測量毫秒級時長
  │
  ▼
④ 影片生成（圖生影片 I2V）
  │  以關鍵幀為首幀，以配音時長為 duration
  │  Kling 3.0（動作/產品類）或 Seedance 1.5（敘事/多角色類）
  │
  ▼
⑤ 拼接成片（FFmpeg）
  │  xfade 轉場 + 背景音樂混合 + WhisperX 字幕燒錄
  │
  ▼
⑥ 草稿匯出（剪映/CapCut）
  │  自動生成草稿工程，保留所有分鏡素材和時間軸
  │
  ▼
⑦ 記憶更新（Mem0）
     使用者評分後，系統自動學習本次創作的風格偏好
```

---

## 🆚 與同類產品對比

| 對比維度 | LibTV | 火寶短劇 | **噼哩噼哩** |
| :--- | :---: | :---: | :---: |
| 互動範式 | 節點畫布，手動觸發 | 表單填寫，按步操作 | **自然語言對話，一句話驅動** |
| 音畫同步 | 手動剪輯對齊 | 未明確支援 | **先測配音時長，再控影片 duration** |
| 主體一致性 | 提示詞引導 | 參考圖上傳 | **Nano Banana 首幀鎖定 + Kling Reference API** |
| 最終交付 | 手動下載匯入剪映 | 壓製 MP4 | **自動生成剪映草稿 + MP4 雙輸出** |
| 記憶系統 | 無 | 無 | **Mem0 數位孿生，越用越懂你** |
| Agent 呼叫 | 無 | 無 | **封裝為標準 Skill，可被任意 Agent 呼叫** |

---

## 🧪 測試

```bash
# 執行所有單元測試（無需 API Key）
python -m pytest tests/test_pipeline.py -v -m "not api and not e2e"
```

目前測試覆蓋：**18 個單元測試，全部通過**。

---

## 📝 常見問題

**Q: FFmpeg 未安裝或找不到？**  
A: 確保 FFmpeg 已安裝並在 PATH 中。執行 `ffmpeg -version` 驗證。

**Q: 影片生成很慢，正常嗎？**  
A: 影片生成依賴雲端 API（Kling/Seedance），通常每個分鏡需要 2-5 分鐘。這是 API 側的限制，與本地效能無關。

**Q: 剪映草稿在哪裡？**  
A: 生成完成後，草稿工程位於 `data/outputs/{project_id}/draft/`，將整個資料夾複製到剪映的草稿目錄即可開啟。

---

## 📄 開源授權

本專案基於 [MIT License](LICENSE) 開源。

---

<p align="center">
  <b>噼哩噼哩 Pilipili-AutoVideo</b> · 本地部署 · 全自動 AI 影片代理<br/>
  如果這個專案對你有幫助，請給一個 ⭐ Star！
</p>
