"""
噼哩噼哩 Pilipili-AutoVideo
FastAPI 后端服务

核心功能：
- 工作流编排（5 阶段流水线）
- WebSocket 实时状态推送（右侧 Agent Console）
- 人工审核暂停/恢复机制（脚本/分镜确认关卡）
- 项目管理（创建/查询/历史）
- API 连接器管理（配置各平台 Key）
"""

import os
import asyncio
import json
import uuid
import yaml
from datetime import datetime
from typing import Optional, Any
from enum import Enum
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import shutil
import subprocess

# 导入核心模块
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import get_config, PilipiliConfig, get_active_llm_config, reset_config, CONFIG_SEARCH_PATHS
from modules.llm import generate_script_sync, VideoScript, Scene, script_to_dict, analyze_reference_video_sync, ReferenceVideoAnalysis
from modules.image_gen import generate_all_keyframes_sync
from modules.tts import generate_all_voiceovers_sync, update_scene_durations
from modules.video_gen import generate_all_video_clips_sync, _generate_kling_jwt
from modules.assembler import assemble_video, AssemblyPlan
from modules.jianying_draft import generate_jianying_draft
from modules.memory import get_memory_manager


# ============================================================
# 应用初始化
# ============================================================

app = FastAPI(
    title="噼哩噼哩 Pilipili-AutoVideo API",
    description="全自动 AI 视频生成代理",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# 工作流状态管理
# ============================================================

class WorkflowStage(str, Enum):
    IDLE = "idle"
    GENERATING_SCRIPT = "generating_script"
    AWAITING_REVIEW = "awaiting_review"       # 人工审核关卡 ⬅️ 关键
    GENERATING_IMAGES = "generating_images"
    GENERATING_AUDIO = "generating_audio"
    GENERATING_VIDEO = "generating_video"
    ASSEMBLING = "assembling"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowStatus(BaseModel):
    project_id: str
    stage: WorkflowStage
    progress: int                              # 0-100
    message: str
    current_scene: Optional[int] = None
    total_scenes: Optional[int] = None
    error: Optional[str] = None
    result: Optional[dict] = None


# 全局项目状态存储
_projects: dict[str, dict] = {}
_review_events: dict[str, asyncio.Event] = {}  # 用于暂停/恢复
_review_decisions: dict[str, dict] = {}         # 用户审核决策

# 项目元数据持久化目录
PROJECTS_META_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "projects_meta")
os.makedirs(PROJECTS_META_DIR, exist_ok=True)


def save_project_meta(project_id: str):
    """将项目元数据（不含大字段）持久化到磁盘"""
    try:
        proj = _projects.get(project_id, {})
        meta = {
            "id": proj.get("id", project_id),
            "topic": proj.get("topic", ""),
            "created_at": proj.get("created_at", datetime.now().isoformat()),
            "status": proj.get("status", {}),
            "from_analysis": proj.get("from_analysis"),
            "result_path": proj.get("result", {}).get("final_video") if proj.get("result") else None,
        }
        path = os.path.join(PROJECTS_META_DIR, f"{project_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[持久化] 保存项目 {project_id} 元数据失败: {e}")


def load_all_project_metas():
    """启动时从磁盘恢复所有项目元数据"""
    try:
        for fname in sorted(os.listdir(PROJECTS_META_DIR)):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(PROJECTS_META_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                pid = meta.get("id", fname.replace(".json", ""))
                if pid not in _projects:
                    _projects[pid] = {
                        "id": pid,
                        "topic": meta.get("topic", ""),
                        "created_at": meta.get("created_at", ""),
                        "status": meta.get("status", {"stage": "completed", "progress": 100}),
                        "script": None,
                        "result": {"final_video": meta["result_path"]} if meta.get("result_path") else None,
                        "from_analysis": meta.get("from_analysis"),
                        "_restored": True,  # 标记为从磁盘恢复
                    }
            except Exception as e:
                print(f"[持久化] 加载 {fname} 失败: {e}")
        print(f"[持久化] 已从磁盘恢复 {len(_projects)} 个历史项目")
    except Exception as e:
        print(f"[持久化] 加载历史项目失败: {e}")


# ============================================================
# WebSocket 连接管理
# ============================================================

class ConnectionManager:
    def __init__(self):
        self.connections: dict[str, list[WebSocket]] = {}

    async def connect(self, project_id: str, websocket: WebSocket):
        await websocket.accept()
        if project_id not in self.connections:
            self.connections[project_id] = []
        self.connections[project_id].append(websocket)

    def disconnect(self, project_id: str, websocket: WebSocket):
        if project_id in self.connections:
            try:
                self.connections[project_id].remove(websocket)
            except ValueError:
                pass

    async def broadcast(self, project_id: str, message: dict):
        """向项目的所有 WebSocket 连接广播消息"""
        if project_id in self.connections:
            dead = []
            for ws in self.connections[project_id]:
                try:
                    await ws.send_json(message)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                try:
                    self.connections[project_id].remove(ws)
                except ValueError:
                    pass


manager = ConnectionManager()


async def push_status(project_id: str, stage: WorkflowStage, progress: int,
                      message: str, **kwargs):
    """推送工作流状态到前端"""
    status = {
        "type": "status",
        "project_id": project_id,
        "stage": stage.value,
        "progress": progress,
        "message": message,
        "timestamp": datetime.now().isoformat(),
        **kwargs
    }
    _projects[project_id]["status"] = status
    await manager.broadcast(project_id, status)


# ============================================================
# 请求/响应模型
# ============================================================

class CreateProjectRequest(BaseModel):
    topic: str
    style: Optional[str] = None
    target_duration: Optional[int] = 60          # 目标时长（秒）
    voice_id: Optional[str] = None
    video_engine: Optional[str] = "kling"        # "kling" / "seedance" / "auto"
    reference_images: Optional[list[str]] = []   # 角色参考图路径
    add_subtitles: bool = True
    auto_publish: bool = False
    preset_scenes: Optional[list[dict]] = None   # 对标分析分镜（有则跳过 LLM 生成）
    preset_title: Optional[str] = None           # 对标分析标题
    resolution: Optional[str] = "1080p"          # 输出分辨率："720p" / "1080p" / "4K"
    aspect_ratio: Optional[str] = "9:16"         # 画面比例："9:16" 竖屏 / "16:9" 横屏
    global_style_prompt: Optional[str] = ""      # 全局风格提示词（防止风格漂移）


class ReviewDecisionRequest(BaseModel):
    approved: bool
    scenes: Optional[list[dict]] = None          # 修改后的分镜数据（如果有修改）


# ============================================================
# 文件上传 API（角色参考图 + 对标视频）
# ============================================================

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "uploads", "references")
VIDEO_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "uploads", "reference_videos")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(VIDEO_UPLOAD_DIR, exist_ok=True)


def _extract_frame_from_video(video_path: str, output_path: str) -> str:
    """
    从视频中提取最清晰的一帧作为参考图。
    策略：取视频 1/3 处的帧（通常比第一帧更有代表性）
    """
    try:
        # 获取视频时长
        probe_cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", video_path
        ]
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
        duration = 1.0
        if probe_result.returncode == 0:
            import json as _json
            info = _json.loads(probe_result.stdout)
            duration = float(info.get("format", {}).get("duration", 3.0))

        # 取 1/3 处的帧
        seek_time = duration / 3

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(seek_time),
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "1",  # 最高质量 JPEG
            output_path
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return output_path
    except Exception as e:
        raise RuntimeError(f"视频截帧失败: {e}")


@app.post("/api/upload/reference")
async def upload_reference_image(
    file: UploadFile = File(...),
):
    """
    上传角色参考图（图片或视频）。
    - 图片：直接保存
    - 视频：自动提取最清晰的一帧
    返回保存后的文件路径，供创建项目时传入 reference_images。
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名为空")

    # 生成唯一文件名
    ext = Path(file.filename).suffix.lower()
    unique_name = f"{uuid.uuid4().hex[:12]}{ext}"
    save_path = os.path.join(UPLOAD_DIR, unique_name)

    # 保存上传文件
    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # 判断是否为视频文件
    video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv"}
    image_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

    if ext in video_exts:
        # 从视频中提取帧
        frame_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex[:12]}_frame.jpg")
        try:
            _extract_frame_from_video(save_path, frame_path)
            # 删除原视频节省空间
            os.remove(save_path)
            return {
                "path": os.path.abspath(frame_path),
                "filename": os.path.basename(frame_path),
                "type": "video_frame",
                "message": "已从视频中提取参考帧"
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"视频截帧失败: {str(e)}")
    elif ext in image_exts:
        return {
            "path": os.path.abspath(save_path),
            "filename": unique_name,
            "type": "image",
            "message": "参考图已上传"
        }
    else:
        os.remove(save_path)
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {ext}。支持的格式: {', '.join(image_exts | video_exts)}"
        )


class UpdateApiKeysRequest(BaseModel):
    llm_provider: Optional[str] = None
    llm_api_key: Optional[str] = None
    image_gen_api_key: Optional[str] = None
    tts_api_key: Optional[str] = None
    kling_api_key: Optional[str] = None
    kling_api_secret: Optional[str] = None
    seedance_api_key: Optional[str] = None
    mem0_api_key: Optional[str] = None


# ============================================================
# 配置文件写入工具
# ============================================================

def _get_config_path() -> Optional[Path]:
    """获取当前使用的配置文件路径"""
    # 优先使用环境变量指定的路径
    env_path = os.environ.get("PILIPILI_CONFIG")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    # 搜索默认路径
    for path in CONFIG_SEARCH_PATHS:
        if path.exists():
            return path

    # 如果都不存在，返回默认写入路径
    default = Path("./configs/config.yaml")
    default.parent.mkdir(parents=True, exist_ok=True)
    return default


def _write_config_updates(updates: dict) -> None:
    """
    将扁平化的 key=value 更新写入 config.yaml。
    updates 格式: {"llm.deepseek.api_key": "sk-xxx", "tts.api_key": "sk-yyy"}
    支持最多 3 层嵌套路径。
    """
    config_path = _get_config_path()

    # 读取现有内容
    if config_path and config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    else:
        raw = {}

    # 将扁平 key 写入嵌套 dict
    for dotted_key, value in updates.items():
        parts = dotted_key.split(".")
        d = raw
        for part in parts[:-1]:
            if part not in d or not isinstance(d[part], dict):
                d[part] = {}
            d = d[part]
        d[parts[-1]] = value

    # 写回文件
    if config_path:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(raw, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


# ============================================================
# 核心工作流（后台任务）
# ============================================================

async def run_workflow(project_id: str, request: CreateProjectRequest):
    """
    完整的 5 阶段视频生成工作流

    阶段 1: LLM 生成脚本
    阶段 2: 人工审核（暂停，等待用户确认）⬅️ 关键关卡
    阶段 3: 并行生成关键帧图片 + TTS 配音
    阶段 4: 图生视频
    阶段 5: 组装拼接 + 生成剪映草稿
    """
    # 每次新任务开始时重置图像模型黑名单，避免上次任务的失败影响本次
    from modules.image_gen import reset_failed_models
    reset_failed_models()

    config = get_config()
    memory = get_memory_manager(config)
    project_dir = os.path.join(config.local.output_dir, project_id)
    os.makedirs(project_dir, exist_ok=True)

    try:
        # ── 阶段 1：生成脚本（或直接使用对标分析分镜）────────────
        if request.preset_scenes:
            # 对标分析模式：直接将分析分镜转换为 VideoScript，跳过 LLM
            await push_status(project_id, WorkflowStage.GENERATING_SCRIPT, 5,
                              "使用对标视频分析分镜，跳过 LLM 生成...")
            preset_scene_objs = []
            for i, sd in enumerate(request.preset_scenes):
                # 兼容 voiceover_text 和 voiceover 两种字段名（对标分析返回 voiceover_text）
                voiceover_val = sd.get("voiceover") or sd.get("voiceover_text") or ""
                preset_scene_objs.append(Scene(
                    scene_id=sd.get("scene_id") or (i + 1),
                    duration=float(sd.get("duration") or 5),
                    image_prompt=sd.get("image_prompt") or "",
                    video_prompt=sd.get("video_prompt") or "",
                    voiceover=voiceover_val,
                    transition=sd.get("transition") or "crossfade",
                    camera_motion=sd.get("camera_motion") or "static",
                    style_tags=sd.get("style_tags") or [],
                    shot_mode=sd.get("shot_mode"),
                ))
            script = VideoScript(
                title=request.preset_title or request.topic,
                topic=request.topic,
                style=request.style or "",
                total_duration=sum(s.duration for s in preset_scene_objs),
                scenes=preset_scene_objs,
                metadata={},
            )
        else:
            # 普通模式：LLM 生成脚本
            await push_status(project_id, WorkflowStage.GENERATING_SCRIPT, 5,
                              "正在分析主题，生成视频脚本...")
            memory_context = memory.build_context_for_generation(request.topic)
            script = await asyncio.to_thread(
                generate_script_sync,
                topic=request.topic,
                style=request.style,
                duration_hint=request.target_duration or 60,
                memory_context=memory_context,
                config=config,
            )

        # 保存脚本到项目
        script_path = os.path.join(project_dir, "script.json")
        script_dict = script_to_dict(script)
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(script_dict, f, ensure_ascii=False, indent=2)

        _projects[project_id]["script"] = script_dict

        await push_status(
            project_id, WorkflowStage.GENERATING_SCRIPT, 15,
            f"脚本就绪：《{script.title}》，共 {len(script.scenes)} 个分镜",
            script=script_dict
        )

        # 从脚本中学习风格偏好
        memory.learn_from_script(script_dict, project_id)

        # ── 阶段 2：人工审核关卡 ──────────────────────────────
        await push_status(
            project_id, WorkflowStage.AWAITING_REVIEW, 20,
            "脚本已生成，请审核并确认分镜内容后继续",
            script=script_to_dict(script),
            requires_action=True,
            action_type="review_script"
        )

        # 创建等待事件，暂停工作流
        review_event = asyncio.Event()
        _review_events[project_id] = review_event

        # 等待用户审核（最长等待 30 分钟）
        try:
            await asyncio.wait_for(review_event.wait(), timeout=1800)
        except asyncio.TimeoutError:
            await push_status(project_id, WorkflowStage.FAILED, 20,
                              "审核超时（30分钟），工作流已取消")
            return

        # 获取审核决策
        decision = _review_decisions.get(project_id, {})
        if not decision.get("approved", False):
            await push_status(project_id, WorkflowStage.IDLE, 0, "用户取消了工作流")
            return

        # 如果用户修改了分镜，更新脚本
        if decision.get("scenes"):
            updated_scenes = []
            for scene_data in decision["scenes"]:
                # 防止前端传来的 null 字段导致 None.strip() 崩溃
                safe_data = dict(scene_data)
                safe_data["voiceover"] = safe_data.get("voiceover") or ""
                safe_data["image_prompt"] = safe_data.get("image_prompt") or ""
                safe_data["video_prompt"] = safe_data.get("video_prompt") or ""
                safe_data["transition"] = safe_data.get("transition") or "crossfade"
                safe_data["camera_motion"] = safe_data.get("camera_motion") or "static"
                safe_data["style_tags"] = safe_data.get("style_tags") or []
                scene = Scene(**safe_data)
                updated_scenes.append(scene)
            script.scenes = updated_scenes

            # 记录用户修改（隐式学习）
            original_scenes = {s["scene_id"]: s for s in (_projects[project_id]["script"] or {}).get("scenes", [])}
            for scene in updated_scenes:
                orig = original_scenes.get(scene.scene_id, {})
                if scene.image_prompt != orig.get("image_prompt", ""):
                    memory.learn_from_user_edit(
                        project_id, scene.scene_id, "image_prompt",
                        orig.get("image_prompt", ""), scene.image_prompt
                    )

        # ── 阶段 3：并行生成关键帧 + TTS ─────────────────────
        await push_status(project_id, WorkflowStage.GENERATING_IMAGES, 25,
                          f"开始并行生成 {len(script.scenes)} 个分镜关键帧和配音...")

        images_dir = os.path.join(project_dir, "keyframes")
        audio_dir = os.path.join(project_dir, "audio")

        # 并行执行生图和 TTS
        # 确定 aspect_ratio：优先用请求参数，其次用配置默认值
        aspect_ratio = request.aspect_ratio or getattr(config.video_gen.kling, 'default_ratio', '9:16') or "9:16"
        global_style_prompt = request.global_style_prompt or ""
        # 如果是对标分析模式，从分析结果提取风格提示词
        if not global_style_prompt and script.style:
            global_style_prompt = script.style

        keyframe_task = asyncio.to_thread(
            generate_all_keyframes_sync,
            scenes=script.scenes,
            output_dir=images_dir,
            reference_images=request.reference_images or [],
            characters=script.characters or [],
            config=config,
            verbose=True,
            aspect_ratio=aspect_ratio,
            global_style_prompt=global_style_prompt,
        )

        audio_task = asyncio.to_thread(
            generate_all_voiceovers_sync,
            scenes=script.scenes,
            output_dir=audio_dir,
            voice_id=request.voice_id,
            characters=script.characters or [],
            config=config,
            max_concurrent=2,  # 降低并发数，减少 MiniMax RPM 限速
            verbose=True,
        )

        await push_status(project_id, WorkflowStage.GENERATING_AUDIO, 30,
                          "并行生成关键帧图片和配音中...")

        keyframe_paths, voiceover_results = await asyncio.gather(keyframe_task, audio_task)

        # 根据 TTS 时长更新分镜 duration
        script.scenes = update_scene_durations(script.scenes, voiceover_results)
        audio_paths = {sid: path for sid, (path, _) in voiceover_results.items()}

        await push_status(project_id, WorkflowStage.GENERATING_IMAGES, 50,
                          "关键帧和配音生成完成，开始生成视频片段...",
                          keyframes=list(keyframe_paths.values()))

        # ── 阶段 4：图生视频 ──────────────────────────────────
        video_engine = request.video_engine or "kling"
        await push_status(project_id, WorkflowStage.GENERATING_VIDEO, 55,
                          f"使用 {video_engine.upper()} 生成视频片段...")

        clips_dir = os.path.join(project_dir, "clips")

        engine = None if video_engine == "auto" else video_engine
        auto_route = (video_engine == "auto")

        video_clips = await asyncio.to_thread(
            generate_all_video_clips_sync,
            scenes=script.scenes,
            keyframe_paths=keyframe_paths,
            output_dir=clips_dir,
            engine=engine,
            auto_route=auto_route,
            config=config,
            verbose=True,
            resolution=request.resolution or "1080p",
            aspect_ratio=aspect_ratio,
        )

        await push_status(project_id, WorkflowStage.ASSEMBLING, 80,
                          "视频片段生成完成，开始组装最终成片...")

        # ── 阶段 5：组装拼接 ──────────────────────────
        output_dir = os.path.join(project_dir, "output")
        temp_dir = os.path.join(project_dir, "temp")
        # 清理文件名中的非法字符（Windows 兼容）
        safe_title = "".join(c for c in script.title if c not in r'\/:*?"<>|').strip() or "output"
        final_video = os.path.join(output_dir, f"{safe_title}.mp4")
        os.makedirs(output_dir, exist_ok=True)

        plan = AssemblyPlan(
            scenes=script.scenes,
            video_clips=video_clips,
            audio_clips=audio_paths,
            output_path=final_video,
            temp_dir=temp_dir,
            add_subtitles=request.add_subtitles,
            aspect_ratio=aspect_ratio,
        )

        await asyncio.to_thread(assemble_video, plan, True)

        # 生成剪映草稿
        draft_dir = os.path.join(output_dir, "jianying_draft")
        await asyncio.to_thread(
            generate_jianying_draft,
            script=script,
            video_clips=video_clips,
            audio_clips=audio_paths,
            output_dir=draft_dir,
            project_name=safe_title,
            verbose=True,
            aspect_ratio=aspect_ratio,
        )

        # 完成
        result = {
            "final_video": final_video,
            "draft_dir": draft_dir,
            "script": script_to_dict(script),
            "total_duration": sum(s.duration for s in script.scenes),
        }

        _projects[project_id]["result"] = result

        await push_status(
            project_id, WorkflowStage.COMPLETED, 100,
            f"🎉 视频生成完成！《{script.title}》",
            result=result
        )
        save_project_meta(project_id)  # 完成时持久化最终状态

    except Exception as e:
        import traceback
        error_msg = f"{type(e).__name__}: {str(e)}"
        await push_status(
            project_id, WorkflowStage.FAILED, 0,
            f"工作流执行失败: {error_msg}",
            error=traceback.format_exc()
        )
        save_project_meta(project_id)  # 失败时也持久化状态


# ============================================================
# API 路由
# ============================================================

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0", "name": "噼哩噼哩 Pilipili-AutoVideo"}


@app.post("/api/projects")
async def create_project(request: CreateProjectRequest, background_tasks: BackgroundTasks):
    """创建新项目，启动视频生成工作流"""
    project_id = str(uuid.uuid4())[:8]

    _projects[project_id] = {
        "id": project_id,
        "topic": request.topic,
        "created_at": datetime.now().isoformat(),
        "status": {"stage": WorkflowStage.IDLE.value, "progress": 0},
        "script": None,
        "result": None,
    }

    save_project_meta(project_id)
    background_tasks.add_task(run_workflow, project_id, request)

    return {"project_id": project_id, "message": "工作流已启动"}


@app.get("/api/projects/{project_id}")
async def get_project(project_id: str):
    """获取项目状态"""
    if project_id not in _projects:
        raise HTTPException(status_code=404, detail="项目不存在")
    return _projects[project_id]


@app.get("/api/projects")
async def list_projects():
    """获取所有项目列表"""
    return list(_projects.values())


@app.post("/api/projects/{project_id}/review")
async def submit_review(project_id: str, decision: ReviewDecisionRequest):
    """
    提交脚本/分镜审核决策

    这是人工审核关卡的核心接口：
    - approved=true + scenes=修改后的数据 → 继续工作流
    - approved=false → 取消工作流
    """
    if project_id not in _review_events:
        raise HTTPException(status_code=400, detail="该项目当前不在审核状态")

    _review_decisions[project_id] = {
        "approved": decision.approved,
        "scenes": [s for s in decision.scenes] if decision.scenes else None,
    }

    # 触发工作流继续
    _review_events[project_id].set()

    return {"message": "审核决策已提交", "approved": decision.approved}


@app.put("/api/projects/{project_id}/script")
async def update_script(project_id: str, scenes: list[dict]):
    """实时更新分镜内容（在审核界面编辑时调用）"""
    if project_id not in _projects:
        raise HTTPException(status_code=404, detail="项目不存在")

    if _projects[project_id]["script"]:
        _projects[project_id]["script"]["scenes"] = scenes

    return {"message": "分镜已更新"}


@app.get("/api/projects/{project_id}/download")
async def get_download_links(project_id: str):
    """获取成品视频和剪映草稿的下载链接"""
    if project_id not in _projects:
        raise HTTPException(status_code=404, detail="项目不存在")

    result = _projects[project_id].get("result")
    if not result:
        raise HTTPException(status_code=400, detail="项目尚未完成")

    return {
        "final_video": result.get("final_video"),
        "draft_dir": result.get("draft_dir"),
        "total_duration": result.get("total_duration"),
    }


@app.post("/api/settings/keys")
async def update_api_keys(request: UpdateApiKeysRequest):
    """
    更新 API Keys 配置
    将 Keys 写入 config.yaml 并重置内存配置单例，立即生效
    """
    # 构建需要写入的更新
    updates = {}

    if request.llm_provider:
        updates["llm.default_provider"] = request.llm_provider

    # LLM api_key 写入当前激活的 provider 下
    if request.llm_api_key:
        config = get_config()
        provider = config.llm.default_provider
        updates[f"llm.{provider}.api_key"] = request.llm_api_key

    if request.image_gen_api_key:
        updates["image_gen.api_key"] = request.image_gen_api_key

    if request.tts_api_key:
        updates["tts.minimax.api_key"] = request.tts_api_key

    if request.kling_api_key:
        updates["video_gen.kling.api_key"] = request.kling_api_key

    if request.kling_api_secret:
        updates["video_gen.kling.api_secret"] = request.kling_api_secret

    if request.seedance_api_key:
        updates["video_gen.seedance.api_key"] = request.seedance_api_key

    if request.mem0_api_key:
        updates["memory.mem0_api_key"] = request.mem0_api_key

    if updates:
        try:
            _write_config_updates(updates)
            # 重置配置单例，让下次请求重新加载
            reset_config()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"配置写入失败: {str(e)}")

    return {"message": "API Keys 已更新并写入配置文件", "updated_keys": list(updates.keys())}


@app.post("/api/projects/{project_id}/resume")
async def resume_project(project_id: str, background_tasks: BackgroundTasks,
                         video_engine: str = "kling", add_subtitles: bool = True):
    """
    断点续传：从已有的 keyframes + audio 文件直接跳到视频生成阶段。
    适用于图片/TTS 已生成但视频生成失败的项目。
    """
    config = get_config()
    project_dir = os.path.join(config.local.output_dir, project_id)
    script_path = os.path.join(project_dir, "script.json")

    if not os.path.exists(script_path):
        raise HTTPException(status_code=404, detail=f"项目 {project_id} 不存在或 script.json 缺失")

    # 注册到 _projects
    with open(script_path, "r", encoding="utf-8") as f:
        script_dict = json.load(f)

    _projects[project_id] = {
        "id": project_id,
        "topic": script_dict.get("topic", script_dict.get("title", "")),
        "created_at": datetime.now().isoformat(),
        "status": {"stage": WorkflowStage.GENERATING_VIDEO.value, "progress": 50},
        "script": script_dict,
        "result": None,
    }
    save_project_meta(project_id)

    background_tasks.add_task(run_resume_workflow, project_id, video_engine, add_subtitles)
    return {"project_id": project_id, "message": "断点续传已启动，从视频生成阶段继续"}


async def run_resume_workflow(project_id: str, video_engine: str = "kling", add_subtitles: bool = True):
    """从已有 keyframes + audio 文件断点续传，直接跳到视频生成阶段"""
    from modules.image_gen import reset_failed_models
    reset_failed_models()

    config = get_config()
    project_dir = os.path.join(config.local.output_dir, project_id)

    try:
        # 读取脚本
        script_path = os.path.join(project_dir, "script.json")
        with open(script_path, "r", encoding="utf-8") as f:
            script_dict = json.load(f)

        from modules.llm import VideoScript, Scene
        scenes = [Scene(**s) for s in script_dict["scenes"]]
        script = VideoScript(
            title=script_dict["title"],
            topic=script_dict.get("topic", script_dict["title"]),
            style=script_dict.get("style", ""),
            total_duration=script_dict.get("total_duration", 0),
            scenes=scenes,
            characters=script_dict.get("characters", []),
            metadata=script_dict.get("metadata", {}),
        )

        await push_status(project_id, WorkflowStage.GENERATING_VIDEO, 50,
                          f"断点续传：读取已有关键帧和配音，共 {len(scenes)} 个分镜...")

        # 扫描已有 keyframes
        keyframes_dir = os.path.join(project_dir, "keyframes")
        keyframe_paths: dict[int, str] = {}
        if os.path.exists(keyframes_dir):
            for fname in os.listdir(keyframes_dir):
                if fname.startswith("scene_") and fname.endswith(("_keyframe.png", "_keyframe.jpg")):
                    try:
                        scene_id = int(fname.split("_")[1])
                        keyframe_paths[scene_id] = os.path.join(keyframes_dir, fname)
                    except (ValueError, IndexError):
                        pass

        # 扫描已有 audio，同时更新 scene duration
        audio_dir = os.path.join(project_dir, "audio")
        audio_paths: dict[int, str] = {}
        from modules.tts import get_audio_duration, update_scene_durations
        voiceover_results: dict[int, tuple[str, float]] = {}
        if os.path.exists(audio_dir):
            for fname in os.listdir(audio_dir):
                if fname.startswith("scene_") and fname.endswith("_voiceover.mp3"):
                    try:
                        scene_id = int(fname.split("_")[1])
                        fpath = os.path.join(audio_dir, fname)
                        dur = get_audio_duration(fpath)
                        audio_paths[scene_id] = fpath
                        voiceover_results[scene_id] = (fpath, dur)
                    except (ValueError, IndexError):
                        pass

        # 用 TTS 时长更新分镜 duration
        if voiceover_results:
            script.scenes = update_scene_durations(script.scenes, voiceover_results)

        missing_kf = [s.scene_id for s in script.scenes if s.scene_id not in keyframe_paths]
        if missing_kf:
            await push_status(project_id, WorkflowStage.FAILED, 0,
                              f"缺少分镜 {missing_kf} 的关键帧图片，无法续传",
                              error=f"keyframes missing: {missing_kf}")
            return

        await push_status(project_id, WorkflowStage.GENERATING_VIDEO, 55,
                          f"已加载 {len(keyframe_paths)} 张关键帧、{len(audio_paths)} 段配音，开始生成视频片段...",
                          keyframes=list(keyframe_paths.values()))

        # ── 视频生成 ──────────────────────────────────────────
        clips_dir = os.path.join(project_dir, "clips")
        engine = None if video_engine == "auto" else video_engine
        auto_route = (video_engine == "auto")

        # 从脚本中提取 aspect_ratio（对标分析会写入），默认竖屏
        aspect_ratio = script_dict.get("aspect_ratio", "9:16")

        video_clips = await asyncio.to_thread(
            generate_all_video_clips_sync,
            scenes=script.scenes,
            keyframe_paths=keyframe_paths,
            output_dir=clips_dir,
            engine=engine,
            auto_route=auto_route,
            config=config,
            verbose=True,
            resolution="1080p",
            aspect_ratio=aspect_ratio,
        )

        await push_status(project_id, WorkflowStage.ASSEMBLING, 80,
                          "视频片段生成完成，开始组装最终成片...")

        # ── 组装拼接 ──────────────────────────────────────
        output_dir = os.path.join(project_dir, "output")
        temp_dir = os.path.join(project_dir, "temp")
        safe_title = "".join(c for c in script.title if c not in r'\/:*?"<>|').strip() or "output"
        final_video = os.path.join(output_dir, f"{safe_title}.mp4")
        os.makedirs(output_dir, exist_ok=True)

        plan = AssemblyPlan(
            scenes=script.scenes,
            video_clips=video_clips,
            audio_clips=audio_paths,
            output_path=final_video,
            temp_dir=temp_dir,
            add_subtitles=add_subtitles,
            aspect_ratio=aspect_ratio,
        )
        await asyncio.to_thread(assemble_video, plan, True)

        # 剪映草稿
        draft_dir = os.path.join(output_dir, "jianying_draft")
        await asyncio.to_thread(
            generate_jianying_draft,
            script=script,
            video_clips=video_clips,
            audio_clips=audio_paths,
            output_dir=draft_dir,
            project_name=safe_title,
            verbose=True,
            aspect_ratio=aspect_ratio,
        )

        result = {
            "final_video": final_video,
            "draft_dir": draft_dir,
            "script": script_dict,
            "total_duration": sum(s.duration for s in script.scenes),
        }
        _projects[project_id]["result"] = result

        await push_status(
            project_id, WorkflowStage.COMPLETED, 100,
            f"🎉 视频生成完成！《{script.title}》",
            result=result
        )
        save_project_meta(project_id)

    except Exception as e:
        import traceback
        error_msg = f"{type(e).__name__}: {str(e)}"
        await push_status(
            project_id, WorkflowStage.FAILED, 0,
            f"续传工作流执行失败: {error_msg}",
            error=traceback.format_exc()
        )
        save_project_meta(project_id)


@app.get("/api/settings/keys/status")
async def get_keys_status():
    """检查各 API Key 的配置状态"""
    config = get_config()
    active_llm = get_active_llm_config(config)
    return {
        "llm": {
            "provider": config.llm.default_provider,
            "configured": bool(active_llm.api_key),
        },
        "image_gen": {
            "provider": "nano_banana",
            "configured": bool(config.image_gen.api_key),
        },
        "tts": {
            "provider": "minimax",
            "configured": bool(config.tts.api_key),
        },
        "kling": {
            "configured": bool(config.video_gen.kling.api_key and config.video_gen.kling.api_secret),
        },
        "seedance": {
            "configured": bool(config.video_gen.seedance.api_key),
        },
    }


class TestKeyRequest(BaseModel):
    service: str  # llm / image_gen / tts / kling / seedance


@app.post("/api/settings/keys/test")
async def test_api_key(request: TestKeyRequest):
    """
    测试指定服务的 API Key 是否有效。
    对每个服务发送一个最小化请求来验证 Key 的有效性。
    """
    config = get_config()
    service = request.service

    try:
        if service == "llm":
            active_llm = get_active_llm_config(config)
            if not active_llm.api_key:
                return {"success": False, "message": "API Key 未配置"}
            provider = config.llm.default_provider
            if provider == "gemini":
                from openai import AsyncOpenAI
                client = AsyncOpenAI(
                    api_key=active_llm.api_key,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
                )
            else:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(
                    api_key=active_llm.api_key,
                    base_url=active_llm.base_url or "https://api.openai.com/v1"
                )
            resp = await client.chat.completions.create(
                model=active_llm.model,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
            )
            return {"success": True, "message": f"{provider} 连接成功，模型: {active_llm.model}"}

        elif service == "image_gen":
            if not config.image_gen.api_key:
                return {"success": False, "message": "API Key 未配置"}
            from google import genai
            client = genai.Client(api_key=config.image_gen.api_key)
            models = list(client.models.list())
            return {"success": True, "message": f"Gemini API 连接成功，可用模型 {len(models)} 个"}

        elif service == "tts":
            if not config.tts.api_key:
                return {"success": False, "message": "API Key 未配置"}
            import aiohttp
            url = "https://api.minimax.chat/v1/t2a_v2"
            headers = {
                "Authorization": f"Bearer {config.tts.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": config.tts.model or "speech-02-hd",
                "text": "测试",
                "stream": False,
                "voice_setting": {
                    "voice_id": config.tts.default_voice or "female-shaonv",
                    "speed": 1.0,
                    "vol": 1.0,
                    "pitch": 0,
                },
                "audio_setting": {
                    "sample_rate": 32000,
                    "format": "mp3",
                },
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    result = await resp.json()
            if "base_resp" in result:
                code = result["base_resp"].get("status_code", -1)
                msg = result["base_resp"].get("status_msg", "未知错误")
                if code == 0:
                    return {"success": True, "message": "MiniMax TTS 连接成功"}
                return {"success": False, "message": f"MiniMax 返回错误: {msg} (code={code})"}
            return {"success": False, "message": f"MiniMax 返回异常: {json.dumps(result, ensure_ascii=False)[:200]}"}

        elif service == "kling":
            if not config.video_gen.kling.api_key or not config.video_gen.kling.api_secret:
                return {"success": False, "message": "API Key 或 API Secret 未配置"}
            import aiohttp
            token = _generate_kling_jwt(config.video_gen.kling.api_key, config.video_gen.kling.api_secret)
            url = f"{config.video_gen.kling.base_url}/v1/videos/image2video"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json={}, headers=headers) as resp:
                    status = resp.status
            if status == 401 or status == 403:
                return {"success": False, "message": f"Kling 认证失败 (HTTP {status})，请检查 API Key 和 Secret"}
            return {"success": True, "message": "Kling API 认证成功"}

        elif service == "seedance":
            if not config.video_gen.seedance.api_key:
                return {"success": False, "message": "API Key 未配置"}
            import aiohttp
            url = f"{config.video_gen.seedance.base_url}/contents/generations/tasks"
            headers = {
                "Authorization": f"Bearer {config.video_gen.seedance.api_key}",
                "Content-Type": "application/json",
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json={}, headers=headers) as resp:
                    status = resp.status
            if status == 401 or status == 403:
                return {"success": False, "message": f"Seedance 认证失败 (HTTP {status})，请检查 API Key"}
            return {"success": True, "message": "Seedance API 认证成功"}

        else:
            return {"success": False, "message": f"未知服务: {service}"}

    except Exception as e:
        return {"success": False, "message": f"连接失败: {type(e).__name__}: {str(e)}"}


# ============================================================
# 对标视频分析 API（P1 新增）
# ============================================================

# 内存缓存：对标视频分析结果（project_id → analysis）
_reference_analyses: dict[str, dict] = {}


def _analysis_to_dict(analysis: ReferenceVideoAnalysis) -> dict:
    """将 ReferenceVideoAnalysis 转为可序列化字典"""
    return {
        "title": analysis.title,
        "style": analysis.style,
        "aspect_ratio": analysis.aspect_ratio,
        "total_duration": analysis.total_duration,
        "bgm_style": analysis.bgm_style,
        "color_grade": analysis.color_grade,
        "overall_prompt": analysis.overall_prompt,
        "characters": [
            {
                "character_id": c.character_id,
                "name": c.name,
                "description": c.description,
                "appearance_prompt": c.appearance_prompt,
                "replacement_image": c.replacement_image,
            }
            for c in analysis.characters
        ],
        "scenes": [
            {
                "scene_id": s.scene_id,
                "duration": s.duration,
                "image_prompt": s.image_prompt,
                "video_prompt": s.video_prompt,
                "voiceover": s.voiceover,
                "shot_mode": s.shot_mode,
                "transition": s.transition,
                "camera_motion": s.camera_motion,
                "style_tags": s.style_tags,
            }
            for s in analysis.scenes
        ],
        "reverse_prompts": analysis.reverse_prompts,
        "raw_analysis": analysis.raw_analysis,
    }


@app.post("/api/analyze/upload")
async def analyze_reference_video_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    """
    上传对标视频文件，触发 Gemini 分析

    分析结果包含：
    - 人物列表（外貌描述 + 英文提示词）
    - 分镜结构（含 shot_mode 标注）
    - 每个分镜的反推提示词（reverse_prompt）
    - 整体风格提示词

    返回 analysis_id，前端通过 GET /api/analyze/{analysis_id} 轮询结果
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名为空")

    ext = Path(file.filename).suffix.lower()
    video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv"}
    if ext not in video_exts:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {ext}。支持的视频格式: {', '.join(video_exts)}"
        )

    # 保存上传文件
    analysis_id = uuid.uuid4().hex[:12]
    save_path = os.path.join(VIDEO_UPLOAD_DIR, f"{analysis_id}{ext}")

    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # 初始化分析状态
    _reference_analyses[analysis_id] = {
        "analysis_id": analysis_id,
        "status": "processing",
        "filename": file.filename,
        "file_path": save_path,
        "created_at": datetime.now().isoformat(),
        "result": None,
        "error": None,
    }

    # 后台异步执行分析
    background_tasks.add_task(_run_reference_analysis, analysis_id, save_path)

    return {
        "analysis_id": analysis_id,
        "status": "processing",
        "message": "视频已上传，正在分析中..."
    }


async def _run_reference_analysis(analysis_id: str, video_path: str):
    """后台任务：执行对标视频分析"""
    try:
        config = get_config()
        analysis = await __import__('asyncio').get_event_loop().run_in_executor(
            None,
            lambda: analyze_reference_video_sync(video_path, config, verbose=True)
        )
        _reference_analyses[analysis_id]["status"] = "completed"
        _reference_analyses[analysis_id]["result"] = _analysis_to_dict(analysis)
    except Exception as e:
        import traceback
        _reference_analyses[analysis_id]["status"] = "failed"
        _reference_analyses[analysis_id]["error"] = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"


@app.get("/api/analyze/{analysis_id}")
async def get_reference_analysis(analysis_id: str):
    """
    获取对标视频分析结果

    status 字段：
    - processing：分析中
    - completed：分析完成，result 字段包含完整结果
    - failed：分析失败，error 字段包含错误信息
    """
    if analysis_id not in _reference_analyses:
        raise HTTPException(status_code=404, detail="分析任务不存在")
    return _reference_analyses[analysis_id]


@app.post("/api/analyze/{analysis_id}/replace-character")
async def replace_character(
    analysis_id: str,
    character_id: int = Form(...),
    file: UploadFile = File(...),
):
    """
    为对标视频中的某个人物上传替换参考图

    上传后，该人物的 replacement_image 字段将被更新。
    创建新项目时可以将此路径传入 reference_images，
    实现人物替换（用用户上传的人物替换对标视频中的原始人物）。
    """
    if analysis_id not in _reference_analyses:
        raise HTTPException(status_code=404, detail="分析任务不存在")

    analysis_data = _reference_analyses[analysis_id]
    if analysis_data["status"] != "completed" or not analysis_data.get("result"):
        raise HTTPException(status_code=400, detail="分析尚未完成")

    ext = Path(file.filename).suffix.lower()
    image_exts = {".jpg", ".jpeg", ".png", ".webp"}
    video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

    unique_name = f"{uuid.uuid4().hex[:12]}{ext}"
    save_path = os.path.join(UPLOAD_DIR, unique_name)

    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # 如果是视频，提取帧
    if ext in video_exts:
        frame_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex[:12]}_frame.jpg")
        try:
            _extract_frame_from_video(save_path, frame_path)
            os.remove(save_path)
            save_path = frame_path
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"视频截帧失败: {str(e)}")

    # 更新人物的 replacement_image
    characters = analysis_data["result"]["characters"]
    for char in characters:
        if char["character_id"] == character_id:
            char["replacement_image"] = os.path.abspath(save_path)
            return {
                "message": f"人物 {char['name']} 的替换参考图已更新",
                "character_id": character_id,
                "replacement_image": os.path.abspath(save_path),
                "path": os.path.abspath(save_path),
            }

    raise HTTPException(status_code=404, detail=f"人物 ID {character_id} 不存在")


@app.delete("/api/analyze/{analysis_id}/remove-character-image")
async def remove_character_image(
    analysis_id: str,
    character_id: int,
):
    """
    删除某个人物的替换参考图（允许用户重新选择或不替换）
    """
    if analysis_id not in _reference_analyses:
        raise HTTPException(status_code=404, detail="分析任务不存在")
    analysis_data = _reference_analyses[analysis_id]
    if analysis_data["status"] != "completed" or not analysis_data.get("result"):
        raise HTTPException(status_code=400, detail="分析尚未完成")
    characters = analysis_data["result"]["characters"]
    for char in characters:
        if char["character_id"] == character_id:
            old_path = char.get("replacement_image")
            char["replacement_image"] = None
            # 尝试删除本地文件
            if old_path and os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except Exception:
                    pass
            return {
                "message": f"人物 {char['name']} 的替换参考图已删除",
                "character_id": character_id,
            }
    raise HTTPException(status_code=404, detail=f"人物 ID {character_id} 不存在")


@app.post("/api/analyze/{analysis_id}/create-project")
async def create_project_from_analysis(
    analysis_id: str,
    background_tasks: BackgroundTasks,
    topic: Optional[str] = Form(None),
    video_engine: Optional[str] = Form("kling"),
    add_subtitles: bool = Form(True),
):
    """
    基于对标视频分析结果直接创建新项目

    自动将分析出的：
    - 整体风格提示词作为 style
    - 人物替换参考图作为 reference_images
    - 分镜结构作为脚本初稿（跳过 LLM 生成，直接进入审核关卡）
    """
    if analysis_id not in _reference_analyses:
        raise HTTPException(status_code=404, detail="分析任务不存在")

    analysis_data = _reference_analyses[analysis_id]
    if analysis_data["status"] != "completed" or not analysis_data.get("result"):
        raise HTTPException(status_code=400, detail="分析尚未完成")

    result = analysis_data["result"]

    # 收集替换参考图
    reference_images = []
    for char in result["characters"]:
        if char.get("replacement_image") and os.path.exists(char["replacement_image"]):
            reference_images.append(char["replacement_image"])

    # 构建创建请求（将分析分镜直接作为 preset_scenes，跳过 LLM 生成）
    req = CreateProjectRequest(
        topic=topic or result["title"],
        style=result.get("overall_prompt", result.get("style", "")),
        video_engine=video_engine or "kling",
        reference_images=reference_images,
        add_subtitles=add_subtitles,
        preset_scenes=result.get("scenes", []),
        preset_title=result.get("title"),
    )

    project_id = str(uuid.uuid4())[:8]
    _projects[project_id] = {
        "id": project_id,
        "topic": req.topic,
        "created_at": datetime.now().isoformat(),
        "status": {"stage": WorkflowStage.IDLE.value, "progress": 0},
        "script": None,
        "result": None,
        "from_analysis": analysis_id,
    }

    save_project_meta(project_id)
    background_tasks.add_task(run_workflow, project_id, req)

    return {
        "project_id": project_id,
        "message": "已基于对标视频分析创建新项目，工作流已启动",
        "reference_images_count": len(reference_images),
    }


@app.post("/api/projects/{project_id}/feedback")
async def submit_feedback(project_id: str, rating: int):
    """提交项目评分（1-5星），用于记忆系统学习"""
    config = get_config()
    memory = get_memory_manager(config)
    memory.learn_from_rating(project_id, rating)
    return {"message": f"评分 {rating} 星已记录，记忆系统已更新"}


# ============================================================
# WebSocket 端点
# ============================================================

@app.websocket("/ws/{project_id}")
async def websocket_endpoint(websocket: WebSocket, project_id: str):
    """
    WebSocket 连接 - 实时推送工作流状态到前端 Agent Console
    """
    await manager.connect(project_id, websocket)

    # 如果项目已有状态，立即推送（恢复场景）
    if project_id in _projects and _projects[project_id].get("status"):
        try:
            await websocket.send_json(_projects[project_id]["status"])
        except Exception:
            pass

    try:
        while True:
            # 保持连接，接收心跳
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(project_id, websocket)
    except Exception:
        manager.disconnect(project_id, websocket)


# ============================================================
# 文件下载端点
# ============================================================

from fastapi.responses import FileResponse
import zipfile
import tempfile


@app.get("/api/projects/{project_id}/download/video")
async def download_video(project_id: str):
    """直接下载成品视频文件"""
    if project_id not in _projects:
        raise HTTPException(status_code=404, detail="项目不存在")

    result = _projects[project_id].get("result")
    if not result:
        raise HTTPException(status_code=400, detail="项目尚未完成")

    video_path = result.get("final_video", "")
    if not video_path or not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail=f"视频文件不存在: {video_path}")

    filename = os.path.basename(video_path)
    return FileResponse(
        path=video_path,
        media_type="video/mp4",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/api/projects/{project_id}/download/draft")
async def download_draft(project_id: str):
    """下载剪映草稿文件夹（打包为 zip）"""
    if project_id not in _projects:
        raise HTTPException(status_code=404, detail="项目不存在")

    result = _projects[project_id].get("result")
    if not result:
        raise HTTPException(status_code=400, detail="项目尚未完成")

    draft_dir = result.get("draft_dir", "")
    if not draft_dir or not os.path.exists(draft_dir):
        raise HTTPException(status_code=404, detail=f"草稿目录不存在: {draft_dir}")

    # 打包为 zip
    zip_path = os.path.join(os.path.dirname(draft_dir), "jianying_draft.zip")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(draft_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, os.path.dirname(draft_dir))
                zf.write(file_path, arcname)

    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename="jianying_draft.zip",
        headers={"Content-Disposition": 'attachment; filename="jianying_draft.zip"'}
    )


# ============================================================
# 应用生命周期事件
# ============================================================

@app.on_event("startup")
async def startup_event():
    """FastAPI 启动时自动恢复历史项目"""
    load_all_project_metas()


# ============================================================
# 启动入口
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
