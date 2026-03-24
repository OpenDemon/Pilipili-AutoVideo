"""
噼哩噼哩 AutoVideo - 全面功能测试套件
覆盖：配置加载、API路由、LLM脚本生成、TTS、图像生成、视频API连通性、剪映草稿、对标分析
"""
import sys
import os
import asyncio
import traceback
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = "✓"
FAIL = "✗"
results = []

def run_test(name, fn):
    print(f"\n{'='*60}")
    print(f"[TEST] {name}")
    print('='*60)
    try:
        fn()
        results.append((name, "PASS", None))
        print(f"{PASS} PASS")
    except Exception as e:
        tb = traceback.format_exc()
        results.append((name, "FAIL", str(e)))
        print(f"{FAIL} FAIL: {e}")
        print(f"堆栈:\n{tb}")

# ============================================================
# 1. 配置加载
# ============================================================
def test_config():
    from core.config import load_config
    config = load_config("configs/config.yaml")
    assert config.llm.default_provider, "LLM 默认提供商未配置"
    assert config.llm.deepseek.api_key and "YOUR" not in config.llm.deepseek.api_key, "DeepSeek API Key 未配置"
    assert config.video_gen.kling.api_key and "YOUR" not in config.video_gen.kling.api_key, "Kling API Key 未配置"
    assert config.tts.api_key and "YOUR" not in config.tts.api_key, "TTS API Key 未配置"
    assert config.image_gen.api_key and "YOUR" not in config.image_gen.api_key, "图像生成 API Key 未配置"
    print(f"  LLM: {config.llm.default_provider} | Video: {config.video_gen.default_provider} | TTS: {config.tts.default_provider}")
    print(f"  DeepSeek key: {config.llm.deepseek.api_key[:15]}...")
    print(f"  Kling key: {config.video_gen.kling.api_key[:10]}...")
    print(f"  TTS key: {config.tts.api_key[:20]}...")
    print(f"  Gemini key: {config.image_gen.api_key[:20]}...")

# ============================================================
# 2. API 路由注册
# ============================================================
def test_api_routes():
    from api.server import app
    routes = [r.path for r in app.routes]
    required = [
        "/health", "/api/projects", "/api/projects/{project_id}",
        "/api/projects/{project_id}/review", "/api/projects/{project_id}/script",
        "/api/settings/keys", "/api/analyze/upload",
        "/api/analyze/{analysis_id}", "/ws/{project_id}",
    ]
    missing = [r for r in required if r not in routes]
    assert not missing, f"缺少路由: {missing}"
    print(f"  已注册 {len(routes)} 条路由，必要路由全部存在 ✓")

# ============================================================
# 3. LLM 脚本生成
# ============================================================
def test_llm_script():
    from core.config import load_config
    from modules.llm import generate_script
    config = load_config("configs/config.yaml")
    script = asyncio.run(generate_script(
        topic="一只猫咪在阳光下打盹，温馨治愈，15秒",
        config=config, verbose=True
    ))
    assert script and script.title, "脚本标题为空"
    assert len(script.scenes) >= 2, f"分镜太少: {len(script.scenes)}"
    for s in script.scenes:
        assert s.scene_id, "分镜缺少 scene_id"
        assert s.duration > 0, "分镜时长为 0"
        assert s.image_prompt, "分镜缺少 image_prompt"
        assert s.voiceover, "分镜缺少 voiceover"
        assert s.shot_mode in ["i2v", "multi_ref", "first_end_frame", "t2v"], f"shot_mode 无效: {s.shot_mode}"
    print(f"  标题: {script.title}")
    print(f"  分镜数: {len(script.scenes)}, 总时长: {sum(s.duration for s in script.scenes)}s")
    print(f"  shot_mode 分布: {[s.shot_mode for s in script.scenes]}")

# ============================================================
# 4. TTS 语音合成
# ============================================================
def test_tts():
    from core.config import load_config
    from modules.tts import generate_voiceover
    from modules.llm import Scene
    config = load_config("configs/config.yaml")
    scene = Scene(
        scene_id=1, duration=5,
        image_prompt="test", video_prompt="test",
        voiceover="这是一段测试语音，验证 TTS 功能是否正常。",
        transition="crossfade", camera_motion="static",
        style_tags=[], shot_mode="i2v"
    )
    output_path = "/tmp/test_tts_scene1.mp3"
    result_path, duration = asyncio.run(generate_voiceover(
        scene=scene, output_dir="/tmp/tts_test", config=config, verbose=True
    ))
    assert result_path and os.path.exists(result_path), f"TTS 输出文件不存在: {result_path}"
    size = os.path.getsize(result_path)
    assert size > 1000, f"TTS 文件太小: {size} bytes"
    print(f"  输出: {result_path} ({size/1024:.1f} KB), 时长: {duration:.2f}s")

# ============================================================
# 5. 图像生成
# ============================================================
def test_image_gen():
    from core.config import load_config
    from modules.image_gen import generate_keyframe
    from modules.llm import Scene
    config = load_config("configs/config.yaml")
    scene = Scene(
        scene_id=1, duration=5,
        image_prompt="A cute cat sleeping in warm sunlight, photorealistic, 4K, cinematic",
        video_prompt="camera slowly zooms in",
        voiceover="猫咪在阳光下打盹",
        transition="crossfade", camera_motion="zoom_in",
        style_tags=["治愈"], shot_mode="i2v"
    )
    output_dir = "/tmp/test_image_gen"
    os.makedirs(output_dir, exist_ok=True)
    result_path = asyncio.run(generate_keyframe(
        scene=scene, output_dir=output_dir, config=config, verbose=True
    ))
    assert result_path and os.path.exists(result_path), f"图像文件不存在: {result_path}"
    size = os.path.getsize(result_path)
    assert size > 5000, f"图像文件太小: {size} bytes"
    print(f"  输出: {result_path} ({size/1024:.1f} KB)")

# ============================================================
# 6. Kling API 连通性（JWT + 接口可达）
# ============================================================
def test_kling_api():
    from core.config import load_config
    from modules.video_gen import _generate_kling_jwt
    import requests
    config = load_config("configs/config.yaml")
    
    token = _generate_kling_jwt(
        config.video_gen.kling.api_key,
        config.video_gen.kling.api_secret
    )
    assert token and len(token) > 50, "JWT token 生成失败"
    print(f"  JWT token: {token[:40]}...")
    
    # 仅验证 JWT 生成正确，不实际调用 API（避免消耗配额）
    import base64, json as _json
    parts = token.split('.')
    assert len(parts) == 3, "JWT 格式错误（应为 3 段）"
    # 解码 payload 验证内容
    padded = parts[1] + '=' * (4 - len(parts[1]) % 4)
    payload_data = _json.loads(base64.urlsafe_b64decode(padded))
    assert 'iss' in payload_data, "JWT 缺少 iss 字段"
    assert 'exp' in payload_data, "JWT 缺少 exp 字段"
    assert payload_data['exp'] > payload_data.get('iat', 0), "JWT 过期时间异常"
    print(f"  JWT 验证成功: iss={payload_data['iss'][:15]}..., exp 有效")
    print(f"  注意: Kling API 实际调用已跳过（避免消耗配额），最终交付时会单独进行一次完整连通性测试")

# ============================================================
# 7. 剪映草稿生成（EDL fallback，不依赖真实视频文件）
# ============================================================
def test_jianying_draft():
    from core.config import load_config
    from modules.llm import Scene, VideoScript
    from modules.jianying_draft import generate_jianying_draft, _generate_scene_manifest
    config = load_config("configs/config.yaml")
    
    scenes = [
        Scene(scene_id=1, duration=5, image_prompt="cat sleeping", video_prompt="zoom in",
              voiceover="猫咪打盹", transition="crossfade", camera_motion="zoom_in",
              style_tags=["治愈"], shot_mode="i2v"),
        Scene(scene_id=2, duration=5, image_prompt="cat wakes up", video_prompt="static",
              voiceover="猫咪醒来", transition="fade", camera_motion="static",
              style_tags=["治愈"], shot_mode="multi_ref"),
    ]
    script = VideoScript(
        title="测试草稿", topic="猫咪", style="治愈系", total_duration=10,
        scenes=scenes, metadata={}
    )
    
    # 测试素材清单生成（不依赖真实视频文件）
    manifest_dir = "/tmp/test_manifest"
    os.makedirs(manifest_dir, exist_ok=True)
    manifest_path = _generate_scene_manifest(
        script=script,
        video_clips={1: "/tmp/fake1.mp4", 2: "/tmp/fake2.mp4"},
        audio_clips={1: "/tmp/fake1.mp3", 2: "/tmp/fake2.mp3"},
        output_dir=manifest_dir,
        project_name="测试项目"
    )
    assert os.path.exists(manifest_path), f"素材清单文件不存在: {manifest_path}"
    import json
    with open(manifest_path) as f:
        manifest = json.load(f)
    assert "scenes" in manifest, "素材清单缺少 scenes 字段"
    assert len(manifest["scenes"]) == 2, f"素材清单分镜数错误: {len(manifest['scenes'])}"
    print(f"  素材清单: {manifest_path}")
    print(f"  分镜数: {len(manifest['scenes'])}")
    
    # 测试 EDL 生成
    from modules.jianying_draft import _generate_edl_fallback
    edl_dir = "/tmp/test_edl"
    result = _generate_edl_fallback(
        script=script,
        video_clips={1: "/tmp/fake1.mp4", 2: "/tmp/fake2.mp4"},
        audio_clips={1: "/tmp/fake1.mp3", 2: "/tmp/fake2.mp3"},
        output_dir=edl_dir,
        project_name="测试项目",
        verbose=True
    )
    assert result and os.path.isdir(result), f"EDL 输出目录不存在: {result}"
    files = os.listdir(result)
    print(f"  EDL 输出目录: {result}")
    print(f"  生成文件: {files}")

# ============================================================
# 8. 对标视频分析（完整流程）
# ============================================================
def test_reference_analysis():
    from core.config import load_config
    from modules.llm import analyze_reference_video_sync
    config = load_config("configs/config.yaml")
    
    video_path = "/tmp/test_video.mp4"
    result = analyze_reference_video_sync(video_path, config, verbose=True)
    assert result and result.title, "分析结果为空"
    assert len(result.scenes) > 0, "分析分镜为空"
    assert len(result.reverse_prompts) > 0, "反推提示词为空"
    print(f"  标题: {result.title}")
    print(f"  风格: {result.style}")
    print(f"  分镜: {len(result.scenes)}, 人物: {len(result.characters)}")
    print(f"  反推示例: {result.reverse_prompts[0][:80]}...")

# ============================================================
# 运行所有测试
# ============================================================
if __name__ == "__main__":
    print("\n" + "="*60)
    print("噼哩噼哩 AutoVideo - 全面功能测试")
    print("="*60)
    
    # 确保测试视频存在
    if not os.path.exists("/tmp/test_video.mp4"):
        print("[准备] 下载测试视频...")
        os.system("wget -q 'https://www.w3schools.com/html/mov_bbb.mp4' -O /tmp/test_video.mp4")
    
    run_test("1. 配置加载", test_config)
    run_test("2. API 路由注册", test_api_routes)
    run_test("3. LLM 脚本生成（DeepSeek）", test_llm_script)
    run_test("4. TTS 语音合成（MiniMax）", test_tts)
    run_test("5. 图像生成（Gemini）", test_image_gen)
    run_test("6. Kling API 连通性", test_kling_api)
    run_test("7. 剪映草稿生成", test_jianying_draft)
    run_test("8. 对标视频分析（Gemini）", test_reference_analysis)
    
    # 汇总
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    passed = [r for r in results if r[1] == "PASS"]
    failed = [r for r in results if r[1] == "FAIL"]
    for name, status, err in results:
        icon = PASS if status == "PASS" else FAIL
        print(f"  {icon} {name}")
        if err:
            print(f"      → {err[:120]}")
    print(f"\n总计: {len(passed)}/{len(results)} 通过")
    if failed:
        print(f"失败: {len(failed)} 个，需要修复")
        sys.exit(1)
    else:
        print("全部通过！✓")
