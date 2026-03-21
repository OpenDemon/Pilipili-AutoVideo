"""
噼哩噼哩 Pilipili-AutoVideo
剪映草稿生成模块 - pyJianYingDraft

职责：
- 将生成的视频片段、音频、字幕自动组装为剪映草稿工程文件
- 用户可直接在剪映中打开进行最终微调
- 支持自动设置转场、字幕样式、音频轨道
- 这是"AI 做 90%，人类做最后 10%"的关键闭环
"""

import os
import json
import shutil
from pathlib import Path
from typing import Optional

from modules.llm import Scene, VideoScript


def generate_jianying_draft(
    script: VideoScript,
    video_clips: dict[int, str],
    audio_clips: dict[int, str],
    output_dir: str,
    project_name: str = "噼哩噼哩作品",
    verbose: bool = False,
) -> str:
    """
    生成剪映草稿工程文件

    Args:
        script: 完整视频脚本
        video_clips: {scene_id: video_path}
        audio_clips: {scene_id: audio_path}
        output_dir: 输出目录（草稿文件夹）
        project_name: 项目名称
        verbose: 是否打印调试信息

    Returns:
        草稿文件夹路径（可直接导入剪映）
    """
    try:
        import pyJianYingDraft as draft
        return _generate_with_pyjianyingdraft(
            script, video_clips, audio_clips, output_dir, project_name, verbose
        )
    except ImportError:
        # 回退：生成标准 EDL 格式（通用剪辑软件可导入）
        if verbose:
            print("[JianyingDraft] pyJianYingDraft 未安装，回退到 EDL 格式")
        return _generate_edl_fallback(
            script, video_clips, audio_clips, output_dir, project_name, verbose
        )


def _generate_with_pyjianyingdraft(
    script: VideoScript,
    video_clips: dict[int, str],
    audio_clips: dict[int, str],
    output_dir: str,
    project_name: str,
    verbose: bool,
) -> str:
    """使用 pyJianYingDraft 生成标准剪映草稿"""
    import pyJianYingDraft as draft
    from pyJianYingDraft import trange, Intro_type, Track_type

    os.makedirs(output_dir, exist_ok=True)

    # 创建草稿
    jy_draft = draft.Script_file(1920, 1080)

    # 当前时间轴位置（微秒）
    current_us = 0

    for scene in script.scenes:
        video_path = video_clips.get(scene.scene_id)
        audio_path = audio_clips.get(scene.scene_id)

        if not video_path or not os.path.exists(video_path):
            continue

        # 时长（微秒）
        duration_us = int(scene.duration * 1_000_000)

        # 添加视频片段
        video_material = draft.Video_material(video_path)
        video_segment = draft.Video_segment(
            video_material,
            trange(f"{current_us}us", f"{duration_us}us"),
            source_timerange=trange("0us", f"{duration_us}us"),
        )
        jy_draft.add_segment(video_segment)

        # 添加配音
        if audio_path and os.path.exists(audio_path):
            audio_material = draft.Audio_material(audio_path)
            audio_segment = draft.Audio_segment(
                audio_material,
                trange(f"{current_us}us", f"{duration_us}us"),
                source_timerange=trange("0us", f"{duration_us}us"),
                volume=1.0,
            )
            jy_draft.add_segment(audio_segment, track_type=Track_type.audio)

        # 添加字幕
        if scene.voiceover.strip():
            text_segment = draft.Text_segment(
                scene.voiceover,
                trange(f"{current_us}us", f"{duration_us}us"),
                style=draft.Text_style(
                    font_size=8.0,
                    bold=False,
                    italic=False,
                    color=(1.0, 1.0, 1.0),  # 白色
                    border_color=(0.0, 0.0, 0.0),  # 黑色描边
                    border_width=0.08,
                ),
                clip_settings=draft.Clip_settings(transform_y=-0.85),  # 底部字幕
            )
            jy_draft.add_segment(text_segment, track_type=Track_type.text)

        current_us += duration_us

    # 保存草稿
    draft_path = os.path.join(output_dir, f"{project_name}.draft")
    jy_draft.dumps(draft_path)

    if verbose:
        print(f"[JianyingDraft] 剪映草稿已生成: {draft_path}")

    return draft_path


def _generate_edl_fallback(
    script: VideoScript,
    video_clips: dict[int, str],
    audio_clips: dict[int, str],
    output_dir: str,
    project_name: str,
    verbose: bool,
) -> str:
    """
    回退方案：生成 EDL（Edit Decision List）文件
    可导入 Premiere Pro、DaVinci Resolve 等专业剪辑软件
    同时生成一个 JSON 工程描述文件
    """
    os.makedirs(output_dir, exist_ok=True)

    # 生成 EDL 文件
    edl_path = os.path.join(output_dir, f"{project_name}.edl")
    edl_lines = [
        "TITLE: " + project_name,
        "FCM: NON-DROP FRAME",
        "",
    ]

    current_tc = 0  # 帧数（25fps）
    fps = 25

    for i, scene in enumerate(script.scenes, 1):
        video_path = video_clips.get(scene.scene_id)
        if not video_path:
            continue

        duration_frames = int(scene.duration * fps)
        src_in = _frames_to_tc(0, fps)
        src_out = _frames_to_tc(duration_frames, fps)
        rec_in = _frames_to_tc(current_tc, fps)
        rec_out = _frames_to_tc(current_tc + duration_frames, fps)

        edl_lines.append(f"{i:03d}  AX       V     C        {src_in} {src_out} {rec_in} {rec_out}")
        edl_lines.append(f"* FROM CLIP NAME: {os.path.basename(video_path)}")
        edl_lines.append("")

        current_tc += duration_frames

    with open(edl_path, "w", encoding="utf-8") as f:
        f.write("\n".join(edl_lines))

    # 生成 JSON 工程描述（包含完整信息）
    project_json = {
        "project_name": project_name,
        "title": script.title,
        "topic": script.topic,
        "total_duration": sum(s.duration for s in script.scenes),
        "resolution": "1920x1080",
        "fps": fps,
        "scenes": []
    }

    for scene in script.scenes:
        project_json["scenes"].append({
            "scene_id": scene.scene_id,
            "duration": scene.duration,
            "voiceover": scene.voiceover,
            "video_clip": video_clips.get(scene.scene_id, ""),
            "audio_clip": audio_clips.get(scene.scene_id, ""),
            "transition": scene.transition,
            "image_prompt": scene.image_prompt,
            "video_prompt": scene.video_prompt,
        })

    json_path = os.path.join(output_dir, f"{project_name}_project.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(project_json, f, ensure_ascii=False, indent=2)

    # 生成 SRT 字幕文件（独立文件，方便导入）
    srt_path = os.path.join(output_dir, f"{project_name}.srt")
    _generate_srt_file(script.scenes, audio_clips, srt_path)

    # 生成操作说明
    readme_path = os.path.join(output_dir, "导入说明.txt")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(f"""噼哩噼哩 - {project_name} 工程文件

生成时间：{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

文件说明：
- {project_name}.edl      → 可导入 Premiere Pro / DaVinci Resolve
- {project_name}.srt      → 字幕文件，可在剪辑软件中导入
- {project_name}_project.json → 完整工程描述，包含所有分镜信息

导入剪映步骤：
1. 打开剪映专业版
2. 新建项目（1920x1080，25fps）
3. 将所有视频片段按顺序导入素材库
4. 参考 _project.json 中的顺序和时长手动排列
5. 导入 .srt 字幕文件

导入 Premiere Pro 步骤：
1. 新建序列（1920x1080，25fps）
2. 文件 → 导入 → 选择 .edl 文件
3. 将素材文件夹指定为视频片段所在目录

总时长：{sum(s.duration for s in script.scenes):.1f} 秒
分镜数：{len(script.scenes)} 个
""")

    if verbose:
        print(f"[JianyingDraft] 工程文件已生成: {output_dir}")

    return output_dir


def _frames_to_tc(frames: int, fps: int) -> str:
    """将帧数转换为时间码 HH:MM:SS:FF"""
    total_seconds = frames // fps
    ff = frames % fps
    hh = total_seconds // 3600
    mm = (total_seconds % 3600) // 60
    ss = total_seconds % 60
    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"


def _generate_srt_file(
    scenes: list[Scene],
    audio_clips: dict[int, str],
    output_path: str,
) -> None:
    """生成 SRT 字幕文件"""
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

        start = current_time
        end = current_time + duration

        def fmt(t):
            h = int(t // 3600)
            m = int((t % 3600) // 60)
            s = int(t % 60)
            ms = int((t % 1) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        srt_lines.append(str(index))
        srt_lines.append(f"{fmt(start)} --> {fmt(end)}")
        srt_lines.append(scene.voiceover.strip())
        srt_lines.append("")

        current_time += scene.duration
        index += 1

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_lines))
