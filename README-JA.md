# 🎬 噼哩噼哩 · Pilipili-AutoVideo

### 完全自動化 AI 動画エージェント · ローカルデプロイ · 一文で完成動画を生成

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-18%20passed-brightgreen)](#テスト)

[简体中文](README-CN.md) · [English](README.md) · [繁體中文](README-TW.md) · [日本語](README-JA.md) · [한국어](README-KO.md)

---

## 📖 プロジェクト概要

**噼哩噼哩（Pilipili-AutoVideo）** は、完全ローカルにデプロイできる全自動 AI 動画エージェントシステムです。一文を入力するだけで、システムが自動的にスクリプト企画 → キーフレーム画像生成 → TTS ナレーション → 動画クリップ生成 → FFmpeg 結合 → 字幕焼き込みを完了し、字幕付きの MP4 完成動画と CapCut/剪映ドラフトプロジェクトを出力します。

同類製品との主な差別化ポイント：

- **音声・映像の完全同期**：まず TTS ナレーションを生成してミリ秒単位の正確な長さを計測し、それを動画の `duration` として使用 — 音声と映像が常に完璧に同期
- **キーフレームロック戦略**：まず Nano Banana で 4K キーフレーム画像を生成し、その後 Image-to-Video（I2V）で動画クリップを生成 — 高い画質を保証し、被写体のドリフトを防止
- **デジタルツイン記憶**：Mem0 駆動の記憶システムがスタイルの好みを自動学習し、毎回の生成に過去の創作習慣を注入
- **Skill 統合**：ワークフロー全体が標準 Skill としてパッケージ化され、任意の AI エージェントから直接呼び出し可能

---

## 🎯 主な特徴

- 🤖 **自然言語駆動**：一文で記述するだけで、AI がすべての作業を自動完了
- 🎨 **プレミアム画質**：Nano Banana キーフレームロック + Kling 3.0 / Seedance 1.5 デュアルエンジン
- 🔊 **完全な音声・映像同期**：ナレーション長を先に計測し、動画長を制御 — ズレなし
- ✂️ **CapCut/剪映ドラフト出力**：AI が 90% を完成させ、人間が CapCut で残り 10% を微調整
- 🧠 **使うほど賢くなる**：Mem0 記憶システムが審美的な好みを自動学習
- 🔌 **エージェント呼び出し可能**：標準 Skill としてパッケージ化、より大きな自動化ワークフローにシームレスに統合

---

## 🛠️ 技術スタック

| レイヤー | 技術 | 説明 |
| :--- | :--- | :--- |
| ブレイン層 (LLM) | DeepSeek / Kimi / MiniMax / Gemini | スクリプト生成、絵コンテ分解、メタデータ生成 |
| ビジョン層 (画像) | Nano Banana (Gemini 3 Pro Image) | 4K キーフレームロック、被写体一貫性の基盤 |
| モーション層 (動画) | Kling 3.0 / Seedance 1.5 Pro | デュアルエンジンスマートルーティング、I2V 生成 |
| ボイス層 (TTS) | MiniMax Speech 2.8 HD | 中国語 TTS 業界最高水準、音声クローン対応 |
| アセンブリ層 | Python + FFmpeg + WhisperX | xfade トランジション + 字幕焼き込み + 音声ミックス |
| ドラフト層 | pyJianYingDraft | CapCut/剪映ドラフトプロジェクト自動生成 |
| 記憶層 | Mem0 (ローカル SQLite / クラウド同期) | スタイル好みのデジタルツイン |
| バックエンド | Python 3.10+ + FastAPI + LangGraph | 非同期ワークフロー編成、WebSocket リアルタイムプッシュ |
| フロントエンド | React 19 + TailwindCSS + Wouter | 3 ペインスタジオ、モックデータなし |

---

## 🚀 クイックスタート

### 📋 必要環境

| ソフトウェア | バージョン | 備考 |
| :--- | :--- | :--- |
| **Python** | 3.10+ | バックエンド実行環境 |
| **Node.js** | 18+ | フロントエンドビルド環境 |
| **FFmpeg** | 4.0+ | 動画結合（**必須**） |
| **Docker** | 20.0+ | コンテナデプロイ（オプション） |

### FFmpeg のインストール

**macOS：**
```bash
brew install ffmpeg
```

**Ubuntu / Debian：**
```bash
sudo apt update && sudo apt install ffmpeg
```

**Windows：** [FFmpeg 公式サイト](https://ffmpeg.org/download.html) からダウンロードして PATH に追加。確認：
```bash
ffmpeg -version
```

### クローンとインストール

```bash
# 1. リポジトリをクローン
git clone https://github.com/OpenDemon/Pilipili-AutoVideo.git
cd Pilipili-AutoVideo

# 2. Python 依存関係をインストール
pip install -r requirements.txt

# 3. 設定ファイルをコピー
cp configs/config.example.yaml configs/config.yaml
```

### API Keys の設定

`configs/config.yaml` を編集して API Keys を入力：

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

tts:
  provider: minimax
  api_key: "xxxx"
  group_id: "xxxx"
```

> 💡 Web UI（`http://localhost:3000/settings`）でも視覚的に設定可能です。YAML の手動編集は不要です。

### 方法 1：CLI（デバッグ推奨）

```bash
# 基本的な使用方法
python cli/main.py run --topic "サイバーパンク火星植民地、60秒、クールカラーパレット"

# エンジンを指定
python cli/main.py run \
  --topic "時代劇ロマンス" \
  --engine seedance \
  --duration 90 \
  --add-subtitles

# 過去のプロジェクトを一覧表示
python cli/main.py list
```

### 方法 2：Web UI（日常使用推奨）

```bash
# バックエンドを起動
python cli/main.py server

# 別のターミナルでフロントエンドを起動
cd frontend
pnpm install && pnpm dev

# http://localhost:3000 にアクセス
```

### 方法 3：Docker Compose（本番デプロイ推奨）

```bash
cp .env.example .env
# .env を編集して API Keys を入力
docker-compose up -d
# http://localhost:3000 にアクセス
```

---

## 🎬 ワークフロー詳細

```
ユーザー入力
  │
  ▼
① スクリプト生成（LLM）
  │  DeepSeek/Kimi が一文を構造化絵コンテスクリプトに展開
  │  各シーン：ナレーションテキスト、ビジュアル説明、モーション説明、尺、トランジション
  │
  ▼
② シーンレビュー（オプション）
  │  Web UI でシーンリストを表示、ユーザーが各シーンを編集後に確認
  │
  ▼
③ 並列生成（キーフレーム画像 + TTS ナレーション）
  │  Nano Banana が各シーンの 4K キーフレーム画像を並列生成
  │  MiniMax TTS が各シーンのナレーションを並列生成し、ミリ秒単位の長さを計測
  │
  ▼
④ 動画生成（Image-to-Video）
  │  キーフレームを最初のフレームとして使用、ナレーション長を duration として使用
  │  Kling 3.0（アクション/製品）または Seedance 1.5（ナラティブ/マルチキャラクター）
  │
  ▼
⑤ 結合（FFmpeg）
  │  xfade トランジション + BGM ミックス + WhisperX 字幕焼き込み
  │
  ▼
⑥ ドラフトエクスポート（CapCut/剪映）
  │  すべてのシーン素材とタイムラインを保持したドラフトプロジェクトを自動生成
  │
  ▼
⑦ 記憶更新（Mem0）
     ユーザー評価後、システムがスタイルの好みを自動学習
```

---

## 🆚 競合製品との比較

| 比較軸 | LibTV | 火宝短剧 | **噼哩噼哩** |
| :--- | :---: | :---: | :---: |
| インタラクション | ノードキャンバス、手動トリガー | フォーム入力、ステップ操作 | **自然言語、一文で駆動** |
| 音声・映像同期 | 手動編集 | 明示的サポートなし | **TTS 長さ計測 → 動画 duration 制御** |
| 被写体一貫性 | プロンプトガイド | 参照画像アップロード | **Nano Banana キーフレームロック + Kling Reference API** |
| 最終納品 | 手動 CapCut インポート | MP4 エクスポート | **CapCut ドラフト自動生成 + MP4 デュアル出力** |
| 記憶システム | なし | なし | **Mem0 デジタルツイン、使うほど賢くなる** |
| エージェント統合 | なし | なし | **標準 Skill、任意のエージェントから呼び出し可能** |

---

## 🧪 テスト

```bash
# すべてのユニットテストを実行（API Key 不要）
python -m pytest tests/test_pipeline.py -v -m "not api and not e2e"
```

現在のテストカバレッジ：**18 ユニットテスト、すべて合格**。

---

## 📝 よくある質問

**Q: FFmpeg が見つからない？**  
A: FFmpeg がインストールされ、PATH に含まれていることを確認してください。`ffmpeg -version` で確認できます。

**Q: 動画生成が遅いのは正常ですか？**  
A: 動画生成はクラウド API（Kling/Seedance）に依存しており、通常シーンごとに 2〜5 分かかります。これは API 側の制約であり、ローカルのパフォーマンスとは無関係です。

**Q: CapCut/剪映ドラフトはどこにありますか？**  
A: 生成完了後、ドラフトプロジェクトは `data/outputs/{project_id}/draft/` にあります。フォルダ全体を CapCut のドラフトディレクトリにコピーして開いてください。

---

## 📄 ライセンス

このプロジェクトは [MIT License](LICENSE) の下でオープンソース公開されています。

---

<p align="center">
  <b>噼哩噼哩 Pilipili-AutoVideo</b> · ローカルデプロイ · 完全自動化 AI 動画エージェント<br/>
  このプロジェクトが役に立ったら、⭐ Star をお願いします！
</p>
