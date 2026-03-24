"""
噼哩噼哩 Pilipili-AutoVideo
LLM 脚本生成模块

v2.0 改动：
- Scene 数据结构新增 shot_mode 字段（multi_ref / first_end_frame / t2v / i2v）
- 脚本生成提示词升级，LLM 自动为每个分镜标注 shot_mode
- 新增 analyze_reference_video() 函数：Gemini 视频理解 → 人物列表 + 分镜 + 反推提示词
- 支持 DeepSeek / Kimi / MiniMax / 智谱 / Gemini / OpenAI / Ollama
- 注入用户记忆偏好，实现风格个性化
- 采用 Agent-S 的 Manager + Reflection 双层架构
"""

import json
import re
import asyncio
import base64
import os
from typing import Optional, Literal
from openai import AsyncOpenAI
from dataclasses import dataclass, field

from core.config import PilipiliConfig, get_config, get_active_llm_config


# ============================================================
# 数据结构：分镜脚本
# ============================================================

ShotMode = Literal["multi_ref", "first_end_frame", "t2v", "i2v"]


@dataclass
class Scene:
    """单个分镜场景（v2.0 新增 shot_mode 字段）"""
    scene_id: int
    duration: float                    # 秒，由 TTS 时长动态决定
    image_prompt: str                  # 发给 Nano Banana 的生图提示词（英文）
    video_prompt: str                  # 发给 Kling/Seedance 的运动描述（英文）
    voiceover: str                     # 中文旁白文案（发给 TTS）
    transition: str = "crossfade"      # 转场类型: crossfade / fade / wipe / cut
    camera_motion: str = "static"      # 镜头运动: static / pan_left / pan_right / zoom_in / zoom_out
    style_tags: list = field(default_factory=list)  # 风格标签，用于记忆学习
    reference_character: Optional[str] = None       # 角色参考图路径（主体一致性）
    # v2.0 新增
    shot_mode: Optional[ShotMode] = None            # 生成模式（LLM 自动标注）
    character_refs: Optional[list[str]] = None      # 多主体参考图路径列表（Omni image_list）


@dataclass
class VideoScript:
    """完整视频脚本"""
    title: str
    topic: str
    style: str
    total_duration: float
    scenes: list[Scene]
    metadata: dict = field(default_factory=dict)  # 标题、描述、tags 等发布元数据


# ============================================================
# 对标视频分析结果数据结构
# ============================================================

@dataclass
class CharacterInfo:
    """视频中的人物信息"""
    character_id: int
    name: str                          # 人物名称（如"男主角"、"女主角"）
    description: str                   # 外貌描述（中文）
    appearance_prompt: str             # 外貌英文提示词（用于生图）
    thumbnail_base64: Optional[str] = None  # 截图缩略图（base64）
    replacement_image: Optional[str] = None  # 替换参考图路径（用户上传）


@dataclass
class ReferenceVideoAnalysis:
    """对标视频分析结果"""
    title: str                         # 视频标题/主题
    style: str                         # 整体风格描述
    aspect_ratio: str                  # 画面比例（16:9 / 9:16 等）
    total_duration: float              # 视频时长（秒）
    characters: list[CharacterInfo]    # 人物列表
    scenes: list[Scene]                # 分镜列表（含反推提示词）
    reverse_prompts: list[str]         # 每个分镜的反推提示词（英文，供直接复用）
    bgm_style: str                     # BGM 风格描述
    color_grade: str                   # 色调/调色风格
    overall_prompt: str                # 整体风格提示词（用于生成同风格视频）
    raw_analysis: str                  # Gemini 原始分析文本


# ============================================================
# 系统提示词
# ============================================================

SCRIPT_SYSTEM_PROMPT = """你是一位专业的短视频脚本策划师和分镜导演。你的任务是将用户的主题转化为一个结构化的 JSON 视频脚本。

## 输出要求

你必须严格输出一个 JSON 对象，不要有任何额外的文字说明。JSON 结构如下：

```json
{{
  "title": "视频标题（中文，吸引人，适合社交媒体）",
  "style": "整体风格描述",
  "total_duration": 预估总时长（秒，整数）,
  "scenes": [
    {{
      "scene_id": 1,
      "duration": 5,
      "image_prompt": "英文生图提示词，描述这一幕的画面构图、光线、色调、主体，要具体且视觉化，适合 AI 生图",
      "video_prompt": "英文运动描述，描述画面中的动态效果，如 camera slowly zooms in, character walks forward",
      "voiceover": "中文旁白文案，这段话将被转换为语音，时长约等于 duration 秒",
      "transition": "crossfade",
      "camera_motion": "static",
      "style_tags": ["风格标签1", "风格标签2"],
      "shot_mode": "i2v"
    }}
  ],
  "metadata": {{
    "description": "视频描述（100字以内）",
    "tags": ["标签1", "标签2", "标签3", "标签4", "标签5"],
    "platform_title": {{
      "douyin": "抖音标题（30字以内，含话题标签）",
      "bilibili": "B站标题（80字以内）"
    }}
  }}
}}
```

## 分镜规则

1. 每个分镜时长建议 4-8 秒，总视频 30-90 秒
2. `image_prompt` 必须是英文，要包含：主体描述、场景环境、光线风格、色调、构图方式
3. `video_prompt` 必须是英文，描述运动和动态，不要重复 image_prompt 的内容
4. `voiceover` 是中文，语速约每秒 3-4 个字，要与画面内容匹配
5. `transition` 可选值：crossfade / fade / wipe / cut / zoom
6. `camera_motion` 可选值：static / pan_left / pan_right / zoom_in / zoom_out / tilt_up / tilt_down
7. 第一幕要有强烈的视觉冲击力，最后一幕要有收尾感

## shot_mode 标注规则（重要）

每个分镜必须标注 `shot_mode`，根据以下规则选择：

- `multi_ref`：有固定人物出现 + 动作/对话场景 → 使用角色参考图生成（角色一致性最强）
- `first_end_frame`：场景转换/时间流逝/运镜过渡镜头 → 首尾帧控制生成
- `t2v`：纯风景/氛围/空镜/无人物 → 文生视频（无需参考图）
- `i2v`：其他情况 → 传统图生视频（默认）

## 风格指导

{style_guidance}
"""

REFLECTION_PROMPT = """请检查以下分镜脚本是否符合要求：

{script}

检查要点：
1. JSON 格式是否正确
2. 每个 scene 的 image_prompt 是否足够具体（至少 20 个英文单词）
3. voiceover 的字数是否与 duration 匹配（每秒约 3-4 个字）
4. 整体风格是否统一
5. 是否有强开头和好结尾
6. 每个 scene 是否都有 shot_mode 字段（必须是 multi_ref / first_end_frame / t2v / i2v 之一）

如果有问题，请直接输出修正后的完整 JSON。如果没有问题，输出原始 JSON 即可。
只输出 JSON，不要有其他文字。"""


VIDEO_ANALYSIS_PROMPT = """你是一位专业的视频分析师和逆向工程师。请分析这段视频，提取以下信息并以 JSON 格式输出。

## 分析任务

1. **人物识别**：识别视频中出现的所有主要人物，描述其外貌特征
2. **分镜结构**：将视频分解为独立的分镜，每个分镜约 3-8 秒
3. **反推提示词**：为每个分镜生成英文提示词（可以直接用于 AI 重新生成同风格视频）
4. **整体风格**：分析视频的视觉风格、色调、BGM 风格

## 输出 JSON 格式

```json
{{
  "title": "视频主题/标题",
  "style": "整体风格描述（中文）",
  "aspect_ratio": "16:9 或 9:16",
  "total_duration": 视频时长（秒，浮点数）,
  "color_grade": "色调风格描述（如：暖色调、冷色调、胶片感、赛博朋克等）",
  "bgm_style": "BGM 风格描述（如：史诗感弦乐、轻快流行、电子音乐等）",
  "overall_prompt": "整体风格英文提示词（用于生成同风格视频，50-100词）",
  "characters": [
    {{
      "character_id": 1,
      "name": "人物名称（如：男主角、女主角、配角A）",
      "description": "外貌详细描述（中文，包括服装、发型、面部特征等）",
      "appearance_prompt": "外貌英文提示词（用于 AI 生图，30-50词）"
    }}
  ],
  "scenes": [
    {{
      "scene_id": 1,
      "duration": 5,
      "description": "分镜内容描述（中文）",
      "image_prompt": "生图英文提示词（描述画面构图、光线、色调、主体）",
      "video_prompt": "运动英文提示词（描述动态效果）",
      "voiceover_text": "该分镜的旁白/对话文字（如果有）",
      "characters_in_scene": [1],
      "shot_mode": "multi_ref 或 t2v 或 first_end_frame 或 i2v",
      "reverse_prompt": "反推提示词（英文，描述如何重新生成这个分镜，包含风格、构图、光线、人物动作等所有细节）"
    }}
  ]
}}
```

## 注意事项

- `reverse_prompt` 是最重要的输出，要足够详细，让 AI 能重新生成相似的画面
- 人物描述要精确，包括所有可见的外貌细节
- shot_mode 判断规则：有人物+动作 → multi_ref；纯风景 → t2v；转场 → first_end_frame；其他 → i2v
- 只输出 JSON，不要有任何其他文字
"""


# ============================================================
# LLM 客户端工厂
# ============================================================

def _build_openai_client(config: PilipiliConfig) -> tuple[AsyncOpenAI, str]:
    """根据配置构建 OpenAI 兼容客户端"""
    provider = config.llm.default_provider
    provider_cfg = get_active_llm_config(config)

    if provider == "gemini":
        # Gemini 使用 OpenAI 兼容接口
        client = AsyncOpenAI(
            api_key=provider_cfg.api_key or "gemini",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )
    else:
        client = AsyncOpenAI(
            api_key=provider_cfg.api_key or "sk-placeholder",
            base_url=provider_cfg.base_url or "https://api.openai.com/v1"
        )

    return client, provider_cfg.model


# ============================================================
# 核心生成函数
# ============================================================

async def generate_script(
    topic: str,
    style: Optional[str] = None,
    duration_hint: int = 60,
    num_scenes: Optional[int] = None,
    memory_context: Optional[str] = None,
    config: Optional[PilipiliConfig] = None,
    verbose: bool = False,
) -> VideoScript:
    """
    将主题转化为结构化分镜脚本

    Args:
        topic: 视频主题（自然语言）
        style: 风格描述（可选，如"赛博朋克，冷色调"）
        duration_hint: 目标时长（秒）
        num_scenes: 分镜数量（可选，不指定则由 LLM 决定）
        memory_context: 从 Mem0 检索到的用户偏好（可选）
        config: 配置对象（可选，默认加载全局配置）
        verbose: 是否打印调试信息

    Returns:
        VideoScript 对象
    """
    if config is None:
        config = get_config()

    client, model = _build_openai_client(config)

    # 构建风格指导
    style_parts = []
    if style:
        style_parts.append(f"用户指定风格：{style}")
    if memory_context:
        style_parts.append(f"用户历史偏好（请参考）：\n{memory_context}")
    if not style_parts:
        style_parts.append("根据主题自由发挥，追求视觉冲击力和叙事节奏感")

    style_guidance = "\n".join(style_parts)

    # 构建用户消息
    scene_hint = f"，分为 {num_scenes} 个分镜" if num_scenes else ""
    user_message = f"""请为以下主题创作一个约 {duration_hint} 秒的短视频脚本{scene_hint}：

主题：{topic}

请直接输出 JSON，不要有任何其他文字。"""

    system_prompt = SCRIPT_SYSTEM_PROMPT.format(style_guidance=style_guidance)

    if verbose:
        print(f"[LLM] 使用模型: {model}")
        print(f"[LLM] 主题: {topic}")
        print(f"[LLM] 风格: {style or '自动'}")

    # 第一轮：生成初稿
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        temperature=0.7,
        **({"response_format": {"type": "json_object"}} if _supports_json_mode(model) else {}),
    )

    raw_script = response.choices[0].message.content

    if verbose:
        print(f"[LLM] 初稿生成完成，长度: {len(raw_script)} 字符")

    # 第二轮：Reflection 检查（借鉴 Agent-S 的 Reflection Agent）
    reflection_response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "你是一位严格的视频脚本审核员。你只输出 JSON，不输出任何其他文字。"},
            {"role": "user", "content": REFLECTION_PROMPT.format(script=raw_script)}
        ],
        temperature=0.3,
        **({"response_format": {"type": "json_object"}} if _supports_json_mode(model) else {}),
    )

    final_script_str = reflection_response.choices[0].message.content

    if verbose:
        print(f"[LLM] Reflection 完成")

    # 解析 JSON
    script_data = _parse_json_safely(final_script_str)

    # 转换为 VideoScript 对象
    return _dict_to_video_script(script_data, topic)


# ============================================================
# 对标视频分析函数（v2.0 新增）
# ============================================================

async def analyze_reference_video(
    video_path: str,
    config: Optional[PilipiliConfig] = None,
    verbose: bool = False,
) -> ReferenceVideoAnalysis:
    """
    使用 Gemini 分析对标视频，提取人物、分镜结构和反推提示词

    Args:
        video_path: 视频文件路径（本地 MP4 文件）
        config: 配置对象
        verbose: 是否打印调试信息

    Returns:
        ReferenceVideoAnalysis 对象（含人物列表、分镜、反推提示词）
    """
    if config is None:
        config = get_config()

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"视频文件不存在: {video_path}")

    if verbose:
        print(f"[LLM] 开始分析对标视频: {video_path}")

    # 使用 Gemini 原生 SDK 进行视频理解（支持视频文件上传）
    try:
        from google import genai
        from google.genai import types

        gemini_api_key = config.image_gen.api_key  # Gemini API Key
        if not gemini_api_key:
            # 尝试从 LLM 配置获取
            gemini_api_key = config.llm.gemini.api_key

        if not gemini_api_key:
            raise ValueError("Gemini API Key 未配置（需要在 image_gen.api_key 或 llm.gemini.api_key 中配置）")

        client = genai.Client(api_key=gemini_api_key)

        if verbose:
            print(f"[LLM] 上传视频到 Gemini Files API...")

        # 确定 MIME 类型
        ext = os.path.splitext(video_path)[1].lower()
        mime_map = {
            ".mp4": "video/mp4",
            ".mov": "video/quicktime",
            ".avi": "video/x-msvideo",
            ".mkv": "video/x-matroska",
            ".webm": "video/webm",
        }
        mime_type = mime_map.get(ext, "video/mp4")

        # 上传到 Gemini Files API（直接传文件路径，不读 bytes）
        video_file = client.files.upload(
            file=video_path,
            config=types.UploadFileConfig(
                mime_type=mime_type,
                display_name=os.path.basename(video_path),
            )
        )

        if verbose:
            print(f"[LLM] 视频已上传: {video_file.name}，等待处理...")

        # 等待文件处理完成
        import time
        max_wait = 120
        start = time.time()
        while video_file.state.name == "PROCESSING":
            if time.time() - start > max_wait:
                raise TimeoutError("Gemini 视频处理超时（120s）")
            await asyncio.sleep(3)
            video_file = client.files.get(name=video_file.name)

        if video_file.state.name == "FAILED":
            raise RuntimeError(f"Gemini 视频处理失败: {video_file.state}")

        if verbose:
            print(f"[LLM] 视频处理完成，开始分析...")

        # 调用 Gemini 分析视频（优先用 config 中的模型，fallback 到 gemini-2.5-flash）
        gemini_model = getattr(config.llm.gemini, 'model', None) or "gemini-2.5-flash"
        # 已下线的 Gemini 模型，强制升级到 gemini-2.5-flash
        DEPRECATED_GEMINI_MODELS = {
            "gemini-2.0-flash", "gemini-2.0-flash-exp",
            "gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.5-pro-latest",
            "gemini-1.0-pro", "gemini-pro",
        }
        if gemini_model in DEPRECATED_GEMINI_MODELS:
            if verbose:
                print(f"[LLM] 模型 {gemini_model} 已下线，自动切换到 gemini-2.5-flash")
            gemini_model = "gemini-2.5-flash"
        if verbose:
            print(f"[LLM] 使用 Gemini 模型: {gemini_model}")
        response = client.models.generate_content(
            model=gemini_model,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(
                            file_uri=video_file.uri,
                            mime_type=mime_type,
                        ),
                        types.Part.from_text(text=VIDEO_ANALYSIS_PROMPT),
                    ]
                )
            ]
        )

        raw_analysis = response.text

        if verbose:
            print(f"[LLM] Gemini 分析完成，长度: {len(raw_analysis)} 字符")

        # 清理上传的文件
        try:
            client.files.delete(name=video_file.name)
        except Exception:
            pass

    except ImportError:
        # 回退到 OpenAI 兼容接口（不支持视频，使用文本描述）
        if verbose:
            print(f"[LLM] google-genai SDK 未安装，回退到文本模式")
        raw_analysis = await _analyze_video_fallback(video_path, config, verbose)

    # 解析分析结果
    return _parse_video_analysis(raw_analysis, video_path)


async def _analyze_video_fallback(
    video_path: str,
    config: PilipiliConfig,
    verbose: bool,
) -> str:
    """
    回退方案：提取视频关键帧，用图片理解代替视频理解
    """
    import subprocess
    import tempfile

    if verbose:
        print(f"[LLM] 使用关键帧提取模式分析视频...")

    # 提取多个关键帧
    frames_dir = tempfile.mkdtemp()
    frame_paths = []

    try:
        # 获取视频时长
        probe_cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", video_path
        ]
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
        duration = 30.0
        if probe_result.returncode == 0:
            info = json.loads(probe_result.stdout)
            duration = float(info.get("format", {}).get("duration", 30.0))

        # 提取均匀分布的8帧
        num_frames = 8
        for i in range(num_frames):
            seek_time = duration * (i + 0.5) / num_frames
            frame_path = os.path.join(frames_dir, f"frame_{i:03d}.jpg")
            cmd = [
                "ffmpeg", "-y", "-ss", str(seek_time),
                "-i", video_path, "-vframes", "1", "-q:v", "2", frame_path
            ]
            subprocess.run(cmd, capture_output=True)
            if os.path.exists(frame_path):
                frame_paths.append(frame_path)

        if not frame_paths:
            raise RuntimeError("无法提取视频关键帧")

        # 构建多图分析请求
        client, model = _build_openai_client(config)

        messages_content = [
            {
                "type": "text",
                "text": f"以下是一段视频的 {len(frame_paths)} 个关键帧截图（按时间顺序排列，视频总时长约 {duration:.1f} 秒）。\n\n{VIDEO_ANALYSIS_PROMPT}"
            }
        ]

        for frame_path in frame_paths:
            with open(frame_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()
            ext = os.path.splitext(frame_path)[1].lower()
            mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
            messages_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{img_b64}"}
            })

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": messages_content}
            ],
            temperature=0.3,
            max_tokens=4096,
        )

        return response.choices[0].message.content

    finally:
        # 清理临时帧文件
        import shutil
        try:
            shutil.rmtree(frames_dir)
        except Exception:
            pass


def _parse_video_analysis(raw_analysis: str, video_path: str) -> ReferenceVideoAnalysis:
    """解析 Gemini 视频分析结果为结构化对象"""
    try:
        data = _parse_json_safely(raw_analysis)
    except Exception:
        # 解析失败时返回最小化结果
        return ReferenceVideoAnalysis(
            title="视频分析结果",
            style="未能解析",
            aspect_ratio="16:9",
            total_duration=0.0,
            characters=[],
            scenes=[],
            reverse_prompts=[],
            bgm_style="未知",
            color_grade="未知",
            overall_prompt="",
            raw_analysis=raw_analysis,
        )

    # 解析人物列表
    characters = []
    for c in data.get("characters", []):
        characters.append(CharacterInfo(
            character_id=c.get("character_id", len(characters) + 1),
            name=c.get("name", f"人物{len(characters) + 1}"),
            description=c.get("description", ""),
            appearance_prompt=c.get("appearance_prompt", ""),
        ))

    # 解析分镜列表
    scenes = []
    reverse_prompts = []
    for s in data.get("scenes", []):
        scene = Scene(
            scene_id=s.get("scene_id", len(scenes) + 1),
            duration=float(s.get("duration", 5)),
            image_prompt=s.get("image_prompt", ""),
            video_prompt=s.get("video_prompt", ""),
            voiceover=s.get("voiceover_text", s.get("voiceover", "")),
            transition="crossfade",
            camera_motion="static",
            style_tags=[],
            shot_mode=s.get("shot_mode", "i2v"),
        )
        scenes.append(scene)
        reverse_prompts.append(s.get("reverse_prompt", scene.image_prompt))

    return ReferenceVideoAnalysis(
        title=data.get("title", "对标视频"),
        style=data.get("style", ""),
        aspect_ratio=data.get("aspect_ratio", "16:9"),
        total_duration=float(data.get("total_duration", 0)),
        characters=characters,
        scenes=scenes,
        reverse_prompts=reverse_prompts,
        bgm_style=data.get("bgm_style", ""),
        color_grade=data.get("color_grade", ""),
        overall_prompt=data.get("overall_prompt", ""),
        raw_analysis=raw_analysis,
    )


# ============================================================
# 工具函数
# ============================================================

def _supports_json_mode(model: str) -> bool:
    """判断模型是否支持 JSON mode"""
    json_mode_models = ["gpt-4", "gpt-3.5", "deepseek", "qwen"]
    return any(m in model.lower() for m in json_mode_models)


def _parse_json_safely(text: str) -> dict:
    """安全解析 JSON，处理 markdown 代码块包裹的情况"""
    # 移除 markdown 代码块
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # 移除第一行（```json 或 ```）和最后一行（```）
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 尝试提取 JSON 对象
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"无法解析 LLM 输出为 JSON: {text[:200]}...")


def _dict_to_video_script(data: dict, topic: str) -> VideoScript:
    """将字典转换为 VideoScript 对象"""
    scenes = []
    for s in data.get("scenes", []):
        scene = Scene(
            scene_id=s.get("scene_id", len(scenes) + 1),
            duration=float(s.get("duration", 5)),
            image_prompt=s.get("image_prompt", ""),
            video_prompt=s.get("video_prompt", ""),
            voiceover=s.get("voiceover", ""),
            transition=s.get("transition", "crossfade"),
            camera_motion=s.get("camera_motion", "static"),
            style_tags=s.get("style_tags", []),
            reference_character=s.get("reference_character"),
            shot_mode=s.get("shot_mode"),
            character_refs=s.get("character_refs"),
        )
        scenes.append(scene)

    total_duration = sum(s.duration for s in scenes)

    return VideoScript(
        title=data.get("title", topic),
        topic=topic,
        style=data.get("style", ""),
        total_duration=total_duration,
        scenes=scenes,
        metadata=data.get("metadata", {}),
    )


# ============================================================
# 同步包装器（供 CLI 使用）
# ============================================================

def generate_script_sync(
    topic: str,
    style: Optional[str] = None,
    duration_hint: int = 60,
    num_scenes: Optional[int] = None,
    memory_context: Optional[str] = None,
    config: Optional[PilipiliConfig] = None,
    verbose: bool = False,
) -> VideoScript:
    """generate_script 的同步版本"""
    return asyncio.run(generate_script(
        topic=topic,
        style=style,
        duration_hint=duration_hint,
        num_scenes=num_scenes,
        memory_context=memory_context,
        config=config,
        verbose=verbose,
    ))


def analyze_reference_video_sync(
    video_path: str,
    config: Optional[PilipiliConfig] = None,
    verbose: bool = False,
) -> ReferenceVideoAnalysis:
    """analyze_reference_video 的同步版本"""
    return asyncio.run(analyze_reference_video(
        video_path=video_path,
        config=config,
        verbose=verbose,
    ))


# ============================================================
# 脚本序列化/反序列化
# ============================================================

def script_to_dict(script: VideoScript) -> dict:
    """将 VideoScript 转换为可序列化的字典"""
    return {
        "title": script.title,
        "topic": script.topic,
        "style": script.style,
        "total_duration": script.total_duration,
        "scenes": [
            {
                "scene_id": s.scene_id,
                "duration": s.duration,
                "image_prompt": s.image_prompt,
                "video_prompt": s.video_prompt,
                "voiceover": s.voiceover,
                "transition": s.transition,
                "camera_motion": s.camera_motion,
                "style_tags": s.style_tags,
                "reference_character": s.reference_character,
                "shot_mode": s.shot_mode,
                "character_refs": s.character_refs,
            }
            for s in script.scenes
        ],
        "metadata": script.metadata,
    }


def dict_to_script(data: dict) -> VideoScript:
    """从字典恢复 VideoScript"""
    return _dict_to_video_script(data, data.get("topic", ""))


def save_script(script: VideoScript, path: str):
    """保存脚本到 JSON 文件"""
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(script_to_dict(script), f, ensure_ascii=False, indent=2)


def load_script(path: str) -> VideoScript:
    """从 JSON 文件加载脚本"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return dict_to_script(data)
