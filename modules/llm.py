"""
噼哩噼哩 Pilipili-AutoVideo
LLM 脚本生成模块

职责：
- 将自然语言主题转化为结构化 JSON 分镜脚本
- 支持 DeepSeek / Kimi / MiniMax / 智谱 / Gemini / OpenAI / Ollama
- 注入用户记忆偏好，实现风格个性化
- 采用 Agent-S 的 Manager + Reflection 双层架构
"""

import json
import re
import asyncio
from typing import Optional
from openai import AsyncOpenAI
from dataclasses import dataclass, field

from core.config import PilipiliConfig, get_config, get_active_llm_config


# ============================================================
# 数据结构：分镜脚本
# ============================================================

@dataclass
class Scene:
    """单个分镜场景"""
    scene_id: int
    duration: float                    # 秒，由 TTS 时长动态决定
    image_prompt: str                  # 发给 Nano Banana 的生图提示词（英文）
    video_prompt: str                  # 发给 Kling/Seedance 的运动描述（英文）
    voiceover: str                     # 中文旁白文案（发给 TTS）
    transition: str = "crossfade"      # 转场类型: crossfade / fade / wipe / cut
    camera_motion: str = "static"      # 镜头运动: static / pan_left / pan_right / zoom_in / zoom_out
    style_tags: list = field(default_factory=list)  # 风格标签，用于记忆学习
    reference_character: Optional[str] = None       # 角色参考图路径（主体一致性）


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
      "style_tags": ["风格标签1", "风格标签2"]
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

如果有问题，请直接输出修正后的完整 JSON。如果没有问题，输出原始 JSON 即可。
只输出 JSON，不要有其他文字。"""


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
        response_format={"type": "json_object"} if _supports_json_mode(model) else None,
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
        response_format={"type": "json_object"} if _supports_json_mode(model) else None,
    )

    final_script_str = reflection_response.choices[0].message.content

    if verbose:
        print(f"[LLM] Reflection 完成")

    # 解析 JSON
    script_data = _parse_json_safely(final_script_str)

    # 转换为 VideoScript 对象
    return _dict_to_video_script(script_data, topic)


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
