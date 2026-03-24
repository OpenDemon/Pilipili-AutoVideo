"""
端对端测试：对标视频分析流程
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import load_config
from modules.llm import analyze_reference_video_sync

def main():
    # 加载配置
    config = load_config("configs/config.yaml")
    
    # 注入 API Key（使用 image_gen 的 key）
    if not config.llm.gemini.api_key or config.llm.gemini.api_key == "YOUR_GEMINI_API_KEY":
        config.llm.gemini.api_key = config.image_gen.api_key
        print(f"[TEST] 使用 image_gen API Key: {config.image_gen.api_key[:20]}...")
    
    # 确保模型是最新的
    config.llm.gemini.model = "gemini-2.5-flash"
    
    video_path = "/tmp/test_video.mp4"
    print(f"[TEST] 开始分析视频: {video_path}")
    
    result = analyze_reference_video_sync(video_path, config, verbose=True)
    
    print("\n[TEST] ✓ 分析成功！")
    print(f"  标题: {result.title}")
    print(f"  风格: {result.style}")
    print(f"  时长: {result.total_duration}s")
    print(f"  分镜数: {len(result.scenes)}")
    print(f"  人物数: {len(result.characters)}")
    if result.scenes:
        print(f"\n  第一个分镇:")
        s = result.scenes[0]
        print(f"    画面描述: {s.image_prompt[:80]}...")
        print(f"    旁白: {(s.voiceover or '(无旁白)')[:60]}...")
        print(f"    shot_mode: {s.shot_mode}")
    if result.reverse_prompts:
        print(f"\n  反推提示词示例: {result.reverse_prompts[0][:80]}...")
    if result.characters:
        c = result.characters[0]
        print(f"\n  第一个人物: {c.name} - {c.description[:60]}...")
    print("\n[TEST] 全部通过 ✓")

if __name__ == "__main__":
    main()
