# 🪟 Windows 完整部署教程

> 适用于 Windows 10 / Windows 11，全程命令行操作，预计耗时 **20-30 分钟**。

---

## 目录

1. [环境准备](#1-环境准备)
2. [克隆项目](#2-克隆项目)
3. [安装 Python 依赖](#3-安装-python-依赖)
4. [安装 FFmpeg](#4-安装-ffmpeg重要)
5. [配置 API Keys](#5-配置-api-keys)
6. [启动后端服务](#6-启动后端服务)
7. [启动前端界面](#7-启动前端界面)
8. [第一次生成视频](#8-第一次生成视频)
9. [API Keys 申请指南](#9-api-keys-申请指南)
10. [常见问题排查](#10-常见问题排查)

---

## 1. 环境准备

### 1.1 安装 Python 3.10+

1. 打开 [Python 官网](https://www.python.org/downloads/) 下载 **Python 3.11**（推荐）
2. 运行安装包时，**务必勾选 "Add Python to PATH"**（底部复选框）
3. 验证安装：

```cmd
python --version
```

应输出 `Python 3.11.x`。

### 1.2 安装 Node.js 18+

1. 打开 [Node.js 官网](https://nodejs.org/) 下载 **LTS 版本**
2. 一路默认安装即可
3. 验证安装：

```cmd
node --version
npm --version
```

### 1.3 安装 Git

1. 打开 [Git 官网](https://git-scm.com/download/win) 下载安装包
2. 安装时选择 **"Git Bash"** 和 **"Git from the command line"**
3. 验证安装：

```cmd
git --version
```

### 1.4 安装 pnpm（前端包管理器）

```cmd
npm install -g pnpm
```

---

## 2. 克隆项目

打开 **命令提示符（CMD）** 或 **PowerShell**，执行：

```cmd
cd C:\Users\你的用户名\Desktop
git clone https://github.com/OpenDemon/Pilipili-AutoVideo.git
cd Pilipili-AutoVideo
```

> 💡 **建议路径不要包含中文或空格**，例如放在 `C:\Projects\Pilipili-AutoVideo`

---

## 3. 安装 Python 依赖

```cmd
pip install -r requirements.txt
```

> ⏳ 首次安装约需 3-5 分钟，请耐心等待。
>
> 如果网速较慢，可使用国内镜像加速：
> ```cmd
> pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
> ```

安装完成后验证：

```cmd
python -m pytest tests/test_pipeline.py -v -m "not api and not e2e"
```

应显示 **18 passed**。

---

## 4. 安装 FFmpeg（重要！）

FFmpeg 是视频拼接的核心工具，**必须安装**。

### 方法一：使用 winget（Windows 10/11 推荐）

打开 **PowerShell（管理员）**：

```powershell
winget install Gyan.FFmpeg
```

安装完成后**重启命令提示符**，验证：

```cmd
ffmpeg -version
```

### 方法二：手动安装

1. 打开 [FFmpeg Builds](https://www.gyan.dev/ffmpeg/builds/) 下载 `ffmpeg-release-essentials.zip`
2. 解压到 `C:\ffmpeg\`，确保目录结构为：
   ```
   C:\ffmpeg\
   └── bin\
       ├── ffmpeg.exe
       ├── ffprobe.exe
       └── ffplay.exe
   ```
3. 将 `C:\ffmpeg\bin` 添加到系统 PATH：
   - 右键"此电脑" → 属性 → 高级系统设置 → 环境变量
   - 在"系统变量"中找到 `Path`，点击"编辑"
   - 点击"新建"，输入 `C:\ffmpeg\bin`
   - 确定保存，**重启命令提示符**
4. 验证：
   ```cmd
   ffmpeg -version
   ```

---

## 5. 配置 API Keys

### 5.1 复制配置文件

```cmd
copy configs\config.example.yaml configs\config.yaml
```

### 5.2 编辑配置文件

用记事本或 VS Code 打开 `configs\config.yaml`：

```cmd
notepad configs\config.yaml
```

### 5.3 最小化配置（只需填 3 个 Key 即可运行）

找到以下字段并填入你的 API Keys：

```yaml
# ① LLM 大脑（选一个填即可，推荐 DeepSeek）
llm:
  default_provider: "deepseek"
  deepseek:
    api_key: "sk-xxxxxxxxxxxxxxxxxxxxxxxx"   # ← 填入 DeepSeek API Key

# ② 生图（Nano Banana / Gemini）
image_gen:
  api_key: "AIzaSyxxxxxxxxxxxxxxxxxxxxxxx"   # ← 填入 Google AI Studio Key

# ③ 视频生成（Kling 或 Seedance 选一个）
video_gen:
  default_provider: "kling"
  kling:
    api_key: "xxxxxxxxxxxxxxxxxxxxxxxx"       # ← 填入 Kling API Key
    api_secret: "xxxxxxxxxxxxxxxxxxxxxxxx"    # ← 填入 Kling API Secret

# ④ TTS 配音（MiniMax）
tts:
  minimax:
    api_key: "xxxxxxxxxxxxxxxxxxxxxxxx"       # ← 填入 MiniMax API Key
```

> 💡 **不知道去哪申请 API Key？** 见本文第 [9 节](#9-api-keys-申请指南)

### 5.4 验证配置

```cmd
python cli\main.py config --show
```

应显示各配置项（API Key 会被隐藏显示为 `sk-****`）。

---

## 6. 启动后端服务

```cmd
python cli\main.py server
```

成功启动后应看到：

```
  ██████╗ ██╗██╗     ██╗██████╗ ██╗██╗     ██╗
  ██╔══██╗██║██║     ██║██╔══██╗██║██║     ██║
  ██████╔╝██║██║     ██║██████╔╝██║██║     ██║
  ...
  噼哩噼哩 Pilipili-AutoVideo v0.1.0
  
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

后端服务运行在 **http://localhost:8000**，保持此窗口开启。

> 💡 可以用浏览器访问 http://localhost:8000/health 验证后端是否正常运行，应返回 `{"status":"ok"}`

---

## 7. 启动前端界面

**新开一个命令提示符窗口**，进入前端目录：

```cmd
cd C:\Users\你的用户名\Desktop\Pilipili-AutoVideo\frontend
pnpm install
pnpm dev
```

成功启动后应看到：

```
  VITE v5.x.x  ready in xxx ms

  ➜  Local:   http://localhost:3000/
  ➜  Network: http://192.168.x.x:3000/
```

打开浏览器访问 **http://localhost:3000**，即可看到噼哩噼哩工作台界面。

---

## 8. 第一次生成视频

### 方式一：通过 Web UI（推荐）

1. 打开 http://localhost:3000
2. 点击右上角 **"进入工作台"**
3. 在左侧输入框填写视频主题，例如：
   ```
   赛博朋克风格的火星殖民地，60秒，冷色调，科技感
   ```
4. 选择视频引擎（Kling 或 Seedance）
5. 点击 **"开始创作"**
6. 等待脚本生成后，在中间面板审核分镜脚本，点击 **"确认生成"**
7. 等待并行生成（图像 + 配音 + 视频），右侧面板实时显示进度
8. 生成完成后，点击下载按钮获取 MP4 成品和剪映草稿

### 方式二：通过 CLI（适合批量/自动化）

**新开一个命令提示符窗口**：

```cmd
cd C:\Users\你的用户名\Desktop\Pilipili-AutoVideo

# 基础生成
python cli\main.py run --topic "赛博朋克火星殖民，60秒，冷色调"

# 指定引擎和时长
python cli\main.py run --topic "古装宫廷爱情" --engine seedance --duration 90

# 跳过人工审核（全自动）
python cli\main.py run --topic "AI 芯片发展史" --no-review

# 仅生成脚本（不调用付费 API，用于预览）
python cli\main.py script --topic "美食探店" --output script.json
```

### 输出文件位置

生成完成后，文件位于：

```
data\outputs\{project_id}\
├── script.json          # 分镜脚本
├── keyframes\           # 关键帧图片（PNG）
├── audio\               # TTS 配音（MP3）
├── clips\               # 视频片段（MP4）
└── output\
    ├── 视频标题.mp4      # 最终成品视频 ← 这是你要的文件
    ├── 视频标题.srt      # 字幕文件
    └── 剪映草稿\         # 剪映草稿工程 ← 复制到剪映草稿目录
```

---

## 9. API Keys 申请指南

| 服务 | 用途 | 申请地址 | 费用参考 |
| :--- | :--- | :--- | :--- |
| **DeepSeek** | LLM 脚本生成（推荐） | [platform.deepseek.com](https://platform.deepseek.com/) | 极低，约 ¥0.001/千 token |
| **Google AI Studio** | Nano Banana 生图 | [aistudio.google.com](https://aistudio.google.com/) | 免费额度充足 |
| **Kling AI** | 视频生成（默认引擎） | [klingai.com](https://klingai.com/) → 开放平台 | 按视频秒数计费 |
| **Seedance** | 视频生成（可选引擎） | [console.volcengine.com](https://console.volcengine.com/) → 视频生成 | 按视频秒数计费 |
| **MiniMax** | TTS 配音 | [platform.minimaxi.com](https://platform.minimaxi.com/) | 免费额度充足 |
| **Mem0 Cloud** | 记忆云同步（可选） | [app.mem0.ai](https://app.mem0.ai/) | 免费套餐可用 |

### DeepSeek API Key 申请步骤

1. 访问 https://platform.deepseek.com/
2. 注册账号并完成手机验证
3. 进入控制台 → **API Keys** → 创建新 Key
4. 复制 `sk-` 开头的 Key 填入配置文件

### Google AI Studio Key 申请步骤

1. 访问 https://aistudio.google.com/
2. 登录 Google 账号
3. 点击 **"Get API Key"** → **"Create API Key"**
4. 复制 `AIzaSy` 开头的 Key 填入配置文件

### Kling API Key 申请步骤

1. 访问 https://klingai.com/ 注册账号
2. 进入 **开放平台** → **API 管理**
3. 创建应用，获取 **API Key** 和 **API Secret**（两个都需要）
4. 分别填入配置文件的 `kling.api_key` 和 `kling.api_secret`

### MiniMax API Key 申请步骤

1. 访问 https://platform.minimaxi.com/ 注册账号
2. 进入 **账户管理** → **API Key**
3. 创建 Key，复制填入配置文件

---

## 10. 常见问题排查

### ❌ `python` 不是内部或外部命令

**原因**：Python 未加入 PATH。

**解决**：
1. 重新运行 Python 安装包
2. 勾选 **"Add Python to PATH"**
3. 重启命令提示符

或手动添加：右键"此电脑" → 属性 → 高级系统设置 → 环境变量 → 在 Path 中添加 Python 安装目录（如 `C:\Python311\` 和 `C:\Python311\Scripts\`）

---

### ❌ `ffmpeg` 不是内部或外部命令

**原因**：FFmpeg 未加入 PATH。

**解决**：参考第 [4 节](#4-安装-ffmpeg重要) 手动安装方法，确保 `C:\ffmpeg\bin` 已加入 PATH，并**重启命令提示符**。

---

### ❌ `pip install` 报错 `Microsoft Visual C++ 14.0 is required`

**原因**：部分 Python 包需要 C++ 编译器。

**解决**：
```cmd
pip install --upgrade setuptools wheel
```

如果仍然报错，安装 [Visual C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)。

---

### ❌ 后端启动报错 `ModuleNotFoundError`

**原因**：依赖未完整安装。

**解决**：
```cmd
pip install -r requirements.txt --force-reinstall
```

---

### ❌ 前端访问 http://localhost:3000 显示"无法连接后端"

**原因**：后端服务未启动，或端口被占用。

**解决**：
1. 确认后端窗口显示 `Uvicorn running on http://0.0.0.0:8000`
2. 访问 http://localhost:8000/health 验证后端
3. 如果 8000 端口被占用，修改启动命令：
   ```cmd
   python cli\main.py server --port 8001
   ```
   同时修改前端的 API 地址（`frontend\.env.local` 中的 `VITE_API_URL`）

---

### ❌ 视频生成卡在"等待中"很久

**原因**：Kling/Seedance 视频生成 API 本身需要时间（每段约 2-5 分钟），这是正常现象。

**解决**：耐心等待，Web UI 右侧面板会实时显示每个分镜的生成进度。

---

### ❌ 剪映草稿打不开

**原因**：草稿目录路径不对，或剪映版本不兼容。

**解决**：
1. 找到剪映草稿目录（通常在 `C:\Users\你的用户名\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft\`）
2. 将 `data\outputs\{project_id}\output\剪映草稿\` 整个文件夹复制进去
3. 重新打开剪映，在草稿列表中找到对应项目

---

### ❌ `pnpm` 不是内部或外部命令

**解决**：
```cmd
npm install -g pnpm
```

然后重启命令提示符。

---

## 快速参考卡

```
# 每次使用前，开两个命令提示符窗口：

【窗口 1 - 后端】
cd C:\Projects\Pilipili-AutoVideo
python cli\main.py server

【窗口 2 - 前端】
cd C:\Projects\Pilipili-AutoVideo\frontend
pnpm dev

【浏览器】
打开 http://localhost:3000
```

---

> 如遇到本教程未覆盖的问题，请在 [GitHub Issues](https://github.com/OpenDemon/Pilipili-AutoVideo/issues) 提交，附上错误截图和操作系统版本。
