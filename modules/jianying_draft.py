"""
噼哩噼哩 Pilipili-AutoVideo
剪映草稿生成模块 - pyJianYingDraft

职责：
- 将生成的视频片段、音频、字幕自动组装为剪映草稿工程文件
- v2.0：每个分镜作为独立片段导入，多轨道分离（视频/配音/字幕各独立轨）
- 用户可在剪映中直接替换单个分镜/配音/字幕，无需重跑全流程
- 支持自动设置转场、字幕样式、音频轨道
- 这是"AI 做 90%，人类做最后 10%"的关键闭环
"""

import os
import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from modules.llm import Scene, VideoScript


def _get_media_duration(filepath: str) -> Optional[float]:
    """用 ffprobe 获取媒体文件实际时长（秒），失败返回 None"""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', filepath],
            capture_output=True, text=True, timeout=10,
        )
        info = json.loads(result.stdout)
        return float(info['format']['duration'])
    except Exception:
        return None


def _clean_voiceover_for_subtitle(text: str) -> str:
    """
    清洗 voiceover 文本用于字幕显示：移除说话人前缀（如 男：、女（英语）：）。
    保留实际台词内容，去掉角色标记。
    """
    import re
    # 移除 男： / 女： / 男（xxx）： / 女（xxx）：
    cleaned = re.sub(r'男[\uff08(][^\uff09)]*[\uff09)]\uff1a|女[\uff08(][^\uff09)]*[\uff09)]\uff1a|男[\uff1a:]|女[\uff1a:]', '', text)
    return cleaned.strip()


def _get_resolution_for_aspect_ratio(aspect_ratio: str) -> tuple[int, int]:
    """根据画面比例返回 (width, height)"""
    if aspect_ratio in ("9:16", "3:4"):
        return (1080, 1920)
    return (1920, 1080)


def generate_jianying_draft(
    script: VideoScript,
    video_clips: dict[int, str],
    audio_clips: dict[int, str],
    output_dir: str,
    project_name: str = "噪哩噪哩作品",
    verbose: bool = False,
    aspect_ratio: str = "9:16",
) -> str:
    """
    生成剪映草稿工程文件（v2.0 分轨模式）

    v2.0 改动：
    - 每个分镜的视频片段作为独立素材导入，不合并
    - 视频轨、配音轨、字幕轨完全分离，可在剪映中单独编辑
    - 同时生成 SRT 字幕文件和 EDL 备用格式

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
            script, video_clips, audio_clips, output_dir, project_name, verbose, aspect_ratio
        )
    except ImportError:
        if verbose:
            print("[JianyingDraft] pyJianYingDraft 未安装，回退到 EDL 格式")
        return _generate_edl_fallback(
            script, video_clips, audio_clips, output_dir, project_name, verbose, aspect_ratio
        )
    except Exception as e:
        if verbose:
            print(f"[JianyingDraft] pyJianYingDraft 生成失败 ({e})，回退到 EDL 格式")
        return _generate_edl_fallback(
            script, video_clips, audio_clips, output_dir, project_name, verbose, aspect_ratio
        )


def _generate_with_pyjianyingdraft(
    script: VideoScript,
    video_clips: dict[int, str],
    audio_clips: dict[int, str],
    output_dir: str,
    project_name: str,
    verbose: bool,
    aspect_ratio: str = "9:16",
) -> str:
    """
    使用 pyJianYingDraft 生成标准剪映草稿（v2.0 分轨模式）

    关键改动：
    1. 每个分镜的视频/音频/字幕都作为独立片段挂在各自轨道上
    2. 视频轨：N 个独立 VideoSegment，不合并
    3. 配音轨：N 个独立 AudioSegment，与视频对齐
    4. 字幕轨：N 个独立 TextSegment，与配音对齐
    5. 用户在剪映中可单独替换任意一个分镜的视频/配音/字幕
    """
    import pyJianYingDraft as draft

    os.makedirs(output_dir, exist_ok=True)

    safe_name = "".join(c for c in project_name if c not in r'\/:*?"<>|').strip() or "pilipili"

    # 使用 DraftFolder API 创建草稿
    draft_folder = draft.DraftFolder(output_dir)
    if draft_folder.has_draft(safe_name):
        draft_folder.remove(safe_name)

    _w, _h = _get_resolution_for_aspect_ratio(aspect_ratio)
    jy_draft = draft_folder.create_draft(
        draft_name=safe_name,
        width=_w,
        height=_h,
        fps=30,
        maintrack_adsorb=True,
        allow_replace=True,
    )

    # ── 创建轨道 ──────────────────────────────────────────────
    # v2.0：每个分镜独立片段，所有片段都在同一轨道上按时间顺序排列
    # 这样在剪映中可以看到每个分镜是独立的素材，可以单独替换
    jy_draft.add_track(draft.TrackType.video)           # 主视频轨道（多片段）
    jy_draft.add_track(draft.TrackType.audio, "配音")   # 配音轨道（多片段）
    jy_draft.add_track(draft.TrackType.text, "字幕")    # 字幕轨道（多片段）

    # ── 逐分镜添加片段 ────────────────────────────────────────
    current_s = 0.0

    for scene in script.scenes:
        video_path = video_clips.get(scene.scene_id)
        audio_path = audio_clips.get(scene.scene_id)

        if not video_path or not os.path.exists(video_path):
            if verbose:
                print(f"[JianyingDraft] Scene {scene.scene_id} 视频片段不存在，跳过")
            continue

        # 获取视频实际时长（比 scene.duration 更准确）
        video_dur = _get_media_duration(video_path) or scene.duration

        # ── 视频片段（独立素材，可在剪映中单独替换）────────────
        video_material = draft.VideoMaterial(os.path.abspath(video_path))
        video_segment = draft.VideoSegment(
            material=video_material,
            target_timerange=draft.trange(f"{current_s}s", f"{video_dur}s"),
        )
        jy_draft.add_segment(video_segment)  # 自动进入主视频轨道

        # ── 配音片段（与对应视频片段对齐）──────────────────────
        if audio_path and os.path.exists(audio_path):
            audio_dur = _get_media_duration(audio_path) or video_dur
            audio_material = draft.AudioMaterial(os.path.abspath(audio_path))
            audio_segment = draft.AudioSegment(
                material=audio_material,
                target_timerange=draft.trange(f"{current_s}s", f"{audio_dur}s"),
                volume=1.0,
            )
            jy_draft.add_segment(audio_segment, "配音")

        # ── 字幕片段（与配音时长对齐，可在剪映中单独修改文字）──
        if scene.voiceover.strip():
            # 清洗说话人前缀，只保留实际台词
            subtitle_text = _clean_voiceover_for_subtitle(scene.voiceover)
            # 字幕时长与配音对齐（如果有配音），否则与视频对齐
            subtitle_dur = audio_dur if (audio_path and os.path.exists(audio_path)) else video_dur
            text_segment = draft.TextSegment(
                text=subtitle_text,
                timerange=draft.trange(f"{current_s}s", f"{subtitle_dur}s"),
                style=draft.TextStyle(
                    size=8.0,
                    bold=False,
                    italic=False,
                    color=(1.0, 1.0, 1.0),  # 白色
                ),
                border=draft.TextBorder(
                    color=(0.0, 0.0, 0.0),  # 黑色描边
                    width=40.0,
                ),
                clip_settings=draft.ClipSettings(transform_y=-0.85),  # 底部字幕
            )
            jy_draft.add_segment(text_segment, "字幕")

        current_s += video_dur

    # 保存草稿
    jy_draft.save()

    draft_path = os.path.join(output_dir, safe_name)

    if verbose:
        print(f"[JianyingDraft] v2.0 分轨草稿已生成: {draft_path}")
        print(f"[JianyingDraft] 共 {len(script.scenes)} 个分镜，每个分镜独立可编辑")

    # 同时生成 SRT 字幕文件（方便备用）
    srt_path = os.path.join(output_dir, f"{safe_name}.srt")
    _generate_srt_file(script.scenes, audio_clips, srt_path)

    # 生成分镜素材清单（方便用户了解每个片段对应的内容）
    _generate_scene_manifest(script, video_clips, audio_clips, output_dir, safe_name)

    return draft_path


def _generate_scene_manifest(
    script: VideoScript,
    video_clips: dict[int, str],
    audio_clips: dict[int, str],
    output_dir: str,
    project_name: str,
) -> str:
    """
    生成分镜素材清单 JSON
    记录每个分镜的视频/音频路径、时长、旁白、提示词等信息
    方便用户了解每个片段对应的内容，也可用于后续重新生成单个分镜
    Returns:
        manifest_path: 生成的清单 JSON 文件路径
    """
    manifest = {
        "project_name": project_name,
        "title": script.title,
        "topic": script.topic,
        "total_scenes": len(script.scenes),
        "total_duration": sum(s.duration for s in script.scenes),
        "resolution": "dynamic",
        "fps": 30,
        "note": "v2.0 分轨模式：每个分镜为独立片段，可在剪映中单独替换",
        "scenes": []
    }

    for scene in script.scenes:
        video_path = video_clips.get(scene.scene_id, "")
        audio_path = audio_clips.get(scene.scene_id, "")
        video_dur = _get_media_duration(video_path) if video_path and os.path.exists(video_path) else scene.duration
        audio_dur = _get_media_duration(audio_path) if audio_path and os.path.exists(audio_path) else None

        manifest["scenes"].append({
            "scene_id": scene.scene_id,
            "duration_planned": scene.duration,
            "duration_actual": video_dur,
            "audio_duration": audio_dur,
            "voiceover": scene.voiceover,
            "image_prompt": scene.image_prompt,
            "video_prompt": scene.video_prompt,
            "shot_mode": getattr(scene, "shot_mode", "i2v"),
            "transition": scene.transition,
            "camera_motion": scene.camera_motion,
            "style_tags": scene.style_tags,
            "video_clip": os.path.abspath(video_path) if video_path else "",
            "audio_clip": os.path.abspath(audio_path) if audio_path else "",
        })

    manifest_path = os.path.join(output_dir, f"{project_name}_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return manifest_path


def _generate_edl_fallback(
    script: VideoScript,
    video_clips: dict[int, str],
    audio_clips: dict[int, str],
    output_dir: str,
    project_name: str,
    verbose: bool,
    aspect_ratio: str = "9:16",
) -> str:
    """
    回退方案：生成 EDL（Edit Decision List）文件
    可导入 Premiere Pro、DaVinci Resolve 等专业剪辑软件
    同时生成 JSON 工程描述文件和 SRT 字幕文件
    """
    os.makedirs(output_dir, exist_ok=True)

    # 生成 EDL 文件
    edl_path = os.path.join(output_dir, f"{project_name}.edl")
    edl_lines = [
        "TITLE: " + project_name,
        "FCM: NON-DROP FRAME",
        "",
    ]

    current_tc = 0  # 帧数（30fps）
    fps = 30

    for i, scene in enumerate(script.scenes, 1):
        video_path = video_clips.get(scene.scene_id)
        if not video_path:
            continue

        # 使用实际视频时长
        actual_dur = _get_media_duration(video_path) or scene.duration
        duration_frames = int(actual_dur * fps)
        src_in = _frames_to_tc(0, fps)
        src_out = _frames_to_tc(duration_frames, fps)
        rec_in = _frames_to_tc(current_tc, fps)
        rec_out = _frames_to_tc(current_tc + duration_frames, fps)

        edl_lines.append(f"{i:03d}  AX       V     C        {src_in} {src_out} {rec_in} {rec_out}")
        edl_lines.append(f"* FROM CLIP NAME: {os.path.basename(video_path)}")
        edl_lines.append(f"* SCENE {scene.scene_id}: {scene.voiceover[:50] if scene.voiceover else ''}")
        edl_lines.append("")

        current_tc += duration_frames

    with open(edl_path, "w", encoding="utf-8") as f:
        f.write("\n".join(edl_lines))

    # 生成分镜素材清单（v2.0 新增）
    _generate_scene_manifest(script, video_clips, audio_clips, output_dir, project_name)

    # 生成 SRT 字幕文件
    srt_path = os.path.join(output_dir, f"{project_name}.srt")
    _generate_srt_file(script.scenes, audio_clips, srt_path)

    # 生成操作说明
    readme_path = os.path.join(output_dir, "导入说明.txt")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(f"""噼哩噼哩 v2.0 - {project_name} 工程文件（分轨模式）

生成时间：{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

【v2.0 重要更新】
本次导出为"分轨模式"：每个分镜作为独立片段，可在剪映中单独替换！
不再导入合并后的成片，而是导入所有原始分镜素材。

文件说明：
- {project_name}.edl              → 可导入 Premiere Pro / DaVinci Resolve
- {project_name}.srt              → 字幕文件，可在剪映中导入
- {project_name}_manifest.json    → 分镜素材清单（含每个分镜的路径、时长、提示词）

导入剪映步骤（分轨模式）：
1. 打开剪映专业版，新建项目（30fps）
2. 将所有视频片段（scene_001_clip.mp4 等）导入素材库
3. 按 manifest.json 中的顺序，将视频片段拖到主轨道
4. 将对应的配音文件拖到音频轨道（与视频对齐）
5. 导入 .srt 字幕文件到字幕轨道
6. 如需替换某个分镜：在素材库中替换对应片段即可

导入 Premiere Pro 步骤：
1. 新建序列（30fps）
2. 文件 → 导入 → 选择 .edl 文件
3. 将素材文件夹指定为视频片段所在目录

总时长：{sum(s.duration for s in script.scenes):.1f} 秒
分镜数：{len(script.scenes)} 个（每个独立可编辑）
""")

    if verbose:
        print(f"[JianyingDraft] v2.0 EDL 工程文件已生成: {output_dir}")

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
    srt_lines = []
    current_time = 0.0
    index = 1

    for scene in scenes:
        if not scene.voiceover.strip():
            # 没有旁白的分镜，时间轴仍然推进
            video_dur = scene.duration
            current_time += video_dur
            continue

        # 字幕时长优先使用音频实际时长
        audio_path = audio_clips.get(scene.scene_id, "")
        if audio_path and os.path.exists(audio_path):
            duration = _get_media_duration(audio_path) or scene.duration
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
        srt_lines.append(_clean_voiceover_for_subtitle(scene.voiceover))
        srt_lines.append("")

        current_time += scene.duration
        index += 1

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_lines))
