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
                "Please maintain the appearance, style and characteristics of the subjects shown in the reference images above."
            ))

    # 添加风格参考图
    if style_reference and os.path.exists(style_reference):
        with open(style_reference, "rb") as f:
            style_data = f.read()
        mime_type = _detect_mime_type(style_reference)
        contents.append(types.Part.from_bytes(data=style_data, mime_type=mime_type))
        contents.append(types.Part.from_text(
            "Please use the visual style, color palette and aesthetic shown in the style reference image above."
        ))

    # 添加主提示词
    contents.append(types.Part.from_text(full_prompt))

    # 调用 API
    response = client.models.generate_content(
        model=config.image_gen.model,
        contents=contents,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
        )
    )

    # 提取图片数据
    image_saved = False
    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            img_data = part.inline_data.data
            if isinstance(img_data, str):
                img_data = base64.b64decode(img_data)
            with open(output_path, "wb") as f:
                f.write(img_data)
            image_saved = True
            break

    if not image_saved:
        raise RuntimeError(f"Scene {scene.scene_id} 图片生成失败：API 未返回图片数据")

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

    Returns:
        {scene_id: image_path} 字典
    """
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

            path = await generate_keyframe(
                scene=scene,
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
