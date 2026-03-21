"""
噼哩噼哩 Pilipili-AutoVideo
视频生成模块 - Kling 3.0 / Seedance 1.5

职责：
- 图生视频（I2V）：以关键帧为首帧，生成动态视频片段
- 支持 Kling 3.0（默认，动态能量强）和 Seedance 1.5（主体一致性强）
- 智能路由：根据场景内容自动选择最优引擎
- 异步轮询任务状态，支持断点续传
"""

import os
import asyncio
import aiohttp
import json
import time
import jwt
import hashlib
from pathlib import Path
from typing import Optional, Literal
from datetime import datetime

from core.config import PilipiliConfig, get_config
from modules.llm import Scene


# ============================================================
# 视频引擎路由逻辑
# ============================================================

def smart_route_engine(scene: Scene, default: str = "kling") -> str:
    """
    根据场景内容智能选择视频引擎

    规则：
    - 包含对话/口型同步关键词 → Seedance（原生音素级口型同步）
    - 包含多人/多角色场景 → Seedance（多主体一致性更强）
    - 包含动作/运动/体育 → Kling（动态能量更强）
    - 其他 → 使用默认引擎
    """
    seedance_keywords = [
        "talking", "speaking", "dialogue", "conversation", "lip sync",
        "multiple characters", "crowd", "group", "people talking",
        "interview", "narration", "说话", "对话", "多人", "人群"
    ]

    kling_keywords = [
        "action", "running", "jumping", "sports", "explosion", "fast",
        "dynamic", "energetic", "chase", "fight", "dance",
        "动作", "奔跑", "跳跃", "运动", "爆炸", "快速", "舞蹈"
    ]

    prompt_lower = (scene.video_prompt + " " + " ".join(scene.style_tags)).lower()

    seedance_score = sum(1 for kw in seedance_keywords if kw.lower() in prompt_lower)
    kling_score = sum(1 for kw in kling_keywords if kw.lower() in prompt_lower)

    if seedance_score > kling_score:
        return "seedance"
    elif kling_score > seedance_score:
        return "kling"
    else:
        return default


# ============================================================
# Kling 3.0 API
# ============================================================

def _generate_kling_jwt(api_key: str, api_secret: str) -> str:
    """生成 Kling API JWT Token（遵循官方文档，显式传 headers）"""
    jwt_headers = {
        "alg": "HS256",
        "typ": "JWT",
    }
    payload = {
        "iss": api_key,
        "exp": int(time.time()) + 1800,
        "nbf": int(time.time()) - 5,
    }
    return jwt.encode(payload, api_secret, algorithm="HS256", headers=jwt_headers)


async def _submit_kling_i2v(
    image_path: str,
    scene: Scene,
    config: PilipiliConfig,
    session: aiohttp.ClientSession,
) -> str:
    """提交 Kling I2V 任务，返回 task_id"""
    api_key = config.video_gen.kling.api_key
    api_secret = config.video_gen.kling.api_secret

    if not api_key or not api_secret:
        raise ValueError("Kling API Key/Secret 未配置")

    token = _generate_kling_jwt(api_key, api_secret)

    # 读取图片并转 base64
    import base64
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    # Kling API 要求纯 base64 字符串，不能带 data:image/xxx;base64, 前缀
    # 官方文档："When using Base64, do NOT add any prefix like data:image/png;base64,"

    # 时长：Kling 支持 5/10 秒，选择最接近的
    duration = 5 if scene.duration <= 7 else 10

    # 根据 quality 配置确定输出分辨率
    quality = config.video_gen.kling.default_quality or "high"
    # Kling API: resolution 可选 "480p" / "720p" / "1080p" / "2k"
    # high → 1080p, 其他 → 720p
    resolution = "1080p" if quality == "high" else "720p"

    payload = {
        "model_name": config.video_gen.kling.model or "kling-v3",
        "image": img_b64,
        "prompt": scene.video_prompt,
        "negative_prompt": "blurry, low quality, distorted, deformed, ugly, bad anatomy",
        "cfg_scale": 0.5,
        "mode": "std",
        "duration": str(duration),
        "aspect_ratio": config.video_gen.kling.default_ratio or "16:9",
        "resolution": resolution,
    }

    url = f"{config.video_gen.kling.base_url}/v1/videos/image2video"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    async with session.post(url, json=payload, headers=headers) as resp:
        resp_text = await resp.text()
        try:
            result = json.loads(resp_text)
        except json.JSONDecodeError:
            raise RuntimeError(f"Kling API 返回非 JSON 响应 (HTTP {resp.status}): {resp_text[:200]}")

    if result.get("code") != 0:
        raise RuntimeError(f"Kling 任务提交失败 (code={result.get('code')}, msg={result.get('message')}): {result}")

    return result["data"]["task_id"]


async def _poll_kling_task(
    task_id: str,
    config: PilipiliConfig,
    session: aiohttp.ClientSession,
    timeout: int = 300,
    poll_interval: int = 5,
) -> str:
    """轮询 Kling 任务状态，返回视频 URL"""
    api_key = config.video_gen.kling.api_key
    api_secret = config.video_gen.kling.api_secret

    url = f"{config.video_gen.kling.base_url}/v1/videos/image2video/{task_id}"
    start_time = time.time()

    while time.time() - start_time < timeout:
        token = _generate_kling_jwt(api_key, api_secret)
        headers = {"Authorization": f"Bearer {token}"}

        async with session.get(url, headers=headers) as resp:
            resp_text = await resp.text()
            try:
                result = json.loads(resp_text)
            except json.JSONDecodeError:
                raise RuntimeError(f"Kling 轮询返回非 JSON 响应 (HTTP {resp.status}): {resp_text[:200]}")

        if result.get("code") != 0:
            raise RuntimeError(f"Kling 任务查询失败 (code={result.get('code')}, msg={result.get('message')}): {result}")

        status = result["data"]["task_status"]

        if status == "succeed":
            videos = result["data"]["task_result"]["videos"]
            if videos:
                return videos[0]["url"]
            raise RuntimeError("Kling 任务成功但无视频 URL")

        elif status == "failed":
            raise RuntimeError(f"Kling 任务失败: {result['data'].get('task_status_msg', '未知错误')}")

        await asyncio.sleep(poll_interval)

    raise TimeoutError(f"Kling 任务 {task_id} 超时（{timeout}s）")


# ============================================================
# Seedance 1.5 API
# ============================================================

async def _submit_seedance_i2v(
    image_path: str,
    scene: Scene,
    config: PilipiliConfig,
    session: aiohttp.ClientSession,
) -> str:
    """提交 Seedance I2V 任务，返回 task_id"""
    api_key = config.video_gen.seedance.api_key

    if not api_key:
        raise ValueError("Seedance (Volcengine) API Key 未配置")

    import base64
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    ext = Path(image_path).suffix.lower()
    mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
    mime_type = mime_map.get(ext, "image/jpeg")
    image_data_url = f"data:{mime_type};base64,{img_b64}"

    # Seedance 支持 5/10 秒
    duration = 5 if scene.duration <= 7 else 10

    payload = {
        "model": config.video_gen.seedance.model or "doubao-seedance-1-5-pro-250528",
        "content": [
            {
                "type": "image_url",
                "image_url": {"url": image_data_url}
            },
            {
                "type": "text",
                "text": scene.video_prompt
            }
        ],
        "duration": duration,
        "ratio": config.video_gen.seedance.default_ratio or "16:9",
        "seed": -1,
    }

    url = f"{config.video_gen.seedance.base_url}/contents/generations/tasks"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with session.post(url, json=payload, headers=headers) as resp:
        resp_text = await resp.text()
        try:
            result = json.loads(resp_text)
        except json.JSONDecodeError:
            raise RuntimeError(f"Seedance API 返回非 JSON 响应 (HTTP {resp.status}): {resp_text[:200]}")

    if "id" not in result:
        raise RuntimeError(f"Seedance 任务提交失败: {result}")

    return result["id"]


async def _poll_seedance_task(
    task_id: str,
    config: PilipiliConfig,
    session: aiohttp.ClientSession,
    timeout: int = 300,
    poll_interval: int = 5,
) -> str:
    """轮询 Seedance 任务状态，返回视频 URL"""
    api_key = config.video_gen.seedance.api_key
    url = f"{config.video_gen.seedance.base_url}/contents/generations/tasks/{task_id}"
    headers = {"Authorization": f"Bearer {api_key}"}
    start_time = time.time()

    while time.time() - start_time < timeout:
        async with session.get(url, headers=headers) as resp:
            resp_text = await resp.text()
            try:
                result = json.loads(resp_text)
            except json.JSONDecodeError:
                raise RuntimeError(f"Seedance 轮询返回非 JSON 响应 (HTTP {resp.status}): {resp_text[:200]}")

        status = result.get("status", "")

        if status == "succeeded":
            content = result.get("content", [])
            for item in content:
                if item.get("type") == "video_url":
                    return item["video_url"]["url"]
            raise RuntimeError("Seedance 任务成功但无视频 URL")

        elif status == "failed":
            raise RuntimeError(f"Seedance 任务失败: {result.get('error', '未知错误')}")

        await asyncio.sleep(poll_interval)

    raise TimeoutError(f"Seedance 任务 {task_id} 超时（{timeout}s）")


# ============================================================
# 统一视频生成接口
# ============================================================

async def generate_video_clip(
    scene: Scene,
    image_path: str,
    output_dir: str,
    engine: Optional[str] = None,
    auto_route: bool = True,
    config: Optional[PilipiliConfig] = None,
    verbose: bool = False,
) -> str:
    """
    为单个分镜生成视频片段

    Args:
        scene: 分镜场景对象
        image_path: 首帧关键图路径
        output_dir: 输出目录
        engine: 指定引擎 "kling" 或 "seedance"（可选）
        auto_route: 是否启用智能路由
        config: 配置对象
        verbose: 是否打印调试信息

    Returns:
        本地视频文件路径
    """
    if config is None:
        config = get_config()

    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, f"scene_{scene.scene_id:03d}_clip.mp4")

    # 断点续传
    if os.path.exists(output_path):
        if verbose:
            print(f"[VideoGen] Scene {scene.scene_id} 视频片段已存在，跳过")
        return output_path

    # 选择引擎
    if engine:
        selected_engine = engine
    elif auto_route:
        selected_engine = smart_route_engine(scene, config.video_gen.default_provider)
    else:
        selected_engine = config.video_gen.default_provider

    if verbose:
        print(f"[VideoGen] Scene {scene.scene_id} 使用引擎: {selected_engine}")
        print(f"[VideoGen] 视频提示词: {scene.video_prompt[:80]}...")

    async with aiohttp.ClientSession() as session:
        # 提交任务
        if selected_engine == "kling":
            task_id = await _submit_kling_i2v(image_path, scene, config, session)
            if verbose:
                print(f"[VideoGen] Kling 任务已提交: {task_id}")
            video_url = await _poll_kling_task(task_id, config, session)
        elif selected_engine == "seedance":
            task_id = await _submit_seedance_i2v(image_path, scene, config, session)
            if verbose:
                print(f"[VideoGen] Seedance 任务已提交: {task_id}")
            video_url = await _poll_seedance_task(task_id, config, session)
        else:
            raise ValueError(f"不支持的视频引擎: {selected_engine}")

        # 下载视频
        if verbose:
            print(f"[VideoGen] Scene {scene.scene_id} 生成完成，下载中...")

        async with session.get(video_url) as resp:
            video_data = await resp.read()

    with open(output_path, "wb") as f:
        f.write(video_data)

    if verbose:
        print(f"[VideoGen] Scene {scene.scene_id} 视频已保存: {output_path}")

    return output_path


async def generate_all_video_clips(
    scenes: list[Scene],
    keyframe_paths: dict[int, str],
    output_dir: str,
    engine: Optional[str] = None,
    auto_route: bool = True,
    config: Optional[PilipiliConfig] = None,
    max_concurrent: int = 3,
    verbose: bool = False,
) -> dict[int, str]:
    """
    并发生成所有分镜的视频片段

    Returns:
        {scene_id: video_path} 字典
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    results = {}

    async def _generate_with_semaphore(scene: Scene):
        async with semaphore:
            image_path = keyframe_paths.get(scene.scene_id)
            if not image_path or not os.path.exists(image_path):
                raise FileNotFoundError(f"Scene {scene.scene_id} 关键帧图片不存在: {image_path}")

            path = await generate_video_clip(
                scene=scene,
                image_path=image_path,
                output_dir=output_dir,
                engine=engine,
                auto_route=auto_route,
                config=config,
                verbose=verbose,
            )
            results[scene.scene_id] = path

    tasks = [_generate_with_semaphore(scene) for scene in scenes]
    await asyncio.gather(*tasks)

    return results


def generate_all_video_clips_sync(
    scenes: list[Scene],
    keyframe_paths: dict[int, str],
    output_dir: str,
    engine: Optional[str] = None,
    auto_route: bool = True,
    config: Optional[PilipiliConfig] = None,
    max_concurrent: int = 3,
    verbose: bool = False,
) -> dict[int, str]:
    """generate_all_video_clips 的同步版本"""
    return asyncio.run(generate_all_video_clips(
        scenes=scenes,
        keyframe_paths=keyframe_paths,
        output_dir=output_dir,
        engine=engine,
        auto_route=auto_route,
        config=config,
        max_concurrent=max_concurrent,
        verbose=verbose,
    ))
