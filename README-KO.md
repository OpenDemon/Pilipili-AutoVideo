# 🎬 噼哩噼哩 · Pilipili-AutoVideo

### 완전 자동화 AI 영상 에이전트 · 로컬 배포 · 한 문장으로 완성 영상 생성

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-18%20passed-brightgreen)](#테스트)

[简体中文](README-CN.md) · [English](README.md) · [繁體中文](README-TW.md) · [日本語](README-JA.md) · [한국어](README-KO.md)

---

## 📖 프로젝트 소개

**噼哩噼哩（Pilipili-AutoVideo）** 는 완전히 로컬에 배포되는 완전 자동화 AI 영상 에이전트 시스템입니다. 한 문장을 입력하면 시스템이 자동으로 스크립트 기획 → 키프레임 이미지 생성 → TTS 나레이션 → 영상 클립 생성 → FFmpeg 편집 → 자막 삽입을 완료하여 자막이 포함된 MP4 완성 영상과 CapCut/剪映 초안 프로젝트를 출력합니다.

유사 제품과의 핵심 차별점：

- **완벽한 오디오-비디오 동기화**：먼저 TTS 나레이션을 생성하고 밀리초 단위로 정확한 길이를 측정한 후, 이를 영상 `duration` 제어에 사용 — 오디오와 비디오가 항상 완벽하게 동기화
- **키프레임 잠금 전략**：먼저 Nano Banana로 4K 키프레임 이미지를 생성한 후, 이미지-투-비디오(I2V)로 영상 클립 생성 — 높은 화질 보장, 피사체 드리프트 방지
- **디지털 트윈 메모리**：Mem0 기반 메모리 시스템이 스타일 선호도를 자동으로 학습하여 매번 생성 시 과거 창작 습관을 주입
- **Skill 통합**：전체 워크플로우가 표준 Skill로 패키징되어 모든 AI 에이전트에서 직접 호출 가능

---

## 🎯 핵심 가치

- 🤖 **자연어 구동**：한 문장 설명만으로 AI가 모든 작업을 자동 완료
- 🎨 **프리미엄 화질**：Nano Banana 키프레임 잠금 + Kling 3.0 / Seedance 1.5 듀얼 엔진
- 🔊 **완벽한 오디오-비디오 동기화**：나레이션 길이를 먼저 측정하고 영상 길이를 제어 — 절대 어긋나지 않음
- ✂️ **CapCut/剪映 초안 출력**：AI가 90% 완성, 사람이 CapCut에서 나머지 10% 미세 조정
- 🧠 **사용할수록 더 똑똑해짐**：Mem0 메모리 시스템이 미적 선호도를 자동 학습
- 🔌 **에이전트 호출 가능**：표준 Skill로 패키징되어 더 큰 자동화 워크플로우에 원활하게 통합

---

## 🛠️ 기술 스택

| 레이어 | 기술 | 설명 |
| :--- | :--- | :--- |
| 브레인 레이어 (LLM) | DeepSeek / Kimi / MiniMax / Gemini | 스크립트 생성, 장면 분해, 메타데이터 생성 |
| 비전 레이어 (이미지) | Nano Banana (Gemini 3 Pro Image) | 4K 키프레임 잠금, 피사체 일관성 기반 |
| 모션 레이어 (영상) | Kling 3.0 / Seedance 1.5 Pro | 듀얼 엔진 스마트 라우팅, I2V 생성 |
| 보이스 레이어 (TTS) | MiniMax Speech 2.8 HD | 중국어 TTS 업계 최고 수준, 음성 복제 지원 |
| 어셈블리 레이어 | Python + FFmpeg + WhisperX | xfade 전환 + 자막 삽입 + 오디오 믹스 |
| 초안 레이어 | pyJianYingDraft | CapCut/剪映 초안 프로젝트 자동 생성 |
| 메모리 레이어 | Mem0 (로컬 SQLite / 클라우드 동기화) | 스타일 선호도 디지털 트윈 |
| 백엔드 | Python 3.10+ + FastAPI + LangGraph | 비동기 워크플로우 편성, WebSocket 실시간 푸시 |
| 프론트엔드 | React 19 + TailwindCSS + Wouter | 3패널 스튜디오, 목업 데이터 없음 |

---

## 🚀 빠른 시작

### 📋 환경 요구사항

| 소프트웨어 | 버전 | 비고 |
| :--- | :--- | :--- |
| **Python** | 3.10+ | 백엔드 실행 환경 |
| **Node.js** | 18+ | 프론트엔드 빌드 환경 |
| **FFmpeg** | 4.0+ | 영상 편집 (**필수**) |
| **Docker** | 20.0+ | 컨테이너 배포 (선택사항) |

### FFmpeg 설치

**macOS：**
```bash
brew install ffmpeg
```

**Ubuntu / Debian：**
```bash
sudo apt update && sudo apt install ffmpeg
```

**Windows：** [FFmpeg 공식 사이트](https://ffmpeg.org/download.html)에서 다운로드하여 PATH에 추가. 확인：
```bash
ffmpeg -version
```

### 클론 및 설치

```bash
# 1. 저장소 클론
git clone https://github.com/OpenDemon/Pilipili-AutoVideo.git
cd Pilipili-AutoVideo

# 2. Python 의존성 설치
pip install -r requirements.txt

# 3. 설정 파일 복사
cp configs/config.example.yaml configs/config.yaml
```

### API Keys 설정

`configs/config.yaml`을 편집하여 API Keys 입력：

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

> 💡 Web UI(`http://localhost:3000/settings`)에서도 시각적으로 설정 가능합니다. YAML 수동 편집이 필요 없습니다.

### 방법 1：CLI (디버깅 권장)

```bash
# 기본 사용법
python cli/main.py run --topic "사이버펑크 화성 식민지, 60초, 쿨 컬러 팔레트"

# 엔진 지정
python cli/main.py run \
  --topic "사극 궁중 로맨스" \
  --engine seedance \
  --duration 90 \
  --add-subtitles

# 이전 프로젝트 목록 보기
python cli/main.py list
```

### 방법 2：Web UI (일상 사용 권장)

```bash
# 백엔드 시작
python cli/main.py server

# 다른 터미널에서 프론트엔드 시작
cd frontend
pnpm install && pnpm dev

# http://localhost:3000 접속
```

### 방법 3：Docker Compose (프로덕션 배포 권장)

```bash
cp .env.example .env
# .env를 편집하여 API Keys 입력
docker-compose up -d
# http://localhost:3000 접속
```

---

## 🎬 워크플로우 상세

```
사용자 입력
  │
  ▼
① 스크립트 생성 (LLM)
  │  DeepSeek/Kimi가 한 문장을 구조화된 스토리보드 스크립트로 확장
  │  각 장면: 나레이션 텍스트, 비주얼 설명, 모션 설명, 길이, 전환
  │
  ▼
② 장면 검토 (선택적 사람 단계)
  │  Web UI에서 장면 목록 표시, 사용자가 각 장면 편집 후 확인
  │
  ▼
③ 병렬 생성 (키프레임 이미지 + TTS 나레이션)
  │  Nano Banana가 각 장면의 4K 키프레임 이미지를 병렬 생성
  │  MiniMax TTS가 각 장면의 나레이션을 병렬 생성하고 밀리초 단위 길이 측정
  │
  ▼
④ 영상 생성 (이미지-투-비디오)
  │  키프레임을 첫 번째 프레임으로, 나레이션 길이를 duration으로 사용
  │  Kling 3.0 (액션/제품) 또는 Seedance 1.5 (내러티브/멀티 캐릭터)
  │
  ▼
⑤ 편집 (FFmpeg)
  │  xfade 전환 + BGM 믹스 + WhisperX 자막 삽입
  │
  ▼
⑥ 초안 내보내기 (CapCut/剪映)
  │  모든 장면 소재와 타임라인을 보존한 초안 프로젝트 자동 생성
  │
  ▼
⑦ 메모리 업데이트 (Mem0)
     사용자 평가 후 시스템이 스타일 선호도를 자동 학습
```

---

## 🆚 경쟁 제품 비교

| 비교 항목 | LibTV | 火宝短剧 | **噼哩噼哩** |
| :--- | :---: | :---: | :---: |
| 인터랙션 방식 | 노드 캔버스, 수동 트리거 | 폼 입력, 단계별 조작 | **자연어 대화, 한 문장으로 구동** |
| 오디오-비디오 동기화 | 수동 편집 | 명시적 지원 없음 | **TTS 길이 측정 → 영상 duration 제어** |
| 피사체 일관성 | 프롬프트 가이드 | 참조 이미지 업로드 | **Nano Banana 키프레임 잠금 + Kling Reference API** |
| 최종 납품 | 수동 CapCut 가져오기 | MP4 내보내기 | **CapCut 초안 자동 생성 + MP4 이중 출력** |
| 메모리 시스템 | 없음 | 없음 | **Mem0 디지털 트윈, 사용할수록 더 똑똑해짐** |
| 에이전트 통합 | 없음 | 없음 | **표준 Skill, 모든 에이전트에서 호출 가능** |
| 배포 방식 | 클라우드 SaaS | 클라우드 SaaS | **로컬 배포, 완전한 데이터 자주권** |

---

## 🧪 테스트

```bash
# 모든 유닛 테스트 실행 (API Key 불필요)
python -m pytest tests/test_pipeline.py -v -m "not api and not e2e"

# API 통합 테스트 실행 (실제 API Key 필요)
python -m pytest tests/test_pipeline.py -v -m "api"
```

현재 테스트 커버리지：**18개 유닛 테스트, 모두 통과**.

---

## 📝 자주 묻는 질문

**Q: FFmpeg를 찾을 수 없나요?**  
A: FFmpeg가 설치되어 있고 PATH에 포함되어 있는지 확인하세요. `ffmpeg -version`으로 확인할 수 있습니다.

**Q: 영상 생성이 느린 것이 정상인가요?**  
A: 영상 생성은 클라우드 API(Kling/Seedance)에 의존하며, 일반적으로 장면당 2~5분이 소요됩니다. 이는 API 측의 제약이며 로컬 성능과는 무관합니다.

**Q: LLM 제공업체를 어떻게 변경하나요?**  
A: `configs/config.yaml`의 `llm.provider` 필드를 편집하거나 Web UI 설정 페이지에서 변경하세요.

**Q: CapCut/剪映 초안은 어디에 있나요?**  
A: 생성 완료 후 초안 프로젝트는 `data/outputs/{project_id}/draft/`에 있습니다. 전체 폴더를 CapCut의 초안 디렉토리에 복사하면 열 수 있습니다.

**Q: 어떤 화면 비율을 지원하나요?**  
A: `9:16`(세로, TikTok/릴스), `16:9`(가로, YouTube), `1:1`(정사각형, 인스타그램).

---

## 🤝 기여 가이드

이슈와 풀 리퀘스트를 환영합니다!

1. 저장소를 Fork하세요
2. 기능 브랜치 생성：`git checkout -b feature/amazing-feature`
3. 변경사항 커밋：`git commit -m 'feat: add amazing feature'`
4. 브랜치 푸시：`git push origin feature/amazing-feature`
5. 풀 리퀘스트 제출

---

## 📄 오픈소스 라이선스

이 프로젝트는 [MIT License](LICENSE) 하에 오픈소스로 공개됩니다.

---

<p align="center">
  <b>噼哩噼哩 Pilipili-AutoVideo</b> · 로컬 배포 · 완전 자동화 AI 영상 에이전트<br/>
  이 프로젝트가 도움이 되셨다면 ⭐ Star를 눌러주세요!
</p>
