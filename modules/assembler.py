"""
噼哩噼哩 Pilipili-AutoVideo
视频组装模块 - FFmpeg 拼接 + 字幕烧录

职责：
- 精确裁剪每段视频到 TTS 时长
- xfade 转场拼接所有片段
- 混合配音音频
- 生成 SRT 字幕并烧录
- 输出最终成品 MP4
"""

import os
import subprocess
import json
import asyncio
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from modules.llm import Scene, VideoScript


# ============================================================
# 数据结构
# ============================================================

@dataclass
class AssemblyPlan:
    """组装计划"""
    scenes: list[Scene]
    video_clips: dict[int, str]      # {scene_id: video_path}
    audio_clips: dict[int, str]      # {scene_id: audio_path}
    output_path: str
    temp_dir: str
    add_subtitles: bool = True
    subtitle_style: str = "default"  # default / minimal / bold


# ============================================================
# 核心组装函数
# ============================================================

def assemble_video(
    plan: AssemblyPlan,
    verbose: bool = False,
) -> str:
    """
    执行完整的视频组装流程

    流程：
    1. 精确裁剪每段视频到 TTS 时长
    2. 生成 SRT 字幕文件
    3. xfade 转场拼接所有片段
    4. 混合配音音频
    5. 烧录字幕

    Returns:
        最终输出视频路径
    """
    os.makedirs(plan.temp_dir, exist_ok=True)
    os.makedirs(os.path.dirname(plan.output_path), exist_ok=True)

    if verbose:
        print(f"[Assembler] 开始组装 {len(plan.scenes)} 个分镜")

    # Step 1: 裁剪每段视频到精确时长
    trimmed_clips = {}
    for scene in plan.scenes:
        clip_path = plan.video_clips.get(scene.scene_id)
        if not clip_path or not os.path.exists(clip_path):
            raise FileNotFoundError(f"Scene {scene.scene_id} 视频片段不存在: {clip_path}")

        trimmed_path = os.path.join(plan.temp_dir, f"trimmed_{scene.scene_id:03d}.mp4")
        _trim_video(clip_path, trimmed_path, scene.duration, verbose=verbose)
        trimmed_clips[scene.scene_id] = trimmed_path

    # Step 2: 生成 SRT 字幕
    srt_path = None
    if plan.add_subtitles:
        srt_path = os.path.join(plan.temp_dir, "subtitles.srt")
        _generate_srt(plan.scenes, plan.audio_clips, srt_path)
        if verbose:
            print(f"[Assembler] 字幕文件已生成: {srt_path}")

    # Step 3: 拼接视频（带转场）
    merged_video = os.path.join(plan.temp_dir, "merged_no_audio.mp4")
    _merge_with_transitions(
        clips=[trimmed_clips[s.scene_id] for s in plan.scenes],
        transitions=[s.transition for s in plan.scenes],
        output_path=merged_video,
        verbose=verbose,
    )

    # Step 4: 混合音频
    merged_with_audio = os.path.join(plan.temp_dir, "merged_with_audio.mp4")
    audio_clips = [plan.audio_clips.get(s.scene_id, "") for s in plan.scenes]
    _mix_audio(
        video_path=merged_video,
        audio_clips=audio_clips,
        scene_durations=[s.duration for s in plan.scenes],
        output_path=merged_with_audio,
        verbose=verbose,
    )

    # Step 5: 烧录字幕
    if srt_path and os.path.exists(srt_path):
        _burn_subtitles(
            video_path=merged_with_audio,
            srt_path=srt_path,
            output_path=plan.output_path,
            style=plan.subtitle_style,
            verbose=verbose,
        )
    else:
        # 无字幕，直接复制
        import shutil
        shutil.copy2(merged_with_audio, plan.output_path)

    if verbose:
        print(f"[Assembler] 组装完成: {plan.output_path}")

    return plan.output_path


# ============================================================
# FFmpeg 工具函数
# ============================================================

def _run_ffmpeg(cmd: list[str], verbose: bool = False) -> None:
    """执行 FFmpeg 命令"""
    if verbose:
        print(f"[FFmpeg] {' '.join(cmd[:6])}...")

    result = subprocess.run(
        cmd,
        capture_output=not verbose,
        text=True,
    )

    if result.returncode != 0:
        error_msg = result.stderr if not verbose else ""
        raise RuntimeError(f"FFmpeg 执行失败 (返回码 {result.returncode}): {error_msg[:500]}")


def _trim_video(input_path: str, output_path: str, duration: float, verbose: bool = False) -> None:
    """精确裁剪视频到指定时长"""
    if os.path.exists(output_path):
        return

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-an",  # 移除原始音频
        "-movflags", "+faststart",
        output_path
    ]
    _run_ffmpeg(cmd, verbose=verbose)


def _merge_with_transitions(
    clips: list[str],
    transitions: list[str],
    output_path: str,
    transition_duration: float = 0.5,
    verbose: bool = False,
) -> None:
    """使用 xfade 滤镜拼接视频片段"""
    if os.path.exists(output_path):
        return

    if len(clips) == 1:
        import shutil
        shutil.copy2(clips[0], output_path)
        return

    # 获取每段视频的精确时长
    durations = [_get_video_duration(clip) for clip in clips]

    # 构建 FFmpeg xfade 滤镜链
    # 格式：[v0][v1]xfade=transition=crossfade:duration=0.5:offset=<d0-0.5>[v01];[v01][v2]xfade=...
    inputs = []
    for clip in clips:
        inputs.extend(["-i", clip])

    filter_parts = []
    current_offset = 0.0

    for i in range(len(clips) - 1):
        current_offset += durations[i] - transition_duration

        # 转场类型映射
        xfade_type = _map_transition(transitions[i + 1] if i + 1 < len(transitions) else "crossfade")

        if i == 0:
            in_label_a = f"[0:v]"
            in_label_b = f"[1:v]"
        else:
            in_label_a = f"[v{i-1}{i}]"
            in_label_b = f"[{i+1}:v]"

        out_label = f"[v{i}{i+1}]"

        filter_parts.append(
            f"{in_label_a}{in_label_b}xfade=transition={xfade_type}:"
            f"duration={transition_duration}:offset={current_offset:.3f}{out_label}"
        )

    final_label = f"[v{len(clips)-2}{len(clips)-1}]"
    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
    ] + inputs + [
        "-filter_complex", filter_complex,
        "-map", final_label,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-movflags", "+faststart",
        output_path
    ]

    _run_ffmpeg(cmd, verbose=verbose)


def _mix_audio(
    video_path: str,
    audio_clips: list[str],
    scene_durations: list[float],
    output_path: str,
    verbose: bool = False,
) -> None:
    """将多段配音混合到视频中"""
    if os.path.exists(output_path):
        return

    # 过滤掉空音频
    valid_audio = [(clip, dur) for clip, dur in zip(audio_clips, scene_durations) if clip and os.path.exists(clip)]

    if not valid_audio:
        # 无音频，直接复制视频
        import shutil
        shutil.copy2(video_path, output_path)
        return

    # 构建音频拼接命令
    audio_inputs = []
    for clip, _ in valid_audio:
        audio_inputs.extend(["-i", clip])

    # 拼接所有音频
    if len(valid_audio) == 1:
        audio_filter = "[1:a]apad[aout]"
        audio_map = "[aout]"
    else:
        concat_inputs = "".join(f"[{i+1}:a]" for i in range(len(valid_audio)))
        audio_filter = f"{concat_inputs}concat=n={len(valid_audio)}:v=0:a=1[aout]"
        audio_map = "[aout]"

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
    ] + audio_inputs + [
        "-filter_complex", audio_filter,
        "-map", "0:v",
        "-map", audio_map,
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_path
    ]

    _run_ffmpeg(cmd, verbose=verbose)


def _burn_subtitles(
    video_path: str,
    srt_path: str,
    output_path: str,
    style: str = "default",
    verbose: bool = False,
) -> None:
    """将 SRT 字幕烧录到视频"""
    if os.path.exists(output_path):
        return

    # 字幕样式
    style_configs = {
        "default": (
            "FontName=PingFang SC,FontSize=22,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,Outline=2,Shadow=1,"
            "Alignment=2,MarginV=30"
        ),
        "minimal": (
            "FontName=PingFang SC,FontSize=18,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,Outline=1,Shadow=0,"
            "Alignment=2,MarginV=20"
        ),
        "bold": (
            "FontName=PingFang SC,FontSize=26,Bold=1,PrimaryColour=&H00FFFF00,"
            "OutlineColour=&H00000000,Outline=3,Shadow=2,"
            "Alignment=2,MarginV=40"
        ),
    }

    style_str = style_configs.get(style, style_configs["default"])

    # 转义路径中的特殊字符
    safe_srt_path = srt_path.replace("\\", "/").replace(":", "\\:")

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"subtitles={safe_srt_path}:force_style='{style_str}'",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-c:a", "copy",
        "-movflags", "+faststart",
        output_path
    ]

    _run_ffmpeg(cmd, verbose=verbose)


def _generate_srt(
    scenes: list[Scene],
    audio_clips: dict[int, str],
    output_path: str,
) -> None:
    """根据分镜旁白和时长生成 SRT 字幕文件"""
    from modules.tts import get_audio_duration

    srt_lines = []
    current_time = 0.0
    index = 1

    for scene in scenes:
        if not scene.voiceover.strip():
            current_time += scene.duration
            continue

        audio_path = audio_clips.get(scene.scene_id, "")
        if audio_path and os.path.exists(audio_path):
            duration = get_audio_duration(audio_path)
        else:
            duration = scene.duration

        start_time = current_time
        end_time = current_time + duration

        # 长文案分行（每行最多 20 个字）
        text = scene.voiceover.strip()
        lines = _split_subtitle_text(text, max_chars=20)

        srt_lines.append(str(index))
        srt_lines.append(f"{_format_srt_time(start_time)} --> {_format_srt_time(end_time)}")
        srt_lines.extend(lines)
        srt_lines.append("")

        current_time += scene.duration
        index += 1

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_lines))


def _split_subtitle_text(text: str, max_chars: int = 20) -> list[str]:
    """将长文本分割为多行字幕"""
    if len(text) <= max_chars:
        return [text]

    lines = []
    while len(text) > max_chars:
        # 尝试在标点符号处断行
        split_pos = max_chars
        for i in range(max_chars, 0, -1):
            if text[i-1] in "，。！？、；：":
                split_pos = i
                break
        lines.append(text[:split_pos])
        text = text[split_pos:]

    if text:
        lines.append(text)

    return lines


def _format_srt_time(seconds: float) -> str:
    """将秒数格式化为 SRT 时间格式 HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _get_video_duration(video_path: str) -> float:
    """使用 ffprobe 获取视频精确时长"""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode == 0:
        return float(result.stdout.strip())
    return 5.0


def _map_transition(transition: str) -> str:
    """将内部转场名映射到 FFmpeg xfade 转场名"""
    mapping = {
        "crossfade": "fade",
        "fade": "fade",
        "wipe": "wipeleft",
        "cut": "fade",  # cut 用极短 fade 模拟
        "zoom": "zoom",
        "slide": "slideleft",
        "dissolve": "dissolve",
    }
    return mapping.get(transition, "fade")
