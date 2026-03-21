"""
噼哩噼哩 Pilipili-AutoVideo
记忆系统 - Mem0 + 程序性记忆（借鉴 Agent-S）

职责：
- 自动从历史创作中学习用户风格偏好
- 在生成新脚本时注入个性化上下文
- 记录成功的提示词模式（程序性记忆）
- 支持本地 SQLite 存储（无需云端）
"""

import os
import json
import sqlite3
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict

from core.config import PilipiliConfig, get_config


# ============================================================
# 数据结构
# ============================================================

@dataclass
class StyleMemory:
    """用户风格偏好记忆"""
    visual_style: list[str]        # 视觉风格标签（如 "赛博朋克", "冷色调"）
    pacing: str                    # 节奏偏好（"fast" / "medium" / "slow"）
    avg_scene_duration: float      # 平均分镜时长（秒）
    preferred_transitions: list[str]  # 常用转场
    preferred_camera_motions: list[str]  # 常用镜头运动
    tone: str                      # 内容基调（"inspiring" / "educational" / "entertaining"）
    voice_id: str                  # 常用音色
    image_style_keywords: list[str]  # 常用生图关键词


@dataclass
class ProceduralMemory:
    """程序性记忆：成功的提示词模式（借鉴 Agent-S）"""
    topic_category: str            # 主题类别（如 "科技", "旅行", "美食"）
    successful_image_prompts: list[str]  # 效果好的生图提示词
    successful_video_prompts: list[str]  # 效果好的视频提示词
    successful_script_patterns: list[str]  # 效果好的脚本结构
    engine_preference: str         # 该类主题偏好的视频引擎


# ============================================================
# 本地 SQLite 记忆存储
# ============================================================

class LocalMemoryStore:
    """基于 SQLite 的本地记忆存储"""

    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS style_preferences (
                    user_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    weight REAL DEFAULT 1.0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, key)
                );

                CREATE TABLE IF NOT EXISTS procedural_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    topic_category TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    success_count INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS project_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    style TEXT,
                    script_json TEXT,
                    rating INTEGER,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS feedback_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    scene_id INTEGER,
                    event_type TEXT NOT NULL,
                    old_value TEXT,
                    new_value TEXT,
                    created_at TEXT NOT NULL
                );
            """)

    def save_style_preference(self, user_id: str, key: str, value: str, weight: float = 1.0):
        """保存或更新风格偏好"""
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO style_preferences (user_id, key, value, weight, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, key) DO UPDATE SET
                    value = excluded.value,
                    weight = excluded.weight,
                    updated_at = excluded.updated_at
            """, (user_id, key, value, weight, now))

    def get_style_preferences(self, user_id: str) -> dict:
        """获取用户所有风格偏好"""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT key, value, weight FROM style_preferences WHERE user_id = ? ORDER BY weight DESC",
                (user_id,)
            ).fetchall()
        return {row[0]: {"value": row[1], "weight": row[2]} for row in rows}

    def save_procedural_memory(
        self, user_id: str, topic_category: str, memory_type: str, content: str
    ):
        """保存程序性记忆，相同内容则增加成功计数"""
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            existing = conn.execute("""
                SELECT id, success_count FROM procedural_memories
                WHERE user_id = ? AND topic_category = ? AND memory_type = ? AND content = ?
            """, (user_id, topic_category, memory_type, content)).fetchone()

            if existing:
                conn.execute("""
                    UPDATE procedural_memories
                    SET success_count = success_count + 1, updated_at = ?
                    WHERE id = ?
                """, (now, existing[0]))
            else:
                conn.execute("""
                    INSERT INTO procedural_memories
                    (user_id, topic_category, memory_type, content, success_count, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 1, ?, ?)
                """, (user_id, topic_category, memory_type, content, now, now))

    def get_procedural_memories(
        self, user_id: str, topic_category: str, memory_type: str, limit: int = 5
    ) -> list[str]:
        """获取最成功的程序性记忆"""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT content FROM procedural_memories
                WHERE user_id = ? AND topic_category = ? AND memory_type = ?
                ORDER BY success_count DESC LIMIT ?
            """, (user_id, topic_category, memory_type, limit)).fetchall()
        return [row[0] for row in rows]

    def save_project(self, user_id: str, project_id: str, topic: str, style: str, script_json: str):
        """保存项目历史"""
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO project_history (user_id, project_id, topic, style, script_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, project_id, topic, style, script_json, now))

    def save_feedback(
        self, user_id: str, project_id: str, scene_id: Optional[int],
        event_type: str, old_value: str = "", new_value: str = ""
    ):
        """保存用户反馈事件（用于隐式学习）"""
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO feedback_events
                (user_id, project_id, scene_id, event_type, old_value, new_value, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, project_id, scene_id, event_type, old_value, new_value, now))


# ============================================================
# 记忆管理器（高层接口）
# ============================================================

class MemoryManager:
    """
    记忆管理器 - 整合 Mem0 和本地 SQLite

    核心功能：
    1. 自动从项目历史中学习风格偏好
    2. 在生成新脚本时注入个性化上下文
    3. 记录用户的手动修改（隐式学习）
    """

    def __init__(self, config: Optional[PilipiliConfig] = None):
        if config is None:
            config = get_config()
        self.config = config
        self.user_id = config.memory.user_id
        self.enabled = config.memory.enabled

        # 本地 SQLite 存储（始终可用）
        self.local_store = LocalMemoryStore(config.memory.local_db_path)

        # Mem0 客户端（可选，需要 API Key）
        self.mem0_client = None
        if config.memory.provider == "mem0" and config.memory.mem0_api_key:
            try:
                from mem0 import MemoryClient
                self.mem0_client = MemoryClient(api_key=config.memory.mem0_api_key)
            except ImportError:
                pass

    def build_context_for_generation(self, topic: str) -> str:
        """
        构建注入到 LLM 的个性化上下文

        这是"越用越聪明"的核心实现：
        在每次生成脚本前，把用户的历史偏好注入到 System Prompt 中
        """
        if not self.enabled:
            return ""

        context_parts = []

        # 1. 获取风格偏好
        prefs = self.local_store.get_style_preferences(self.user_id)
        if prefs:
            style_items = []
            for key, data in prefs.items():
                style_items.append(f"  - {key}: {data['value']}")
            if style_items:
                context_parts.append("用户历史创作风格偏好：\n" + "\n".join(style_items))

        # 2. 获取程序性记忆（成功的提示词模式）
        topic_category = self._classify_topic(topic)
        successful_prompts = self.local_store.get_procedural_memories(
            self.user_id, topic_category, "image_prompt", limit=3
        )
        if successful_prompts:
            context_parts.append(
                f"该类主题（{topic_category}）历史上效果好的生图提示词风格：\n" +
                "\n".join(f"  - {p[:80]}" for p in successful_prompts)
            )

        # 3. 从 Mem0 获取语义记忆（如果可用）
        if self.mem0_client:
            try:
                memories = self.mem0_client.search(topic, user_id=self.user_id, limit=5)
                if memories:
                    mem_items = [f"  - {m['memory']}" for m in memories]
                    context_parts.append("相关历史记忆：\n" + "\n".join(mem_items))
            except Exception:
                pass

        if not context_parts:
            return ""

        return "\n\n".join(context_parts)

    def learn_from_script(self, script_data: dict, project_id: str):
        """
        从生成的脚本中自动学习风格偏好（被动积累）
        """
        if not self.enabled:
            return

        scenes = script_data.get("scenes", [])
        if not scenes:
            return

        # 学习平均分镜时长
        avg_duration = sum(s.get("duration", 5) for s in scenes) / len(scenes)
        self.local_store.save_style_preference(
            self.user_id, "avg_scene_duration", str(round(avg_duration, 1))
        )

        # 学习风格标签
        all_tags = []
        for scene in scenes:
            all_tags.extend(scene.get("style_tags", []))

        if all_tags:
            # 统计最常用的标签
            from collections import Counter
            tag_counts = Counter(all_tags)
            top_tags = [tag for tag, _ in tag_counts.most_common(5)]
            self.local_store.save_style_preference(
                self.user_id, "top_style_tags", json.dumps(top_tags, ensure_ascii=False)
            )

        # 学习转场偏好
        transitions = [s.get("transition", "crossfade") for s in scenes]
        from collections import Counter
        top_transition = Counter(transitions).most_common(1)[0][0]
        self.local_store.save_style_preference(self.user_id, "preferred_transition", top_transition)

        # 保存项目历史
        self.local_store.save_project(
            self.user_id, project_id,
            script_data.get("topic", ""),
            script_data.get("style", ""),
            json.dumps(script_data, ensure_ascii=False)
        )

    def learn_from_user_edit(
        self,
        project_id: str,
        scene_id: int,
        field: str,
        old_value: str,
        new_value: str,
    ):
        """
        从用户的手动修改中学习（隐式学习）

        当用户在审核界面修改分镜内容时，记录修改模式
        """
        if not self.enabled:
            return

        self.local_store.save_feedback(
            self.user_id, project_id, scene_id,
            f"edit_{field}", old_value, new_value
        )

        # 如果用户修改了 image_prompt，记录为成功的提示词模式
        if field == "image_prompt" and new_value:
            topic_category = "general"
            self.local_store.save_procedural_memory(
                self.user_id, topic_category, "image_prompt", new_value
            )

    def learn_from_rating(self, project_id: str, rating: int):
        """
        从用户评分中学习（显式学习）

        rating: 1-5 星
        """
        if not self.enabled:
            return

        if rating >= 4:
            # 高评分：强化当前风格偏好
            with sqlite3.connect(self.local_store.db_path) as conn:
                conn.execute("""
                    UPDATE style_preferences
                    SET weight = MIN(weight * 1.2, 5.0)
                    WHERE user_id = ?
                """, (self.user_id,))

        elif rating <= 2:
            # 低评分：降低当前风格偏好权重
            with sqlite3.connect(self.local_store.db_path) as conn:
                conn.execute("""
                    UPDATE style_preferences
                    SET weight = MAX(weight * 0.8, 0.1)
                    WHERE user_id = ?
                """, (self.user_id,))

    def _classify_topic(self, topic: str) -> str:
        """简单的主题分类（用于程序性记忆检索）"""
        categories = {
            "科技": ["AI", "人工智能", "科技", "技术", "编程", "机器人", "太空", "火星"],
            "旅行": ["旅行", "旅游", "城市", "风景", "自然", "山", "海", "森林"],
            "美食": ["美食", "食物", "餐厅", "烹饪", "料理", "菜"],
            "人物": ["人物", "故事", "人生", "成长", "励志"],
            "商业": ["商业", "创业", "品牌", "营销", "产品"],
        }

        topic_lower = topic.lower()
        for category, keywords in categories.items():
            if any(kw in topic_lower for kw in keywords):
                return category

        return "general"


# ============================================================
# 全局单例
# ============================================================

_memory_manager: Optional[MemoryManager] = None


def get_memory_manager(config: Optional[PilipiliConfig] = None) -> MemoryManager:
    """获取全局记忆管理器单例"""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager(config)
    return _memory_manager
