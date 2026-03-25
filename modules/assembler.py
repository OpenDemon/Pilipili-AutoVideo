"""
噼哩噼哩 Pilipili-AutoVideo
视频组装模块 - FFmpeg 拼接 + 字幕烧录

职责：
- 精确裁剪每段视频到 TTS 时长
- xfade 转场拼接所有片段
- 混合配音音频（精确对齐每段偏移量，考虑 xfade 重叠）
- 生成 SRT 字幕并烧录
- 输出最终成品 MP4（Windows 兼容编码）
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
    aspect_ratio: str = "9:16"       # 画面比例：9:16 竖屏 / 16:9 横屏


# Windows 兼容的 H.264 编码参数
# pix_fmt yuv420p + profile high + level 4.1 确保 Windows 自带播放器可播放
H264_COMPAT_ARGS = [
    "-c:v", "libx264",
    "-preset", "fast",
    "-crf", "18",
    "-pix_fmt", "yuv420p",
    "-profile:v", "high",
    "-level:v", "4.1",
    "-movflags", "+faststart",
]


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
    1. 清理旧的临时文件（确保重新编码）
    2. 精确裁剪每段视频到 TTS 时长 + 统一分辨率
    3. 生成 SRT 字幕文件
    4. xfade 转场拼接所有片段
    5. 混合配音音频（精确对齐偏移量）
    6. 烧录字幕

    Returns:
        最终输出视频路径
    """
    os.makedirs(plan.temp_dir, exist_ok=True)
    os.makedirs(os.path.dirname(plan.output_path), exist_ok=True)

    if verbose:
        print(f"[Assembler] 开始组装 {len(plan.scenes)} 个分镜")

    # 根据 aspect_ratio 确定目标分辨率
    if plan.aspect_ratio in ("9:16", "3:4"):
        target_w, target_h = 1080, 1920  # 竖屏
    else:
        target_w, target_h = 1920, 1080  # 横屏

    # Step 0: 清理旧的临时文件，确保使用最新编码参数
    _clean_temp_files(plan.temp_dir, verbose=verbose)

    # Step 1: 裁剪每段视频到精确时长 + 统一分辨率
    trimmed_clips = {}
    for scene in plan.scenes:
        clip_path = plan.video_clips.get(scene.scene_id)
        if not clip_path or not os.path.exists(clip_path):
            raise FileNotFoundError(f"Scene {scene.scene_id} 视频片段不存在: {clip_path}")

        trimmed_path = os.path.join(plan.temp_dir, f"trimmed_{scene.scene_id:03d}.mp4")
        _trim_video(clip_path, trimmed_path, scene.duration,
                    target_w=target_w, target_h=target_h, verbose=verbose)
        trimmed_clips[scene.scene_id] = trimmed_path

    # Step 2: 生成 SRT 字幕
    srt_path = None
    if plan.add_subtitles:
        srt_path = os.path.join(plan.temp_dir, "subtitles.srt")
        _generate_srt(plan.scenes, plan.audio_clips, srt_path, aspect_ratio=plan.aspect_ratio)
        if verbose:
            print(f"[Assembler] 字幕文件已生成: {srt_path}")

    # Step 3: 拼接视频（带转场）
    transition_duration = 0.5
    merged_video = os.path.join(plan.temp_dir, "merged_no_audio.mp4")
    _merge_with_transitions(
        clips=[trimmed_clips[s.scene_id] for s in plan.scenes],
        transitions=[s.transition for s in plan.scenes],
        output_path=merged_video,
        transition_duration=transition_duration,
        verbose=verbose,
    )

    # Step 4: 混合音频（精确对齐每段偏移量，考虑 xfade 重叠）
    merged_with_audio = os.path.join(plan.temp_dir, "merged_with_audio.mp4")
    audio_clips = [plan.audio_clips.get(s.scene_id, "") for s in plan.scenes]
    scene_durations = [s.duration for s in plan.scenes]
    _mix_audio_aligned(
        video_path=merged_video,
        audio_clips=audio_clips,
        scene_durations=scene_durations,
        transition_duration=transition_duration,
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
            aspect_ratio=plan.aspect_ratio,
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
        print(f"[FFmpeg] {' '.join(cmd)}")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        error_msg = result.stderr or ""
        raise RuntimeError(f"FFmpeg 执行失败 (返回码 {result.returncode}): {error_msg[:500]}")


def _clean_temp_files(temp_dir: str, verbose: bool = False) -> None:
    """清理临时目录中的旧文件，确保重新编码"""
    if not os.path.exists(temp_dir):
        return
    for f in os.listdir(temp_dir):
        fp = os.path.join(temp_dir, f)
        if os.path.isfile(fp):
            os.remove(fp)
            if verbose:
                print(f"[Assembler] 清理旧临时文件: {f}")


def _trim_video(input_path: str, output_path: str, duration: float,
                target_w: int = 1920, target_h: int = 1080,
                verbose: bool = False) -> None:
    """精确裁剪视频到指定时长，并统一缩放到目标分辨率

    使用 scale+pad 方式：先等比缩放到目标尺寸内，再用黑边填充到精确分辨率，
    确保所有片段分辨率一致，避免 xfade 报错。
    编码使用 yuv420p + H.264 High profile 确保 Windows 兼容。
    """
    # scale: 等比缩放使宽高都不超过目标值
    # pad:  用黑色填充到精确的 target_w x target_h
    vf = (
        f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
        f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black,"
        f"setsar=1"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-t", str(duration),
        "-vf", vf,
    ] + H264_COMPAT_ARGS[:-2] + [  # 不需要 movflags（中间文件）
        "-an",  # 移除原始音频
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
    """使用 xfade 滤镜拼接视频片段

    注意：xfade 会使总时长缩短 (N-1) * transition_duration 秒，
    因为每个转场有 transition_duration 秒的重叠。
    音频混合时需要考虑这个偏移。
    """
    if len(clips) == 1:
        import shutil
        shutil.copy2(clips[0], output_path)
        return

    # 获取每段视频的精确时长
    durations = [_get_video_duration(clip) for clip in clips]

    # 构建 FFmpeg xfade 滤镜链
    inputs = []
    for clip in clips:
        inputs.extend(["-i", clip])

    filter_parts = []
    # xfade offset 计算：
    # 第 1 个转场 offset = duration[0] - transition_duration
    # 第 2 个转场 offset = duration[0] + duration[1] - 2 * transition_duration
    # 第 i 个转场 offset = sum(duration[0..i]) - (i+1) * transition_duration
    cumulative_duration = 0.0

    for i in range(len(clips) - 1):
        cumulative_duration += durations[i]
        offset = cumulative_duration - (i + 1) * transition_duration

        # 确保 offset 不为负
        offset = max(offset, 0.001)

        # 转场类型映射
        xfade_type = _map_transition(transitions[i + 1] if i + 1 < len(transitions) else "crossfade")

        if i == 0:
            in_label_a = "[0:v]"
            in_label_b = "[1:v]"
        else:
            in_label_a = f"[v{i-1}{i}]"
            in_label_b = f"[{i+1}:v]"

        out_label = f"[v{i}{i+1}]"

        filter_parts.append(
            f"{in_label_a}{in_label_b}xfade=transition={xfade_type}:"
            f"duration={transition_duration}:offset={offset:.3f}{out_label}"
        )

    final_label = f"[v{len(clips)-2}{len(clips)-1}]"
    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
    ] + inputs + [
        "-filter_complex", filter_complex,
        "-map", final_label,
    ] + H264_COMPAT_ARGS + [
        output_path
    ]

    _run_ffmpeg(cmd, verbose=verbose)


def _mix_audio_aligned(
    video_path: str,
    audio_clips: list[str],
    scene_durations: list[float],
    transition_duration: float,
    output_path: str,
    verbose: bool = False,
) -> None:
    """将多段配音混合到视频中，精确对齐每段音频的起始偏移量

    关键：xfade 转场会使视频总时长缩短，每个转场有 transition_duration 秒重叠。
    因此第 i 段音频的起始时间 = sum(duration[0..i-1]) - i * transition_duration

    使用 adelay 滤镜精确设置每段音频的起始偏移，然后 amix 混合所有音频轨。
    """
    # 过滤掉空音频
    valid_entries = []
    for i, (clip, dur) in enumerate(zip(audio_clips, scene_durations)):
        if clip and os.path.exists(clip):
            # 计算该段音频在最终视频中的起始时间
            # 前 i 段视频的总时长 - i 个转场重叠
            offset_s = sum(scene_durations[:i]) - i * transition_duration
            offset_s = max(offset_s, 0.0)
            valid_entries.append((clip, offset_s))

    if not valid_entries:
        import shutil
        shutil.copy2(video_path, output_path)
        return

    # 构建 FFmpeg 命令
    # 输入：[0] = 视频, [1..N] = 各段音频
    audio_inputs = []
    for clip, _ in valid_entries:
        audio_inputs.extend(["-i", clip])

    # 构建滤镜：每段音频用 adelay 设置偏移，然后 amix 混合
    filter_parts = []
    mix_inputs = []

    for idx, (clip, offset_s) in enumerate(valid_entries):
        input_idx = idx + 1  # [0] 是视频
        delay_ms = int(offset_s * 1000)
        label = f"[a{idx}]"

        if delay_ms > 0:
            filter_parts.append(f"[{input_idx}:a]adelay={delay_ms}|{delay_ms}{label}")
        else:
            filter_parts.append(f"[{input_idx}:a]acopy{label}")

        mix_inputs.append(label)

    # amix 混合所有音频轨
    mix_input_str = "".join(mix_inputs)
    filter_parts.append(
        f"{mix_input_str}amix=inputs={len(valid_entries)}:duration=longest:normalize=0[aout]"
    )

    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
    ] + audio_inputs + [
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[aout]",
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
    aspect_ratio: str = "9:16",
) -> None:
    """将 SRT 字幕烧录到视频"""
    # 竖屏字幕需要更大字号和更高的底部边距
    is_vertical = aspect_ratio in ("9:16", "3:4")

    # 字幕样式 - 使用 Windows 通用字体
    if is_vertical:
        style_configs = {
            "default": (
                "FontName=Microsoft YaHei,FontSize=16,PrimaryColour=&H00FFFFFF,"
                "OutlineColour=&H00000000,Outline=2,Shadow=1,"
                "Alignment=2,MarginV=60"
            ),
            "minimal": (
                "FontName=Microsoft YaHei,FontSize=14,PrimaryColour=&H00FFFFFF,"
                "OutlineColour=&H00000000,Outline=1,Shadow=0,"
                "Alignment=2,MarginV=50"
            ),
            "bold": (
                "FontName=Microsoft YaHei,FontSize=20,Bold=1,PrimaryColour=&H00FFFF00,"
                "OutlineColour=&H00000000,Outline=3,Shadow=2,"
                "Alignment=2,MarginV=80"
            ),
        }
    else:
        style_configs = {
            "default": (
                "FontName=Microsoft YaHei,FontSize=22,PrimaryColour=&H00FFFFFF,"
                "OutlineColour=&H00000000,Outline=2,Shadow=1,"
                "Alignment=2,MarginV=30"
            ),
            "minimal": (
                "FontName=Microsoft YaHei,FontSize=18,PrimaryColour=&H00FFFFFF,"
                "OutlineColour=&H00000000,Outline=1,Shadow=0,"
                "Alignment=2,MarginV=20"
            ),
            "bold": (
                "FontName=Microsoft YaHei,FontSize=26,Bold=1,PrimaryColour=&H00FFFF00,"
                "OutlineColour=&H00000000,Outline=3,Shadow=2,"
                "Alignment=2,MarginV=40"
            ),
        }

    style_str = style_configs.get(style, style_configs["default"])

    # 转义路径中的特殊字符（FFmpeg subtitles 滤镜要求）
    safe_srt_path = srt_path.replace("\\", "/").replace(":", "\\:")

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"subtitles={safe_srt_path}:force_style='{style_str}'",
    ] + H264_COMPAT_ARGS + [
        "-c:a", "copy",
        output_path
    ]

    _run_ffmpeg(cmd, verbose=verbose)


def _clean_voiceover_for_subtitle(text: str) -> str:
    """清洗 voiceover 文本用于字幕显示：移除说话人前缀（如 男：、女（英语）：）"""
    import re
    cleaned = re.sub(r'男[\uff08(][^\uff09)]*[\uff09)]\uff1a|女[\uff08(][^\uff09)]*[\uff09)]\uff1a|男[\uff1a:]|女[\uff1a:]', '', text)
    return cleaned.strip()


def _generate_srt(
    scenes: list[Scene],
    audio_clips: dict[int, str],
    output_path: str,
    transition_duration: float = 0.5,
    aspect_ratio: str = "9:16",
) -> None:
    """根据分镜旁白和时长生成 SRT 字幕文件

    字幕时间轴需要考虑 xfade 转场重叠：
    第 i 段字幕起始时间 = sum(duration[0..i-1]) - i * transition_duration
    """
    from modules.tts import get_audio_duration

    srt_lines = []
    index = 1
    durations = [s.duration for s in scenes]

    for i, scene in enumerate(scenes):
        if not scene.voiceover.strip():
            continue

        # 计算该段在最终视频中的起始时间（考虑 xfade 重叠）
        start_time = sum(durations[:i]) - i * transition_duration
        start_time = max(start_time, 0.0)

        # 获取音频实际时长作为字幕持续时间
        audio_path = audio_clips.get(scene.scene_id, "")
        if audio_path and os.path.exists(audio_path):
            duration = get_audio_duration(audio_path)
        else:
            duration = scene.duration

        end_time = start_time + duration

        # 清洗说话人前缀 + 长文案分行
        text = _clean_voiceover_for_subtitle(scene.voiceover)
        # 竖屏每行字数更少（屏幕窄）
        max_chars = 14 if aspect_ratio in ("9:16", "3:4") else 20
        lines = _split_subtitle_text(text, max_chars=max_chars)

        srt_lines.append(str(index))
        srt_lines.append(f"{_format_srt_time(start_time)} --> {_format_srt_time(end_time)}")
        srt_lines.extend(lines)
        srt_lines.append("")

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
