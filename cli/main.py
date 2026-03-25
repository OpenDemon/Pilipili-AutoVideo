#!/usr/bin/env python3
"""
噼哩噼哩 Pilipili-AutoVideo
CLI 命令行入口

用法示例：
  python cli/main.py run --topic "AI 改变世界" --style "科技感，蓝紫色调"
  python cli/main.py run --topic "西藏旅行" --duration 60 --engine kling
  python cli/main.py config --show
  python cli/main.py server --port 8000
"""

import os
import sys
import json
import asyncio
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text
from rich import print as rprint

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import get_config, load_config, reset_config, PilipiliConfig
from modules.llm import generate_script_sync, script_to_dict, save_script
from modules.image_gen import generate_all_keyframes_sync
from modules.tts import generate_all_voiceovers_sync, update_scene_durations
from modules.video_gen import generate_all_video_clips_sync
from modules.assembler import assemble_video, AssemblyPlan
from modules.jianying_draft import generate_jianying_draft
from modules.memory import get_memory_manager


console = Console()

LOGO = """
[bold cyan]
  ██████╗ ██╗██╗     ██╗██████╗ ██╗██╗     ██╗
  ██╔══██╗██║██║     ██║██╔══██╗██║██║     ██║
  ██████╔╝██║██║     ██║██████╔╝██║██║     ██║
  ██╔═══╝ ██║██║     ██║██╔═══╝ ██║██║     ██║
  ██║     ██║███████╗██║██║     ██║███████╗██║
  ╚═╝     ╚═╝╚══════╝╚═╝╚═╝     ╚═╝╚══════╝╚═╝
[/bold cyan]
[dim]噼哩噼哩 AutoVideo - 全自动 AI 视频生成代理 v1.0.0[/dim]
"""


@click.group()
@click.version_option(version="1.0.0", prog_name="pilipili")
def cli():
    """噼哩噼哩 Pilipili-AutoVideo - 全自动 AI 视频生成代理"""
    pass


# ============================================================
# run 命令：完整工作流
# ============================================================

@cli.command()
@click.option("--topic", "-t", required=True, help="视频主题（自然语言描述）")
@click.option("--style", "-s", default=None, help="风格描述，如 '科技感，蓝紫色调'")
@click.option("--duration", "-d", default=60, type=int, help="目标时长（秒），默认 60")
@click.option("--engine", "-e", default="kling",
              type=click.Choice(["kling", "seedance", "auto"]),
              help="视频生成引擎，默认 kling")
@click.option("--voice", "-v", default=None, help="TTS 音色 ID")
@click.option("--no-subtitles", is_flag=True, default=False, help="不添加字幕")
@click.option("--no-review", is_flag=True, default=False, help="跳过人工审核直接生成")
@click.option("--output", "-o", default=None, help="输出目录（默认使用配置文件中的路径）")
@click.option("--config-file", default=None, help="配置文件路径")
@click.option("--verbose", is_flag=True, default=False, help="显示详细日志")
@click.option("--reference-image", "-r", multiple=True,
              help="角色参考图路径（可多次指定）")
def run(topic, style, duration, engine, voice, no_subtitles, no_review,
        output, config_file, verbose, reference_image):
    """
    完整视频生成工作流

    从自然语言主题到最终成片，全程自动化。

    示例：
      pilipili run --topic "AI 改变世界" --style "科技感"
      pilipili run --topic "西藏旅行" --duration 90 --engine seedance
    """
    console.print(LOGO)

    # 加载配置
    if config_file:
        reset_config()
        config = load_config(config_file)
    else:
        config = get_config()

    # 覆盖输出目录
    if output:
        config.local.output_dir = output

    console.print(Panel(
        f"[bold]主题：[/bold]{topic}\n"
        f"[bold]风格：[/bold]{style or '自动'}\n"
        f"[bold]时长：[/bold]{duration}s\n"
        f"[bold]引擎：[/bold]{engine.upper()}\n"
        f"[bold]字幕：[/bold]{'否' if no_subtitles else '是'}\n"
        f"[bold]人工审核：[/bold]{'跳过' if no_review else '开启'}",
        title="[bold cyan]任务配置[/bold cyan]",
        border_style="cyan"
    ))

    # 检查 API Keys
    _check_api_keys(config)

    # 创建项目目录
    import uuid
    project_id = str(uuid.uuid4())[:8]
    project_dir = os.path.join(config.local.output_dir, project_id)
    os.makedirs(project_dir, exist_ok=True)

    console.print(f"\n[dim]项目 ID: {project_id}[/dim]")
    console.print(f"[dim]输出目录: {project_dir}[/dim]\n")

    try:
        # ── 阶段 1：生成脚本 ──────────────────────────────────
        with console.status("[bold cyan]正在生成视频脚本...[/bold cyan]"):
            memory = get_memory_manager(config)
            memory_context = memory.build_context_for_generation(topic)

            script = generate_script_sync(
                topic=topic,
                style=style,
                duration_hint=duration,
                memory_context=memory_context,
                config=config,
                verbose=verbose,
            )

        console.print(f"[green]✓[/green] 脚本生成完成：《{script.title}》，共 {len(script.scenes)} 个分镜")

        # 保存脚本
        script_path = os.path.join(project_dir, "script.json")
        save_script(script, script_path)
        console.print(f"[dim]  脚本已保存: {script_path}[/dim]")

        # 显示分镜预览
        _print_script_preview(script)

        # ── 阶段 2：人工审核关卡 ──────────────────────────────
        if not no_review:
            approved = _interactive_review(script)
            if not approved:
                console.print("[yellow]用户取消，工作流已停止[/yellow]")
                return

        # 从脚本学习
        memory.learn_from_script(script_to_dict(script), project_id)

        # ── 阶段 3：并行生成关键帧 + TTS ─────────────────────
        images_dir = os.path.join(project_dir, "keyframes")
        audio_dir = os.path.join(project_dir, "audio")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task_img = progress.add_task("[cyan]生成关键帧图片...", total=len(script.scenes))
            task_tts = progress.add_task("[magenta]生成 TTS 配音...", total=len(script.scenes))

            # 并行执行
            import threading

            keyframe_result = {}
            audio_result = {}
            errors = []

            # 从配置获取默认 aspect_ratio（在线程外定义，保证后续步骤可用）
            _aspect_ratio = getattr(config.video_gen.kling, 'default_ratio', '9:16') or '9:16'

            def gen_images():
                try:
                    result = generate_all_keyframes_sync(
                        scenes=script.scenes,
                        output_dir=images_dir,
                        reference_images=list(reference_image) if reference_image else [],
                        config=config,
                        verbose=verbose,
                        aspect_ratio=_aspect_ratio,
                    )
                    keyframe_result.update(result)
                    for _ in result:
                        progress.advance(task_img)
                except Exception as e:
                    errors.append(f"图片生成失败: {e}")

            def gen_audio():
                try:
                    result = generate_all_voiceovers_sync(
                        scenes=script.scenes,
                        output_dir=audio_dir,
                        voice_id=voice,
                        config=config,
                        verbose=verbose,
                    )
                    audio_result.update(result)
                    for _ in result:
                        progress.advance(task_tts)
                except Exception as e:
                    errors.append(f"TTS 生成失败: {e}")

            t1 = threading.Thread(target=gen_images)
            t2 = threading.Thread(target=gen_audio)
            t1.start()
            t2.start()
            t1.join()
            t2.join()

        if errors:
            for err in errors:
                console.print(f"[red]✗ {err}[/red]")
            raise RuntimeError("关键帧/TTS 生成失败")

        console.print(f"[green]✓[/green] 关键帧生成完成: {len(keyframe_result)} 张")
        console.print(f"[green]✓[/green] 配音生成完成: {len(audio_result)} 段")

        # 根据 TTS 时长更新分镜 duration
        script.scenes = update_scene_durations(script.scenes, audio_result)
        audio_paths = {sid: path for sid, (path, _) in audio_result.items()}

        # ── 阶段 4：图生视频 ──────────────────────────────────
        clips_dir = os.path.join(project_dir, "clips")

        selected_engine = None if engine == "auto" else engine
        auto_route = (engine == "auto")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task_vid = progress.add_task(
                f"[yellow]使用 {engine.upper()} 生成视频片段...",
                total=len(script.scenes)
            )

            video_clips = generate_all_video_clips_sync(
                scenes=script.scenes,
                keyframe_paths=keyframe_result,
                output_dir=clips_dir,
                engine=selected_engine,
                auto_route=auto_route,
                config=config,
                verbose=verbose,
                aspect_ratio=_aspect_ratio,
            )
            for _ in video_clips:
                progress.advance(task_vid)

        console.print(f"[green]✓[/green] 视频片段生成完成: {len(video_clips)} 段")

        # ── 阶段 5：组装拼接 ──────────────────────────────────
        output_dir_final = os.path.join(project_dir, "output")
        temp_dir = os.path.join(project_dir, "temp")
        final_video = os.path.join(output_dir_final, f"{script.title}.mp4")
        os.makedirs(output_dir_final, exist_ok=True)

        with console.status("[bold green]正在组装最终成片...[/bold green]"):
            plan = AssemblyPlan(
                scenes=script.scenes,
                video_clips=video_clips,
                audio_clips=audio_paths,
                output_path=final_video,
                temp_dir=temp_dir,
                add_subtitles=not no_subtitles,
                aspect_ratio=_aspect_ratio,
            )
            assemble_video(plan, verbose=verbose)

        console.print(f"[green]✓[/green] 视频组装完成")

        # 生成剪映草稿
        draft_dir = os.path.join(output_dir_final, "剪映草稿")
        with console.status("[bold blue]正在生成剪映草稿...[/bold blue]"):
            generate_jianying_draft(
                script=script,
                video_clips=video_clips,
                audio_clips=audio_paths,
                output_dir=draft_dir,
                project_name=script.title,
                verbose=verbose,
                aspect_ratio=_aspect_ratio,
            )

        console.print(f"[green]✓[/green] 剪映草稿已生成")

        # ── 完成 ──────────────────────────────────────────────
        total_duration = sum(s.duration for s in script.scenes)

        console.print(Panel(
            f"[bold green]🎉 视频生成完成！[/bold green]\n\n"
            f"[bold]标题：[/bold]{script.title}\n"
            f"[bold]总时长：[/bold]{total_duration:.1f} 秒\n"
            f"[bold]分镜数：[/bold]{len(script.scenes)} 个\n\n"
            f"[bold]成品视频：[/bold]\n  {final_video}\n\n"
            f"[bold]剪映草稿：[/bold]\n  {draft_dir}",
            title="[bold green]生成完成[/bold green]",
            border_style="green"
        ))

        # 询问评分（用于记忆学习）
        _ask_rating(memory, project_id)

    except KeyboardInterrupt:
        console.print("\n[yellow]用户中断[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]✗ 工作流失败: {e}[/bold red]")
        if verbose:
            import traceback
            console.print_exception()
        sys.exit(1)


# ============================================================
# server 命令：启动 Web UI 后端
# ============================================================

@cli.command()
@click.option("--host", default="0.0.0.0", help="监听地址")
@click.option("--port", "-p", default=8000, type=int, help="监听端口")
@click.option("--reload", is_flag=True, default=False, help="开启热重载（开发模式）")
@click.option("--config-file", default=None, help="配置文件路径")
def server(host, port, reload, config_file):
    """启动 Web UI 后端服务"""
    console.print(LOGO)
    console.print(f"[bold cyan]启动后端服务...[/bold cyan]")
    console.print(f"[dim]地址: http://{host}:{port}[/dim]")

    if config_file:
        os.environ["PILIPILI_CONFIG"] = config_file

    import uvicorn
    uvicorn.run(
        "api.server:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


# ============================================================
# config 命令：配置管理
# ============================================================

@cli.command()
@click.option("--show", is_flag=True, help="显示当前配置（隐藏敏感信息）")
@click.option("--init", is_flag=True, help="初始化配置文件")
@click.option("--set", "set_value", nargs=2, metavar="KEY VALUE",
              help="设置配置项，如 --set llm.default_provider deepseek")
def config(show, init, set_value):
    """配置管理"""
    if init:
        _init_config()
    elif show:
        _show_config()
    elif set_value:
        _set_config(set_value[0], set_value[1])
    else:
        click.echo(click.get_current_context().get_help())


# ============================================================
# script 命令：仅生成脚本（不生成视频）
# ============================================================

@cli.command()
@click.option("--topic", "-t", required=True, help="视频主题")
@click.option("--style", "-s", default=None, help="风格描述")
@click.option("--duration", "-d", default=60, type=int, help="目标时长（秒）")
@click.option("--output", "-o", default="script.json", help="输出 JSON 文件路径")
@click.option("--verbose", is_flag=True, default=False)
def script(topic, style, duration, output, verbose):
    """仅生成脚本（不调用视频/图片 API，快速预览）"""
    console.print(LOGO)

    config = get_config()
    memory = get_memory_manager(config)
    memory_context = memory.build_context_for_generation(topic)

    with console.status("[bold cyan]正在生成脚本...[/bold cyan]"):
        script_obj = generate_script_sync(
            topic=topic,
            style=style,
            duration_hint=duration,
            memory_context=memory_context,
            config=config,
            verbose=verbose,
        )

    save_script(script_obj, output)
    console.print(f"[green]✓[/green] 脚本已保存: {output}")
    _print_script_preview(script_obj)


# ============================================================
# test 命令：逐模块 API 连接测试
# ============================================================

ALL_MODULES = ["llm", "image", "tts", "video", "ffmpeg"]


@cli.command()
@click.option("--module", "-m", default="all",
              type=click.Choice(["all"] + ALL_MODULES),
              help="要测试的模块（默认 all 全部）")
@click.option("--verbose", is_flag=True, default=False, help="显示详细日志")
def test(module, verbose):
    """
    逐模块 API 连接测试

    快速验证各 API Key 是否可用，无需走完整工作流。

    示例：
      pilipili test                    # 测试全部模块
      pilipili test --module llm       # 只测试 LLM
      pilipili test --module video     # 只测试 Kling/Seedance
    """
    console.print(LOGO)
    config = get_config()

    modules_to_test = ALL_MODULES if module == "all" else [module]

    results = []
    for mod in modules_to_test:
        console.print(f"\n[bold cyan]── 测试模块: {mod.upper()} ──[/bold cyan]")
        ok, msg = _test_module(mod, config, verbose)
        status = "[green]✓ 通过[/green]" if ok else "[red]✗ 失败[/red]"
        console.print(f"  {status}  {msg}")
        results.append((mod, ok, msg))

    # 汇总
    console.print("\n")
    table = Table(title="测试结果汇总", show_lines=True)
    table.add_column("模块", style="bold", width=10)
    table.add_column("状态", width=8)
    table.add_column("详情", width=50)
    for mod, ok, msg in results:
        table.add_row(
            mod.upper(),
            "✓ 通过" if ok else "✗ 失败",
            msg,
        )
    console.print(table)

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    if passed == total:
        console.print(f"\n[bold green]全部 {total} 个模块测试通过！[/bold green]")
    else:
        console.print(f"\n[bold yellow]{passed}/{total} 个模块通过，{total - passed} 个失败[/bold yellow]")
        sys.exit(1)


def _test_module(module: str, config: PilipiliConfig, verbose: bool) -> tuple[bool, str]:
    """测试单个模块，返回 (是否通过, 描述信息)"""
    try:
        if module == "llm":
            return _test_llm(config, verbose)
        elif module == "image":
            return _test_image(config, verbose)
        elif module == "tts":
            return _test_tts(config, verbose)
        elif module == "video":
            return _test_video(config, verbose)
        elif module == "ffmpeg":
            return _test_ffmpeg(config, verbose)
        else:
            return False, f"未知模块: {module}"
    except Exception as e:
        return False, f"异常: {e}"


def _test_llm(config: PilipiliConfig, verbose: bool) -> tuple[bool, str]:
    """测试 LLM API 连接"""
    from core.config import get_active_llm_config
    provider = config.llm.default_provider
    provider_cfg = get_active_llm_config(config)

    if not provider_cfg.api_key and provider != "ollama":
        return False, f"{provider} API Key 未配置"

    from openai import OpenAI
    if provider == "gemini":
        client = OpenAI(
            api_key=provider_cfg.api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )
    else:
        client = OpenAI(
            api_key=provider_cfg.api_key,
            base_url=provider_cfg.base_url or "https://api.openai.com/v1"
        )

    resp = client.chat.completions.create(
        model=provider_cfg.model,
        messages=[{"role": "user", "content": "请回复'连接成功'四个字"}],
        max_tokens=20,
    )
    reply = resp.choices[0].message.content.strip()
    return True, f"{provider}/{provider_cfg.model} → {reply}"


def _test_image(config: PilipiliConfig, verbose: bool) -> tuple[bool, str]:
    """测试 Gemini 图像生成 API 连接"""
    if not config.image_gen.api_key:
        return False, "Gemini (image_gen) API Key 未配置"

    from google import genai
    from google.genai import types
    client = genai.Client(api_key=config.image_gen.api_key)

    # 用一个极简提示词测试连接（只生成一张小图）
    response = client.models.generate_content(
        model=config.image_gen.model,
        contents="Generate a tiny 64x64 red square image",
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
        )
    )

    has_image = False
    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            has_image = True
            break

    if has_image:
        return True, f"{config.image_gen.model} 图像生成正常"
    else:
        return False, "API 响应中无图片数据"


def _test_tts(config: PilipiliConfig, verbose: bool) -> tuple[bool, str]:
    """测试 MiniMax TTS API 连接"""
    if not config.tts.api_key:
        return False, "MiniMax TTS API Key 未配置"

    import requests
    payload = {
        "model": config.tts.model,
        "text": "测试",
        "stream": False,
        "voice_setting": {
            "voice_id": config.tts.default_voice,
            "speed": 1.0,
            "vol": 1.0,
            "pitch": 0,
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1,
        }
    }
    headers = {
        "Authorization": f"Bearer {config.tts.api_key}",
        "Content-Type": "application/json",
    }
    resp = requests.post(
        "https://api.minimax.chat/v1/t2a_v2",
        json=payload,
        headers=headers,
        timeout=30,
    )
    result = resp.json()
    if "data" in result and "audio" in result["data"]:
        audio_len = len(result["data"]["audio"]) // 2  # hex → bytes
        return True, f"speech-02-hd 正常，测试音频 {audio_len} bytes"
    else:
        return False, f"API 响应异常: {str(result)[:120]}"


def _test_video(config: PilipiliConfig, verbose: bool) -> tuple[bool, str]:
    """测试 Kling/Seedance 视频生成 API 连接（仅验证认证，不提交生成任务）"""
    provider = config.video_gen.default_provider

    if provider == "kling":
        kling_cfg = config.video_gen.kling
        if not kling_cfg.api_key or not kling_cfg.api_secret:
            return False, "Kling API Key 或 Secret 未配置"

        from modules.video_gen import _generate_kling_jwt
        token = _generate_kling_jwt(kling_cfg.api_key, kling_cfg.api_secret)

        # 调用 Kling 查询接口验证 Token 有效性
        import requests
        url = f"{kling_cfg.base_url}/v1/videos/image2video/nonexistent_task_id"
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(url, headers=headers, timeout=15)

        try:
            result = resp.json()
        except Exception:
            return False, f"Kling API 返回非 JSON (HTTP {resp.status_code}): {resp.text[:100]}"

        # code=0 表示认证通过（即使 task 不存在）
        # code 不为 0 但不是认证错误也算通过
        code = result.get("code", -1)
        msg = result.get("message", "")

        # 认证失败通常返回 401 或特定 code
        if resp.status_code == 401:
            return False, f"Kling 认证失败: {msg}"
        if code in [-1000, -1001, -1002]:  # 常见认证错误码
            return False, f"Kling 认证失败 (code={code}): {msg}"

        return True, f"Kling JWT 认证通过 (base_url={kling_cfg.base_url}, code={code}, msg={msg})"

    elif provider == "seedance":
        seedance_cfg = config.video_gen.seedance
        if not seedance_cfg.api_key:
            return False, "Seedance (Volcengine) API Key 未配置"
        return True, f"Seedance API Key 已配置 (base_url={seedance_cfg.base_url})"

    else:
        return False, f"未知视频引擎: {provider}"


def _test_ffmpeg(config: PilipiliConfig, verbose: bool) -> tuple[bool, str]:
    """测试 FFmpeg 是否可用"""
    import subprocess
    ffmpeg_path = config.local.ffmpeg_path or "ffmpeg"
    try:
        result = subprocess.run(
            [ffmpeg_path, "-version"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            # 提取版本号
            first_line = result.stdout.split("\n")[0]
            return True, first_line
        else:
            return False, f"FFmpeg 返回错误码 {result.returncode}"
    except FileNotFoundError:
        return False, f"FFmpeg 未找到 (路径: {ffmpeg_path})，请安装 FFmpeg"
    except Exception as e:
        return False, f"FFmpeg 测试异常: {e}"


# ============================================================
# 辅助函数
# ============================================================

def _check_api_keys(config: PilipiliConfig):
    """检查必要的 API Keys 是否已配置"""
    missing = []

    provider = config.llm.default_provider
    provider_cfg = getattr(config.llm, provider, None)
    if not provider_cfg or (not provider_cfg.api_key and provider != "ollama"):
        missing.append(f"LLM ({provider}) API Key")

    if not config.image_gen.api_key:
        missing.append("Nano Banana (Gemini) API Key")

    if not config.tts.api_key:
        missing.append("MiniMax TTS API Key")

    if config.video_gen.default_provider == "kling":
        if not config.video_gen.kling.api_key:
            missing.append("Kling API Key")
    elif config.video_gen.default_provider == "seedance":
        if not config.video_gen.seedance.api_key:
            missing.append("Seedance (Volcengine) API Key")

    if missing:
        console.print(Panel(
            "[bold red]以下 API Keys 未配置：[/bold red]\n" +
            "\n".join(f"  • {k}" for k in missing) +
            "\n\n[dim]请编辑 configs/config.yaml 或设置对应环境变量[/dim]",
            title="[bold red]配置缺失[/bold red]",
            border_style="red"
        ))
        sys.exit(1)


def _print_script_preview(script):
    """打印分镜脚本预览表格"""
    table = Table(title=f"《{script.title}》分镜预览", show_lines=True)
    table.add_column("ID", style="dim", width=4)
    table.add_column("时长", width=6)
    table.add_column("旁白", width=30)
    table.add_column("画面提示词", width=40)
    table.add_column("转场", width=10)

    for scene in script.scenes:
        table.add_row(
            str(scene.scene_id),
            f"{scene.duration}s",
            scene.voiceover[:28] + "..." if len(scene.voiceover) > 28 else scene.voiceover,
            scene.image_prompt[:38] + "..." if len(scene.image_prompt) > 38 else scene.image_prompt,
            scene.transition,
        )

    console.print(table)
    console.print(f"[dim]总时长预估: {sum(s.duration for s in script.scenes):.0f}s，{len(script.scenes)} 个分镜[/dim]\n")


def _interactive_review(script) -> bool:
    """交互式审核分镜脚本"""
    console.print(Panel(
        "[bold yellow]⚠️  人工审核关卡[/bold yellow]\n\n"
        "请检查以上分镜内容。\n"
        "确认后将开始调用付费 API 生成图片、配音和视频。\n\n"
        "[dim]提示：如需修改分镜，请直接编辑 script.json 后重新运行[/dim]",
        border_style="yellow"
    ))

    choice = click.prompt(
        "是否继续生成？",
        type=click.Choice(["y", "n", "edit"]),
        default="y",
        show_choices=True,
    )

    if choice == "n":
        return False
    elif choice == "edit":
        console.print("[dim]请编辑 script.json 后重新运行，使用 --no-review 跳过审核[/dim]")
        return False

    return True


def _ask_rating(memory, project_id: str):
    """询问用户评分（用于记忆学习）"""
    try:
        rating_str = click.prompt(
            "\n请对本次生成结果评分（1-5星，回车跳过）",
            default="",
            show_default=False,
        )
        if rating_str.strip():
            rating = int(rating_str.strip())
            if 1 <= rating <= 5:
                memory.learn_from_rating(project_id, rating)
                console.print(f"[dim]评分 {rating} 星已记录，记忆系统已更新 ✓[/dim]")
    except (ValueError, click.Abort):
        pass


def _init_config():
    """初始化配置文件"""
    config_dir = Path("configs")
    config_dir.mkdir(exist_ok=True)
    config_path = config_dir / "config.yaml"

    if config_path.exists():
        if not click.confirm(f"配置文件 {config_path} 已存在，是否覆盖？"):
            return

    # 复制示例配置
    example_path = Path(__file__).parent.parent / "configs" / "config.example.yaml"
    if example_path.exists():
        import shutil
        shutil.copy2(example_path, config_path)
        console.print(f"[green]✓[/green] 配置文件已创建: {config_path}")
        console.print("[dim]请编辑配置文件，填入你的 API Keys[/dim]")
    else:
        console.print("[red]示例配置文件不存在[/red]")


def _show_config():
    """显示当前配置（隐藏敏感信息）"""
    config = get_config()

    def mask(key: str) -> str:
        if not key:
            return "[dim]未配置[/dim]"
        return key[:4] + "****" + key[-4:] if len(key) > 8 else "****"

    table = Table(title="当前配置", show_lines=True)
    table.add_column("配置项", style="bold")
    table.add_column("值")

    table.add_row("LLM 提供商", config.llm.default_provider)
    table.add_row("LLM API Key", mask(getattr(getattr(config.llm, config.llm.default_provider, None), "api_key", "")))
    table.add_row("图像生成", config.image_gen.provider)
    table.add_row("图像 API Key", mask(config.image_gen.api_key))
    table.add_row("TTS 提供商", config.tts.default_provider)
    table.add_row("TTS API Key", mask(config.tts.api_key))
    table.add_row("视频引擎", config.video_gen.default_provider)
    table.add_row("Kling API Key", mask(config.video_gen.kling.api_key))
    table.add_row("输出目录", config.local.output_dir)
    table.add_row("记忆系统", f"{config.memory.provider} ({'启用' if config.memory.enabled else '禁用'})")

    console.print(table)


def _set_config(key: str, value: str):
    """设置配置项"""
    import yaml

    config_path = Path("configs/config.yaml")
    if not config_path.exists():
        console.print("[red]配置文件不存在，请先运行 pilipili config --init[/red]")
        return

    with open(config_path, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f) or {}

    # 解析嵌套键（如 llm.default_provider）
    keys = key.split(".")
    d = config_data
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config_data, f, allow_unicode=True, default_flow_style=False)

    console.print(f"[green]✓[/green] 已设置 {key} = {value}")


if __name__ == "__main__":
    cli()
