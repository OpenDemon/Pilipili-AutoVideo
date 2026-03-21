"""
噼哩噼哩 Pilipili-AutoVideo
集成测试套件

测试策略：
- 单元测试：不调用真实 API，使用 mock
- 集成测试：调用真实 API（需要有效的 API Keys）
- 端到端测试：完整工作流（耗时较长）

运行方式：
  pytest tests/ -v                    # 运行所有测试
  pytest tests/ -v -m "not api"       # 跳过需要 API 的测试
  pytest tests/ -v -m "api"           # 只运行 API 测试
"""

import os
import json
import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import PilipiliConfig, get_config, reset_config
from modules.llm import Scene, VideoScript, script_to_dict, dict_to_script, _parse_json_safely
from modules.tts import get_audio_duration, update_scene_durations
from modules.assembler import _format_srt_time, _split_subtitle_text, _map_transition


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def sample_scene():
    return Scene(
        scene_id=1,
        duration=5.0,
        image_prompt="A futuristic city at night, neon lights, cyberpunk style",
        video_prompt="Camera slowly pans right, revealing the cityscape",
        voiceover="在这个充满科技感的未来都市中，霓虹灯光照亮了每一个角落。",
        transition="crossfade",
        camera_motion="pan_right",
        style_tags=["cyberpunk", "neon", "futuristic"],
    )


@pytest.fixture
def sample_script(sample_scene):
    scene2 = Scene(
        scene_id=2,
        duration=6.0,
        image_prompt="Close-up of a robot hand touching a holographic screen",
        video_prompt="Fingers slowly reach out and touch the glowing interface",
        voiceover="人工智能正在以前所未有的速度改变着我们的生活方式。",
        transition="fade",
        camera_motion="zoom_in",
        style_tags=["technology", "ai", "futuristic"],
    )

    return VideoScript(
        title="AI 改变世界",
        topic="AI 改变世界",
        style="科技感，蓝紫色调",
        total_duration=11.0,
        scenes=[sample_scene, scene2],
        metadata={
            "description": "探索人工智能如何改变我们的未来",
            "tags": ["AI", "科技", "未来"],
        }
    )


@pytest.fixture
def config():
    reset_config()
    return PilipiliConfig()


# ============================================================
# 单元测试：数据结构
# ============================================================

class TestDataStructures:
    def test_scene_creation(self, sample_scene):
        assert sample_scene.scene_id == 1
        assert sample_scene.duration == 5.0
        assert sample_scene.transition == "crossfade"
        assert len(sample_scene.style_tags) == 3

    def test_script_serialization(self, sample_script):
        """测试脚本序列化/反序列化"""
        script_dict = script_to_dict(sample_script)

        assert script_dict["title"] == "AI 改变世界"
        assert len(script_dict["scenes"]) == 2
        assert script_dict["scenes"][0]["scene_id"] == 1

        # 反序列化
        restored = dict_to_script(script_dict)
        assert restored.title == sample_script.title
        assert len(restored.scenes) == len(sample_script.scenes)
        assert restored.scenes[0].image_prompt == sample_script.scenes[0].image_prompt

    def test_json_parsing_with_markdown(self):
        """测试 JSON 解析（处理 markdown 代码块）"""
        json_with_markdown = """```json
{
  "title": "测试",
  "scenes": []
}
```"""
        result = _parse_json_safely(json_with_markdown)
        assert result["title"] == "测试"

    def test_json_parsing_plain(self):
        """测试纯 JSON 解析"""
        plain_json = '{"title": "测试", "scenes": []}'
        result = _parse_json_safely(plain_json)
        assert result["title"] == "测试"


# ============================================================
# 单元测试：TTS 工具函数
# ============================================================

class TestTTSUtils:
    def test_update_scene_durations(self, sample_script):
        """测试根据 TTS 时长更新分镜时长"""
        voiceover_results = {
            1: ("audio_1.mp3", 4.2),
            2: ("audio_2.mp3", 5.8),
        }

        updated_scenes = update_scene_durations(
            sample_script.scenes,
            voiceover_results,
            padding=0.5,
        )

        # 时长 = TTS 时长 + padding，取最近的 0.5 倍数
        assert updated_scenes[0].duration == 4.5  # 4.2 + 0.5 = 4.7 → 5.0... wait
        # 4.2 + 0.5 = 4.7, round(4.7 * 2) / 2 = round(9.4) / 2 = 9 / 2 = 4.5
        assert updated_scenes[1].duration == 6.5  # 5.8 + 0.5 = 6.3, round(6.3*2)/2 = 6.5


# ============================================================
# 单元测试：字幕工具函数
# ============================================================

class TestSubtitleUtils:
    def test_format_srt_time(self):
        """测试 SRT 时间格式化"""
        assert _format_srt_time(0.0) == "00:00:00,000"
        assert _format_srt_time(1.5) == "00:00:01,500"
        assert _format_srt_time(65.123) == "00:01:05,123"
        assert _format_srt_time(3661.0) == "01:01:01,000"

    def test_split_subtitle_text_short(self):
        """短文本不分行"""
        text = "这是短文本"
        lines = _split_subtitle_text(text, max_chars=20)
        assert lines == ["这是短文本"]

    def test_split_subtitle_text_long(self):
        """长文本按标点分行"""
        text = "这是一段很长的文本，需要在标点处分行，以便显示更清晰。"
        lines = _split_subtitle_text(text, max_chars=15)
        assert len(lines) > 1
        for line in lines:
            assert len(line) <= 15

    def test_map_transition(self):
        """测试转场映射"""
        assert _map_transition("crossfade") == "fade"
        assert _map_transition("wipe") == "wipeleft"
        assert _map_transition("unknown") == "fade"  # 未知转场回退到 fade


# ============================================================
# 单元测试：配置系统
# ============================================================

class TestConfig:
    def test_default_config(self):
        """测试默认配置"""
        config = PilipiliConfig()
        assert config.llm.default_provider == "deepseek"
        assert config.video_gen.default_provider == "kling"
        assert config.tts.default_provider == "minimax"
        assert config.memory.enabled is True

    def test_config_env_override(self, monkeypatch):
        """测试环境变量覆盖配置"""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-123")
        monkeypatch.setenv("LLM_PROVIDER", "deepseek")

        reset_config()
        from core.config import load_config
        config = load_config()

        assert config.llm.deepseek.api_key == "test-key-123"
        reset_config()


# ============================================================
# 单元测试：记忆系统
# ============================================================

class TestMemorySystem:
    def test_local_memory_store(self, tmp_path):
        """测试本地 SQLite 记忆存储"""
        from modules.memory import LocalMemoryStore

        db_path = str(tmp_path / "test.db")
        store = LocalMemoryStore(db_path)

        # 保存风格偏好
        store.save_style_preference("user1", "visual_style", "cyberpunk", weight=1.5)
        prefs = store.get_style_preferences("user1")

        assert "visual_style" in prefs
        assert prefs["visual_style"]["value"] == "cyberpunk"
        assert prefs["visual_style"]["weight"] == 1.5

    def test_procedural_memory(self, tmp_path):
        """测试程序性记忆"""
        from modules.memory import LocalMemoryStore

        db_path = str(tmp_path / "test.db")
        store = LocalMemoryStore(db_path)

        # 保存程序性记忆
        store.save_procedural_memory("user1", "科技", "image_prompt", "neon city at night")
        store.save_procedural_memory("user1", "科技", "image_prompt", "neon city at night")  # 重复，计数+1

        memories = store.get_procedural_memories("user1", "科技", "image_prompt")
        assert len(memories) == 1
        assert memories[0] == "neon city at night"

    def test_memory_manager_context(self, tmp_path):
        """测试记忆管理器构建上下文"""
        from modules.memory import MemoryManager

        config = PilipiliConfig()
        config.memory.local_db_path = str(tmp_path / "mem.db")

        manager = MemoryManager(config)
        context = manager.build_context_for_generation("AI 科技")

        # 空记忆时返回空字符串
        assert context == ""

        # 添加记忆后应有内容
        manager.local_store.save_style_preference("default_user", "style", "cyberpunk")
        context = manager.build_context_for_generation("AI 科技")
        assert "cyberpunk" in context


# ============================================================
# 集成测试：LLM（需要 API Key）
# ============================================================

@pytest.mark.api
class TestLLMIntegration:
    @pytest.mark.asyncio
    async def test_generate_script_mock(self):
        """使用 Mock 测试脚本生成流程"""
        mock_response = {
            "title": "AI 改变世界",
            "style": "科技感",
            "total_duration": 30,
            "scenes": [
                {
                    "scene_id": 1,
                    "duration": 5,
                    "image_prompt": "Futuristic city with AI robots",
                    "video_prompt": "Camera slowly pans across the skyline",
                    "voiceover": "人工智能正在改变世界。",
                    "transition": "crossfade",
                    "camera_motion": "pan_right",
                    "style_tags": ["futuristic", "technology"],
                }
            ],
            "metadata": {"description": "AI 的未来", "tags": ["AI"]}
        }

        mock_completion = MagicMock()
        mock_completion.choices[0].message.content = json.dumps(mock_response)

        with patch("modules.llm.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)

            from modules.llm import generate_script
            config = PilipiliConfig()
            config.llm.deepseek.api_key = "test-key"

            script = await generate_script(
                topic="AI 改变世界",
                config=config,
            )

            assert script.title == "AI 改变世界"
            assert len(script.scenes) == 1


# ============================================================
# 集成测试：视频引擎路由
# ============================================================

class TestVideoEngineRouting:
    def test_route_to_seedance_for_dialogue(self, sample_scene):
        """对话场景应路由到 Seedance"""
        from modules.video_gen import smart_route_engine

        dialogue_scene = Scene(
            scene_id=1,
            duration=5,
            image_prompt="Person talking to camera",
            video_prompt="Person speaking, lip sync, dialogue",
            voiceover="这是一段对话。",
            style_tags=["talking"],
        )
        engine = smart_route_engine(dialogue_scene, default="kling")
        assert engine == "seedance"

    def test_route_to_kling_for_action(self):
        """动作场景应路由到 Kling"""
        from modules.video_gen import smart_route_engine

        action_scene = Scene(
            scene_id=1,
            duration=5,
            image_prompt="Athlete running fast",
            video_prompt="Fast running, dynamic action, energetic",
            voiceover="运动员全力冲刺。",
            style_tags=["action", "dynamic"],
        )
        engine = smart_route_engine(action_scene, default="seedance")
        assert engine == "kling"

    def test_route_to_default_for_neutral(self, sample_scene):
        """中性场景使用默认引擎"""
        from modules.video_gen import smart_route_engine

        engine = smart_route_engine(sample_scene, default="kling")
        assert engine == "kling"


# ============================================================
# 集成测试：剪映草稿生成
# ============================================================

class TestJianyingDraft:
    def test_edl_fallback(self, sample_script, tmp_path):
        """测试 EDL 回退方案"""
        from modules.jianying_draft import _generate_edl_fallback

        video_clips = {1: "/tmp/clip1.mp4", 2: "/tmp/clip2.mp4"}
        audio_clips = {1: "/tmp/audio1.mp3", 2: "/tmp/audio2.mp3"}

        output_dir = str(tmp_path / "draft")
        result = _generate_edl_fallback(
            sample_script, video_clips, audio_clips,
            output_dir, "测试项目", verbose=False
        )

        assert os.path.exists(output_dir)
        edl_file = os.path.join(output_dir, "测试项目.edl")
        assert os.path.exists(edl_file)

        json_file = os.path.join(output_dir, "测试项目_project.json")
        assert os.path.exists(json_file)

        with open(json_file, "r", encoding="utf-8") as f:
            project_data = json.load(f)

        assert project_data["project_name"] == "测试项目"
        assert len(project_data["scenes"]) == 2


# ============================================================
# 端到端测试（需要所有 API Keys）
# ============================================================

@pytest.mark.e2e
@pytest.mark.slow
class TestEndToEnd:
    """端到端测试，需要真实 API Keys，耗时较长"""

    def test_full_pipeline(self, tmp_path):
        """完整流水线测试"""
        config = get_config()

        # 跳过如果没有配置 API Keys
        if not config.llm.deepseek.api_key and not config.llm.gemini.api_key:
            pytest.skip("未配置 LLM API Key")

        from modules.llm import generate_script_sync

        script = generate_script_sync(
            topic="测试视频",
            duration_hint=15,
            config=config,
            verbose=True,
        )

        assert script.title
        assert len(script.scenes) > 0
        assert all(s.image_prompt for s in script.scenes)
        assert all(s.voiceover for s in script.scenes)
