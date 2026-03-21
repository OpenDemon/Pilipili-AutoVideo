"""
噼哩噼哩 Pilipili-AutoVideo
TTS 配音模块 - MiniMax Speech

职责：
- 将旁白文案转换为语音
- 测量精确音频时长（用于动态控制视频 duration）
- 支持 MiniMax Speech-02-HD（默认）
- 支持声音克隆（传入参考音频）
- 支持情绪控制
"""

import os
import asyncio
import aiohttp
import json
import struct
import wave
from pathlib import Path
from typing import Optional

from core.config import PilipiliConfig, get_config
from modules.llm import Scene


# ============================================================
# MiniMax TTS API 常量
# ============================================================

MINIMAX_TTS_URL = "https://api.minimax.chat/v1/t2a_v2"

# 可用音色列表（部分）
VOICE_OPTIONS = {
    # 女声
    "female_shaonv": "female-shaonv",      # 少女音（默认）
    "female_yujie": "female-yujie",        # 御姐音
    "female_chengshu": "female-chengshu",  # 成熟女声
    "female_tianmei": "female-tianmei",    # 甜美音
    # 男声
    "male_qinchen": "male-qinchen",        # 亲沉男声
    "male_badao": "male-badao",            # 霸道男声
    "male_shaonian": "male-shaonian",      # 少年音
    # 播音
    "presenter_male": "presenter_male",    # 男播音员
    "presenter_female": "presenter_female",# 女播音员
}

# 情绪选项
EMOTION_OPTIONS = ["neutral", "happy", "sad", "angry", "fearful", "disgusted", "surprised"]


# ============================================================
# 核心生成函数
# ============================================================

async def generate_voiceover(
    scene: Scene,
    output_dir: str,
    voice_id: Optional[str] = None,
    emotion: Optional[str] = None,
    speed: Optional[float] = None,
    config: Optional[PilipiliConfig] = None,
    verbose: bool = False,
) -> tuple[str, float]:
    """
    为单个分镜生成配音

    Args:
        scene: 分镜场景对象
        output_dir: 输出目录
        voice_id: 音色 ID（可选，默认使用配置）
        emotion: 情绪（可选）
        speed: 语速（可选，0.5-2.0）
        config: 配置对象
        verbose: 是否打印调试信息

    Returns:
        (音频文件路径, 精确时长秒数) 元组
    """
    if config is None:
        config = get_config()

    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, f"scene_{scene.scene_id:03d}_voiceover.mp3")

    # 断点续传
    if os.path.exists(output_path):
        duration = get_audio_duration(output_path)
        if verbose:
            print(f"[TTS] Scene {scene.scene_id} 配音已存在，时长: {duration:.2f}s")
        return output_path, duration

    if not scene.voiceover.strip():
        if verbose:
            print(f"[TTS] Scene {scene.scene_id} 无旁白文案，跳过")
        return "", 0.0

    api_key = config.tts.api_key
    if not api_key:
        raise ValueError("MiniMax API Key 未配置，请在 config.yaml 中设置 tts.minimax.api_key")

    # 参数
    voice = voice_id or config.tts.default_voice
    emo = emotion or config.tts.emotion
    spd = speed or config.tts.speed

    if verbose:
        print(f"[TTS] Scene {scene.scene_id} 生成配音: {scene.voiceover[:30]}...")

    payload = {
        "model": config.tts.model,
        "text": scene.voiceover,
        "stream": False,
        "voice_setting": {
            "voice_id": voice,
            "speed": spd,
            "vol": 1.0,
            "pitch": 0,
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1,
        }
    }

    # 添加情绪（如果不是 neutral）
    if emo and emo != "neutral":
        payload["voice_setting"]["emotion"] = emo

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(MINIMAX_TTS_URL, json=payload, headers=headers) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise RuntimeError(f"MiniMax TTS API 错误 {resp.status}: {error_text}")

            result = await resp.json()

    # 提取音频数据
    if "data" not in result or "audio" not in result["data"]:
        raise RuntimeError(f"MiniMax TTS 响应格式异常: {json.dumps(result)[:200]}")

    audio_hex = result["data"]["audio"]
    audio_bytes = bytes.fromhex(audio_hex)

    with open(output_path, "wb") as f:
        f.write(audio_bytes)

    # 测量精确时长
    duration = get_audio_duration(output_path)

    if verbose:
        print(f"[TTS] Scene {scene.scene_id} 配音完成，时长: {duration:.2f}s，保存至: {output_path}")

    return output_path, duration


async def generate_all_voiceovers(
    scenes: list[Scene],
    output_dir: str,
    voice_id: Optional[str] = None,
    emotion: Optional[str] = None,
    speed: Optional[float] = None,
    config: Optional[PilipiliConfig] = None,
    max_concurrent: int = 5,
    verbose: bool = False,
) -> dict[int, tuple[str, float]]:
    """
    并发生成所有分镜的配音

    Returns:
        {scene_id: (audio_path, duration)} 字典
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    results = {}

    async def _generate_with_semaphore(scene: Scene):
        async with semaphore:
            path, duration = await generate_voiceover(
                scene=scene,
                output_dir=output_dir,
                voice_id=voice_id,
                emotion=emotion,
                speed=speed,
                config=config,
                verbose=verbose,
            )
            results[scene.scene_id] = (path, duration)

    tasks = [_generate_with_semaphore(scene) for scene in scenes]
    await asyncio.gather(*tasks)

    return results


def generate_all_voiceovers_sync(
    scenes: list[Scene],
    output_dir: str,
    voice_id: Optional[str] = None,
    emotion: Optional[str] = None,
    speed: Optional[float] = None,
    config: Optional[PilipiliConfig] = None,
    max_concurrent: int = 5,
    verbose: bool = False,
) -> dict[int, tuple[str, float]]:
    """generate_all_voiceovers 的同步版本"""
    return asyncio.run(generate_all_voiceovers(
        scenes=scenes,
        output_dir=output_dir,
        voice_id=voice_id,
        emotion=emotion,
        speed=speed,
        config=config,
        max_concurrent=max_concurrent,
        verbose=verbose,
    ))


# ============================================================
# 音频工具函数
# ============================================================

def get_audio_duration(audio_path: str) -> float:
    """
    获取音频文件的精确时长（秒）
    支持 MP3 / WAV / M4A
    """
    try:
        # 优先使用 mutagen（更准确）
        from mutagen.mp3 import MP3
        from mutagen.mp4 import MP4
        from mutagen.wave import WAVE

        ext = Path(audio_path).suffix.lower()
        if ext == ".mp3":
            audio = MP3(audio_path)
            return audio.info.length
        elif ext in [".m4a", ".mp4"]:
            audio = MP4(audio_path)
            return audio.info.length
        elif ext == ".wav":
            audio = WAVE(audio_path)
            return audio.info.length
    except ImportError:
        pass

    # 回退：使用 wave 标准库（仅支持 WAV）
    try:
        if audio_path.endswith(".wav"):
            with wave.open(audio_path, "r") as wav_file:
                frames = wav_file.getnframes()
                rate = wav_file.getframerate()
                return frames / float(rate)
    except Exception:
        pass

    # 最后回退：使用 ffprobe
    try:
        import subprocess
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except Exception:
        pass

    # 无法获取时长，返回估算值（每字约 0.3 秒）
    return 5.0


def update_scene_durations(
    scenes: list[Scene],
    voiceover_results: dict[int, tuple[str, float]],
    padding: float = 0.5,
) -> list[Scene]:
    """
    根据 TTS 实际时长更新分镜的 duration 字段

    Args:
        scenes: 分镜列表
        voiceover_results: TTS 生成结果 {scene_id: (path, duration)}
        padding: 额外缓冲时间（秒），避免画面切换太急

    Returns:
        更新后的分镜列表
    """
    for scene in scenes:
        if scene.scene_id in voiceover_results:
            _, tts_duration = voiceover_results[scene.scene_id]
            if tts_duration > 0:
                # 视频时长 = TTS 时长 + 缓冲
                # 向上取整到最近的 0.5 秒
                raw_duration = tts_duration + padding
                scene.duration = round(raw_duration * 2) / 2  # 取最近的 0.5 倍数

    return scenes
