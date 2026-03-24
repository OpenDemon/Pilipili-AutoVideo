"""
噼哩噼哩 Pilipili-AutoVideo
图像生成模块 - Nano Banana (Gemini Image Generation)

职责：
- 为每个分镜生成高质量 4K 首帧关键图
- 支持多参考图注入（角色一致性）
- 支持风格参考图
- 异步并发生成，提升效率
"""

import os
import asyncio
import aiohttp
import base64
import hashlib
from pathlib import Path
from typing import Optional
from google import genai
from google.genai import types

from core.config import PilipiliConfig, get_config
from modules.llm import Scene


# ============================================================
# 图像生成核心函数
# ============================================================

async def generate_keyframe(
    scene: Scene,
    output_dir: str,
    reference_images: Optional[list[str]] = None,
    style_reference: Optional[str] = None,
    config: Optional[PilipiliConfig] = None,
    verbose: bool = False,
) -> str:
    """
    为单个分镜生成关键帧图片

    Args:
        scene: 分镜场景对象
        output_dir: 输出目录
        reference_images: 角色/主体参考图路径列表（用于主体一致性）
        style_reference: 风格参考图路径
        config: 配置对象
        verbose: 是否打印调试信息

    Returns:
        生成的图片本地路径
    """
    if config is None:
        config = get_config()

    os.makedirs(output_dir, exist_ok=True)

    # 输出路径
    output_path = os.path.join(output_dir, f"scene_{scene.scene_id:03d}_keyframe.png")

    # 如果已存在，跳过（断点续传）
    if os.path.exists(output_path):
        if verbose:
            print(f"[ImageGen] Scene {scene.scene_id} 关键帧已存在，跳过生成")
        return output_path

    api_key = config.image_gen.api_key
    if not api_key:
        raise ValueError("Nano Banana (Gemini) API Key 未配置，请在 config.yaml 中设置 image_gen.api_key")

    client = genai.Client(api_key=api_key)

    # 构建提示词：基础提示词 + 风格标签
    style_str = ", ".join(scene.style_tags) if scene.style_tags else ""
    full_prompt = scene.image_prompt
    if style_str:
        full_prompt = f"{full_prompt}, style: {style_str}"

    # 添加质量提示词
    full_prompt = (
        f"{full_prompt}, "
        f"ultra high quality, 4K resolution, cinematic composition, "
        f"professional photography, sharp focus, detailed"
    )

    if verbose:
        print(f"[ImageGen] Scene {scene.scene_id} 生成关键帧")
        print(f"[ImageGen] Prompt: {full_prompt[:100]}...")

    # 构建多模态内容（支持参考图注入）
    contents = []

    # 添加参考图（角色一致性）
    if reference_images:
        ref_parts = []
        for ref_path in reference_images:
            if os.path.exists(ref_path):
                with open(ref_path, "rb") as f:
                    img_data = f.read()
                img_b64 = base64.b64encode(img_data).decode()
                # 检测图片格式
                mime_type = _detect_mime_type(ref_path)
                ref_parts.append(
                    types.Part.from_bytes(data=img_data, mime_type=mime_type)
                )
        if ref_parts:
            contents.extend(ref_parts)
            contents.append(types.Part.from_text(
                text=(
                    "CRITICAL CHARACTER CONSISTENCY INSTRUCTION: "
                    "The reference image(s) above show the EXACT character(s) that MUST appear in the generated image. "
                    "You MUST preserve: 1) The EXACT same face, facial features, and facial structure. "
                    "2) The EXACT same hairstyle, hair color, and hair length. "
                    "3) The EXACT same clothing, accessories, glasses, hats, and other distinctive items. "
                    "4) The EXACT same body type and proportions. "
                    "5) The EXACT same skin tone and complexion. "
                    "The character should look like the SAME PERSON in a different scene/pose, NOT a different person. "
                    "This is the highest priority requirement — character identity must be preserved above all else."
                )
            ))

    # 添加风格参考图
    if style_reference and os.path.exists(style_reference):
        with open(style_reference, "rb") as f:
            style_data = f.read()
        mime_type = _detect_mime_type(style_reference)
        contents.append(types.Part.from_bytes(data=style_data, mime_type=mime_type))
        contents.append(types.Part.from_text(
            text="Please use the visual style, color palette and aesthetic shown in the style reference image above."
        ))

    # 添加主提示词
    contents.append(types.Part.from_text(text=full_prompt))

    # 调用 API，503 时自动切换备用模型
    # 图像生成 fallback 列表（均经过 ListModels 确认存在）
    FALLBACK_MODELS = [
        config.image_gen.model,                    # config 配置的主模型
        "models/gemini-2.5-flash-image",           # 备选：2.5 Flash 图像版
        "models/gemini-3.1-flash-image-preview",   # 备选：3.1 Flash 图像预览版
    ]
    # 去重保序
    seen = set()
    model_list = [m for m in FALLBACK_MODELS if not (m in seen or seen.add(m))]

    last_err = None
    response = None
    for model_name in model_list:
        try:
            if verbose and model_name != config.image_gen.model:
                print(f"[ImageGen] 主模型不可用，切换到备用模型: {model_name}")
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"],
                )
            )
            break  # 成功则退出循环
        except Exception as e:
            last_err = e
            err_str = str(e)
            if ("503" in err_str or "UNAVAILABLE" in err_str or "429" in err_str) and "404" not in err_str:
                if verbose:
                    print(f"[ImageGen] 模型 {model_name} 不可用 ({err_str[:60]})，尝试下一个...")
                continue
            raise  # 404/其他错误直接抛出，不尝试下一个模型
    if response is None:
        raise RuntimeError(f"Scene {scene.scene_id} 所有图像模型均不可用: {last_err}")

    # 提取图片数据（防御性检查：candidates / content / parts 均可能为 None）
    image_saved = False
    candidates = response.candidates if response.candidates else []
    for candidate in candidates:
        content = candidate.content if candidate else None
        if content is None:
            continue
        parts = content.parts if content.parts else []
        for part in parts:
            if part.inline_data is not None:
                img_data = part.inline_data.data
                if isinstance(img_data, str):
                    img_data = base64.b64decode(img_data)
                with open(output_path, "wb") as f:
                    f.write(img_data)
                image_saved = True
                break
        if image_saved:
            break

    if not image_saved:
        # 打印完整 response 结构便于调试
        finish_reason = None
        if candidates and candidates[0]:
            finish_reason = getattr(candidates[0], 'finish_reason', None)
        raise RuntimeError(
            f"Scene {scene.scene_id} 图片生成失败：API 未返回图片数据 "
            f"(finish_reason={finish_reason}, candidates={len(candidates)})"
        )

    if verbose:
        print(f"[ImageGen] Scene {scene.scene_id} 关键帧已保存: {output_path}")

    return output_path


async def generate_all_keyframes(
    scenes: list[Scene],
    output_dir: str,
    reference_images: Optional[list[str]] = None,
    style_reference: Optional[str] = None,
    config: Optional[PilipiliConfig] = None,
    max_concurrent: int = 3,
    verbose: bool = False,
    characters: Optional[list] = None,  # list[CharacterInfo]
) -> dict[int, str]:
    """
    并发生成所有分镜的关键帧

    Args:
        scenes: 分镜列表
        output_dir: 输出目录
        reference_images: 全局角色参考图
        style_reference: 全局风格参考图
        config: 配置对象
        max_concurrent: 最大并发数（避免 API 限速）
        verbose: 是否打印调试信息
        characters: 角色列表（CharacterInfo），无参考图时用 appearance_prompt 增强一致性

    Returns:
        {scene_id: image_path} 字典
    """
    # 构建 character_id -> CharacterInfo 映射
    char_map: dict[int, object] = {}
    if characters:
        for char in characters:
            cid = char.character_id if hasattr(char, 'character_id') else char.get('character_id')
            if cid is not None:
                char_map[cid] = char

    semaphore = asyncio.Semaphore(max_concurrent)
    results = {}

    async def _generate_with_semaphore(scene: Scene):
        async with semaphore:
            # 优先使用场景级别的角色参考图
            scene_refs = None
            if scene.reference_character and os.path.exists(scene.reference_character):
                scene_refs = [scene.reference_character]
            elif reference_images:
                scene_refs = reference_images

            # 如果没有参考图，尝试用 appearance_prompt 增强 image_prompt
            enhanced_scene = scene
            if not scene_refs and char_map and scene.characters_in_scene:
                # 收集本分镜出现的所有角色的 appearance_prompt
                appearance_parts = []
                for cid in scene.characters_in_scene:
                    char = char_map.get(cid)
                    if char:
                        ap = char.appearance_prompt if hasattr(char, 'appearance_prompt') else char.get('appearance_prompt', '')
                        if ap:
                            appearance_parts.append(ap)
                if appearance_parts:
                    # 将外貌描述追加到 image_prompt 末尾，帮助 Gemini 保持角色一致性
                    from dataclasses import replace as dc_replace
                    extra = "; ".join(appearance_parts)
                    new_prompt = f"{scene.image_prompt}. CHARACTER APPEARANCE (maintain consistency): {extra}"
                    enhanced_scene = dc_replace(scene, image_prompt=new_prompt)

            path = await generate_keyframe(
                scene=enhanced_scene,
                output_dir=output_dir,
                reference_images=scene_refs,
                style_reference=style_reference,
                config=config,
                verbose=verbose,
            )
            results[scene.scene_id] = path

    tasks = [_generate_with_semaphore(scene) for scene in scenes]
    await asyncio.gather(*tasks)

    return results


def generate_all_keyframes_sync(
    scenes: list[Scene],
    output_dir: str,
    reference_images: Optional[list[str]] = None,
    style_reference: Optional[str] = None,
    config: Optional[PilipiliConfig] = None,
    max_concurrent: int = 3,
    verbose: bool = False,
    characters: Optional[list] = None,
) -> dict[int, str]:
    """generate_all_keyframes 的同步版本"""
    return asyncio.run(generate_all_keyframes(
        scenes=scenes,
        output_dir=output_dir,
        reference_images=reference_images,
        style_reference=style_reference,
        config=config,
        max_concurrent=max_concurrent,
        verbose=verbose,
        characters=characters,
    ))


# ============================================================
# 工具函数
# ============================================================

def _detect_mime_type(path: str) -> str:
    """根据文件扩展名检测 MIME 类型"""
    ext = Path(path).suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    return mime_map.get(ext, "image/jpeg")
