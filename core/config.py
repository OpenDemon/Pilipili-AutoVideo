"""
噼哩噼哩 Pilipili-AutoVideo
核心配置加载器 - 支持 YAML 配置文件与环境变量双轨制
"""

import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


# 配置文件搜索路径（按优先级排序）
CONFIG_SEARCH_PATHS = [
    Path("./configs/config.yaml"),
    Path("./config.yaml"),
    Path(os.path.expanduser("~/.pilipili/config.yaml")),
]


@dataclass
class LLMProviderConfig:
    api_key: str = ""
    model: str = ""
    base_url: str = ""


@dataclass
class LLMConfig:
    default_provider: str = "deepseek"
    deepseek: LLMProviderConfig = field(default_factory=lambda: LLMProviderConfig(
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1"
    ))
    kimi: LLMProviderConfig = field(default_factory=lambda: LLMProviderConfig(
        model="moonshot-v1-32k",
        base_url="https://api.moonshot.cn/v1"
    ))
    minimax: LLMProviderConfig = field(default_factory=lambda: LLMProviderConfig(
        model="MiniMax-Text-01",
        base_url="https://api.minimax.chat/v1"
    ))
    zhipu: LLMProviderConfig = field(default_factory=lambda: LLMProviderConfig(
        model="glm-4",
        base_url="https://open.bigmodel.cn/api/paas/v4"
    ))
    gemini: LLMProviderConfig = field(default_factory=lambda: LLMProviderConfig(
        model="gemini-2.5-flash"
    ))
    openai: LLMProviderConfig = field(default_factory=lambda: LLMProviderConfig(
        model="gpt-4o",
        base_url="https://api.openai.com/v1"
    ))
    ollama: LLMProviderConfig = field(default_factory=lambda: LLMProviderConfig(
        model="qwen2.5:latest",
        base_url="http://localhost:11434/v1",
        api_key="ollama"
    ))


@dataclass
class ImageGenConfig:
    provider: str = "nano_banana"
    api_key: str = ""
    model: str = "gemini-2.0-flash-preview-image-generation"


@dataclass
class VideoGenProviderConfig:
    api_key: str = ""
    api_secret: str = ""
    model: str = ""
    base_url: str = ""
    default_duration: int = 5
    default_ratio: str = "9:16"
    default_quality: str = "high"


@dataclass
class VideoGenConfig:
    default_provider: str = "kling"
    kling: VideoGenProviderConfig = field(default_factory=lambda: VideoGenProviderConfig(
        model="kling-v3",
        base_url="https://api.klingai.com",
    ))
    seedance: VideoGenProviderConfig = field(default_factory=lambda: VideoGenProviderConfig(
        model="doubao-seedance-1-5-pro-250528",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
    ))


@dataclass
class TTSConfig:
    default_provider: str = "minimax"
    api_key: str = ""
    model: str = "speech-02-hd"
    default_voice: str = "female-shaonv"
    speed: float = 1.0
    emotion: str = "neutral"


@dataclass
class LocalConfig:
    ffmpeg_path: str = "ffmpeg"
    whisperx_model: str = "base"
    output_dir: str = "./data/outputs"
    assets_dir: str = "./data/assets"
    temp_dir: str = "./data/temp"


@dataclass
class JianYingConfig:
    enabled: bool = True
    draft_dir: str = "./data/outputs/jianying_drafts"
    capcut_draft_dir: str = ""


@dataclass
class MemoryConfig:
    enabled: bool = True
    provider: str = "local"
    mem0_api_key: str = ""
    local_db_path: str = "./data/memory/mem0.db"
    user_id: str = "default_user"


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    frontend_port: int = 3000


@dataclass
class PilipiliConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    image_gen: ImageGenConfig = field(default_factory=ImageGenConfig)
    video_gen: VideoGenConfig = field(default_factory=VideoGenConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    local: LocalConfig = field(default_factory=LocalConfig)
    jianying: JianYingConfig = field(default_factory=JianYingConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    server: ServerConfig = field(default_factory=ServerConfig)


def _deep_merge(base: dict, override: dict) -> dict:
    """深度合并两个字典，override 优先级更高"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(config_path: Optional[str] = None) -> PilipiliConfig:
    """
    加载配置文件，支持：
    1. 指定路径的 YAML 文件
    2. 默认搜索路径
    3. 环境变量覆盖（优先级最高）
    """
    raw = {}

    # 1. 从 YAML 文件加载
    if config_path:
        search_paths = [Path(config_path)]
    else:
        search_paths = CONFIG_SEARCH_PATHS

    for path in search_paths:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                file_config = yaml.safe_load(f) or {}
                raw = _deep_merge(raw, file_config)
            break

    # 2. 环境变量覆盖（优先级最高，方便 Docker 部署）
    env_overrides = {
        "DEEPSEEK_API_KEY": ("llm", "deepseek", "api_key"),
        "KIMI_API_KEY": ("llm", "kimi", "api_key"),
        "MINIMAX_API_KEY": ("llm", "minimax", "api_key"),
        "ZHIPU_API_KEY": ("llm", "zhipu", "api_key"),
        "GEMINI_API_KEY": ("llm", "gemini", "api_key"),
        "OPENAI_API_KEY": ("llm", "openai", "api_key"),
        "KLING_API_KEY": ("video_gen", "kling", "api_key"),
        "KLING_API_SECRET": ("video_gen", "kling", "api_secret"),
        "VOLCENGINE_API_KEY": ("video_gen", "seedance", "api_key"),
        "MEM0_API_KEY": ("memory", "mem0_api_key"),
        "LLM_PROVIDER": ("llm", "default_provider"),
        "VIDEO_PROVIDER": ("video_gen", "default_provider"),
    }

    for env_var, path_tuple in env_overrides.items():
        value = os.environ.get(env_var)
        if value:
            # 动态设置嵌套字典路径
            d = raw
            for key in path_tuple[:-1]:
                d = d.setdefault(key, {})
            d[path_tuple[-1]] = value

    # 3. 构建配置对象
    config = PilipiliConfig()

    # LLM 配置
    if "llm" in raw:
        llm_raw = raw["llm"]
        config.llm.default_provider = llm_raw.get("default_provider", config.llm.default_provider)
        for provider in ["deepseek", "kimi", "minimax", "zhipu", "gemini", "openai", "ollama"]:
            if provider in llm_raw:
                p = llm_raw[provider]
                provider_cfg = getattr(config.llm, provider)
                provider_cfg.api_key = p.get("api_key", provider_cfg.api_key)
                provider_cfg.model = p.get("model", provider_cfg.model)
                provider_cfg.base_url = p.get("base_url", provider_cfg.base_url)

    # 图像生成配置
    if "image_gen" in raw:
        ig = raw["image_gen"]
        config.image_gen.api_key = ig.get("api_key", config.image_gen.api_key)
        config.image_gen.model = ig.get("model", config.image_gen.model)

    # 视频生成配置
    if "video_gen" in raw:
        vg = raw["video_gen"]
        config.video_gen.default_provider = vg.get("default_provider", config.video_gen.default_provider)
        for provider in ["kling", "seedance"]:
            if provider in vg:
                p = vg[provider]
                provider_cfg = getattr(config.video_gen, provider)
                for attr in ["api_key", "api_secret", "model", "base_url", "default_duration", "default_ratio", "default_quality"]:
                    if attr in p:
                        setattr(provider_cfg, attr, p[attr])

    # TTS 配置
    if "tts" in raw:
        tts = raw["tts"]
        if "minimax" in tts:
            m = tts["minimax"]
            config.tts.api_key = m.get("api_key", config.tts.api_key)
            config.tts.model = m.get("model", config.tts.model)
            config.tts.default_voice = m.get("default_voice", config.tts.default_voice)
            config.tts.speed = m.get("speed", config.tts.speed)
            config.tts.emotion = m.get("emotion", config.tts.emotion)

    # 本地引擎配置
    if "local" in raw:
        lc = raw["local"]
        for attr in ["ffmpeg_path", "whisperx_model", "output_dir", "assets_dir", "temp_dir"]:
            if attr in lc:
                setattr(config.local, attr, lc[attr])

    # 剪映配置
    if "jianying" in raw:
        jy = raw["jianying"]
        config.jianying.enabled = jy.get("enabled", config.jianying.enabled)
        config.jianying.draft_dir = jy.get("draft_dir", config.jianying.draft_dir)
        config.jianying.capcut_draft_dir = jy.get("capcut_draft_dir", config.jianying.capcut_draft_dir)

    # 记忆系统配置
    if "memory" in raw:
        mem = raw["memory"]
        for attr in ["enabled", "provider", "mem0_api_key", "local_db_path", "user_id"]:
            if attr in mem:
                setattr(config.memory, attr, mem[attr])

    # 服务器配置
    if "server" in raw:
        srv = raw["server"]
        for attr in ["host", "port", "frontend_port"]:
            if attr in srv:
                setattr(config.server, attr, srv[attr])

    return config


def get_active_llm_config(config: PilipiliConfig) -> LLMProviderConfig:
    """获取当前激活的 LLM 配置"""
    provider = config.llm.default_provider
    return getattr(config.llm, provider, config.llm.deepseek)


# 全局单例
_config: Optional[PilipiliConfig] = None


def get_config(config_path: Optional[str] = None) -> PilipiliConfig:
    """获取全局配置单例"""
    global _config
    if _config is None:
        _config = load_config(config_path)
    return _config


def reset_config():
    """重置配置单例（用于测试）"""
    global _config
    _config = None
