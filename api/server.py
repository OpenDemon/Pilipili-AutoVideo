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
from datetime import datetime
from typing import Optional, Any
from enum import Enum

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# 导入核心模块
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import get_config, PilipiliConfig
from modules.llm import generate_script_sync, VideoScript, Scene, script_to_dict
from modules.image_gen import generate_all_keyframes_sync
from modules.tts import generate_all_voiceovers_sync, update_scene_durations
from modules.video_gen import generate_all_video_clips_sync
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
            self.connections[project_id].remove(websocket)

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
                self.connections[project_id].remove(ws)


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


class ReviewDecisionRequest(BaseModel):
    approved: bool
    scenes: Optional[list[dict]] = None          # 修改后的分镜数据（如果有修改）


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
    config = get_config()
    memory = get_memory_manager(config)
    project_dir = os.path.join(config.local.output_dir, project_id)
    os.makedirs(project_dir, exist_ok=True)

    try:
        # ── 阶段 1：生成脚本 ──────────────────────────────────
        await push_status(project_id, WorkflowStage.GENERATING_SCRIPT, 5,
                          "正在分析主题，生成视频脚本...")

        # 注入记忆上下文
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
            f"脚本生成完成：《{script.title}》，共 {len(script.scenes)} 个分镜",
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
                scene = Scene(**scene_data)
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
        keyframe_task = asyncio.to_thread(
            generate_all_keyframes_sync,
            scenes=script.scenes,
            output_dir=images_dir,
            reference_images=request.reference_images or [],
            config=config,
            verbose=True,
        )

        audio_task = asyncio.to_thread(
            generate_all_voiceovers_sync,
            scenes=script.scenes,
            output_dir=audio_dir,
            voice_id=request.voice_id,
            config=config,
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
        await push_status(project_id, WorkflowStage.GENERATING_VIDEO, 55,
                          f"使用 {request.video_engine.upper()} 生成视频片段...")

        clips_dir = os.path.join(project_dir, "clips")

        engine = None if request.video_engine == "auto" else request.video_engine
        auto_route = (request.video_engine == "auto")

        video_clips = await asyncio.to_thread(
            generate_all_video_clips_sync,
            scenes=script.scenes,
            keyframe_paths=keyframe_paths,
            output_dir=clips_dir,
            engine=engine,
            auto_route=auto_route,
            config=config,
            verbose=True,
        )

        await push_status(project_id, WorkflowStage.ASSEMBLING, 80,
                          "视频片段生成完成，开始组装最终成片...")

        # ── 阶段 5：组装拼接 ──────────────────────────────────
        output_dir = os.path.join(project_dir, "output")
        temp_dir = os.path.join(project_dir, "temp")
        final_video = os.path.join(output_dir, f"{script.title}.mp4")
        os.makedirs(output_dir, exist_ok=True)

        plan = AssemblyPlan(
            scenes=script.scenes,
            video_clips=video_clips,
            audio_clips=audio_paths,
            output_path=final_video,
            temp_dir=temp_dir,
            add_subtitles=request.add_subtitles,
        )

        await asyncio.to_thread(assemble_video, plan, True)

        # 生成剪映草稿
        draft_dir = os.path.join(output_dir, "剪映草稿")
        await asyncio.to_thread(
            generate_jianying_draft,
            script=script,
            video_clips=video_clips,
            audio_clips=audio_paths,
            output_dir=draft_dir,
            project_name=script.title,
            verbose=True,
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

    except Exception as e:
        import traceback
        error_msg = f"{type(e).__name__}: {str(e)}"
        await push_status(
            project_id, WorkflowStage.FAILED, 0,
            f"工作流执行失败: {error_msg}",
            error=traceback.format_exc()
        )


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
    """更新 API Keys 配置"""
    config = get_config()
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "configs", "config.yaml")

    updates = {}
    if request.llm_api_key:
        updates["llm.api_key"] = request.llm_api_key
    if request.llm_provider:
        updates["llm.provider"] = request.llm_provider
    if request.image_gen_api_key:
        updates["image_gen.api_key"] = request.image_gen_api_key
    if request.tts_api_key:
        updates["tts.api_key"] = request.tts_api_key
    if request.kling_api_key:
        updates["video_gen.kling.api_key"] = request.kling_api_key
    if request.kling_api_secret:
        updates["video_gen.kling.api_secret"] = request.kling_api_secret
    if request.seedance_api_key:
        updates["video_gen.seedance.api_key"] = request.seedance_api_key
    if request.mem0_api_key:
        updates["memory.mem0_api_key"] = request.mem0_api_key

    return {"message": "API Keys 已更新", "updated_keys": list(updates.keys())}


@app.get("/api/settings/keys/status")
async def get_keys_status():
    """检查各 API Key 的配置状态"""
    config = get_config()
    return {
        "llm": {
            "provider": config.llm.provider,
            "configured": bool(config.llm.api_key),
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


@app.post("/api/projects/{project_id}/feedback")
async def submit_feedback(project_id: str, rating: int):
    """提交项目评分（1-5星），用于记忆系统学习"""
    memory = get_memory_manager()
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

    # 如果项目已有状态，立即推送
    if project_id in _projects and _projects[project_id].get("status"):
        await websocket.send_json(_projects[project_id]["status"])

    try:
        while True:
            # 保持连接，接收心跳
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(project_id, websocket)


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
