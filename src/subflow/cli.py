"""CLI entry point for SubFlow — AI-powered subtitle generation."""

import sys
from pathlib import Path
from typing import Annotated

import typer

from subflow.config import load_config
from subflow.logging import get_logger, setup_logging
from subflow.pipeline import run_pipeline

logger = get_logger(__name__)

app = typer.Typer(
    name="subflow",
    help="🎬 SubFlow — AI 视频字幕生成工具",
    add_completion=False,
    pretty_exceptions_enable=False,
)


def _version_callback(value: bool) -> None:
    if value:
        from subflow import __version__  # noqa: PLC0415
        print(f"SubFlow v{__version__}")
        raise typer.Exit()


@app.callback()
def _app_callback(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="显示版本号"),
    ] = None,
) -> None:
    """App-level callback for global options."""


def _setup_cli_logging(verbose: int) -> None:
    """Configure logging level based on verbosity."""
    setup_logging(verbose)


@app.command(name="run")
def main(
    files: Annotated[
        list[Path],
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="视频或音频文件（支持多个）",
        ),
    ],
    # ── Model options ──
    model: Annotated[
        str,
        typer.Option("--model", "-m", help="Whisper 模型大小 (tiny/base/small/medium/large-v3)"),
    ] = "",
    language: Annotated[
        str | None,
        typer.Option("--lang", "-l", help="语言代码 (zh/en/ja/...) 或留空自动检测"),
    ] = None,
    beam_size: Annotated[
        int,
        typer.Option("--beam-size", help="束搜索宽度 (默认 5)"),
    ] = 0,
    device: Annotated[
        str,
        typer.Option("--device", help="计算设备 (auto/cpu/cuda)"),
    ] = "",
    model_dir: Annotated[
        str | None,
        typer.Option("--model-dir", help="模型存储目录"),
    ] = None,
    # ── Output options ──
    fmt: Annotated[
        str,
        typer.Option("--format", "-f", help="字幕格式 (srt/vtt)"),
    ] = "",
    output: Annotated[
        str | None,
        typer.Option("--output", "-o", help="输出文件路径"),
    ] = None,
    output_dir: Annotated[
        str | None,
        typer.Option("--output-dir", help="输出目录"),
    ] = None,
    # ── Audio options ──
    audio_track: Annotated[
        int,
        typer.Option("--audio-track", help="音轨索引 (默认 0)"),
    ] = -1,
    keep_audio: Annotated[
        str | None,
        typer.Option("--keep-audio", help="保留提取的音频到指定路径"),
    ] = None,
    # ── Translation options ──
    target_lang: Annotated[
        str | None,
        typer.Option(
            "--target-lang", "-t",
            help="目标翻译语言，逗号分隔 (如 en,ja)",
        ),
    ] = None,
    no_source: Annotated[
        bool,
        typer.Option("--no-source", help="不输出原文字幕，仅输出译文"),
    ] = False,
    translator_base_url: Annotated[
        str | None,
        typer.Option("--translator-base-url", help="LLM API 地址"),
    ] = None,
    translator_api_key: Annotated[
        str | None,
        typer.Option("--translator-api-key", help="LLM API 密钥"),
    ] = None,
    translator_model: Annotated[
        str | None,
        typer.Option("--translator-model", help="LLM 模型名"),
    ] = None,
    translator_temperature: Annotated[
        float | None,
        typer.Option("--translator-temperature", help="LLM 温度 (默认 0.2)"),
    ] = None,
    # ── Burn options ──
    burn: Annotated[
        bool,
        typer.Option("--burn", help="生成字幕时同时烧录到视频"),
    ] = False,
    burn_lang: Annotated[
        str | None,
        typer.Option("--burn-lang", help="指定烧录的语言 (多目标语言时)"),
    ] = None,
    no_burn_source: Annotated[
        bool,
        typer.Option("--no-burn-source", help="不烧录原文字幕"),
    ] = False,
    ffmpeg_path: Annotated[
        str | None,
        typer.Option(
            "--ffmpeg-path",
            help="FFmpeg 可执行文件路径",
        ),
    ] = None,
    # ── Processing options ──
    max_duration: Annotated[
        float | None,
        typer.Option("--max-duration", help="最大处理时长（秒）"),
    ] = None,
    max_words: Annotated[
        int,
        typer.Option("--max-words", help="每行字幕最大词数 (默认 15)"),
    ] = 0,
    max_line_duration: Annotated[
        float,
        typer.Option("--max-line-duration", help="每行字幕最大时长/秒 (默认 3.0)"),
    ] = 0.0,
    # ── Debug options ──
    verbose: Annotated[
        int,
        typer.Option("--verbose", "-v", count=True, help="详细输出 (-v 信息, -vv 调试)"),
    ] = 0,
    dump_json: Annotated[
        bool,
        typer.Option("--dump-json", help="输出完整 transcript 到 JSON 文件"),
    ] = False,
    config_path: Annotated[
        str | None,
        typer.Option("--config", "-c", help="配置文件路径"),
    ] = None,
) -> None:
    """SubFlow — AI 视频字幕生成

    从视频或音频文件自动生成 SRT/VTT 字幕，支持词级对齐和智能拆分。

    \\b
    示例:
      subflow video.mp4                    # 默认 SRT 字幕
      subflow video.mp4 --format vtt       # VTT 格式
      subflow video.mp4 -t en              # 翻译为英文
      subflow video.mp4 -t en,ja           # 多语言翻译
      subflow video.mp4 -t en --burn       # 翻译并烧录到视频
      subflow *.mp4                        # 批量处理
      subflow podcast.mp3 --lang zh        # 指定语言
      subflow video.mp4 -vv --dump-json    # 调试模式
    """
    _setup_cli_logging(verbose)

    # ── Load config ──
    config = load_config(config_path)

    # ── Merge CLI overrides into config ──
    overrides: dict[str, object] = {}
    if model:
        overrides["model"] = model
    if language is not None:
        overrides["language"] = language
    if beam_size > 0:
        overrides["beam_size"] = beam_size
    if device:
        overrides["device"] = device
    if model_dir is not None:
        overrides["model_dir"] = model_dir
    if fmt:
        overrides["default_format"] = fmt
    if output is not None:
        overrides["output"] = output
    if output_dir is not None:
        overrides["output_dir"] = output_dir
    if audio_track >= 0:
        overrides["audio_track"] = audio_track
    if keep_audio is not None:
        overrides["keep_audio"] = keep_audio
    if max_duration is not None:
        overrides["max_duration"] = max_duration
    if max_words > 0:
        overrides["max_words_per_line"] = max_words
    if max_line_duration > 0:
        overrides["max_duration_seconds"] = max_line_duration
    # Translation overrides
    if target_lang is not None:
        overrides["target_langs"] = [t.strip() for t in target_lang.split(",") if t.strip()]
    overrides["no_source"] = no_source
    if translator_base_url is not None:
        config.translator.base_url = translator_base_url
    if translator_api_key is not None:
        config.translator.api_key = translator_api_key
    if translator_model is not None:
        config.translator.model = translator_model
    if translator_temperature is not None:
        config.translator.temperature = translator_temperature
    # Burn overrides
    overrides["burn"] = burn
    if burn_lang is not None:
        overrides["burn_lang"] = burn_lang
    if no_burn_source:
        overrides["burn_source"] = False
    if ffmpeg_path is not None:
        overrides["ffmpeg_path"] = ffmpeg_path
    overrides["dump_json"] = dump_json
    overrides["verbose"] = verbose

    config.merge_cli(**overrides)

    # ── Process each file ──
    total = len(files)
    success = 0
    failed: list[tuple[Path, str]] = []

    for i, filepath in enumerate(files, 1):
        if total > 1:
            print(f"\n{'─' * 60}")
            print(f"[{i}/{total}] {filepath.name}")
            print(f"{'─' * 60}")

        try:
            run_pipeline(filepath, config)
            success += 1
        except Exception as e:
            error_msg = str(e)
            failed.append((filepath, error_msg))
            if verbose > 0:
                logger.exception("处理失败: %s", filepath)
            else:
                logger.error("处理失败: %s", error_msg)

    # ── Summary ──
    if total > 1:
        print(f"\n{'─' * 60}")
        print(f"✅ 完成: {success}/{total}")
        if failed:
            print(f"❌ 失败: {len(failed)}")
            for f, err in failed:
                print(f"   • {f.name}: {err}")


@app.command(name="burn")
def burn(
    video: Annotated[
        Path,
        typer.Argument(
            exists=True, file_okay=True, dir_okay=False, readable=True,
            help="目标视频文件",
        ),
    ],
    subtitle: Annotated[
        Path | None,
        typer.Option("--subtitle", "-s", exists=True, help="字幕文件 (SRT)"),
    ] = None,
    output: Annotated[
        str | None,
        typer.Option("--output", "-o", help="输出视频路径"),
    ] = None,
    font: Annotated[
        str | None,
        typer.Option("--font", help="字体名称或 .ttf/.otf 路径"),
    ] = None,
    font_size: Annotated[
        int | None,
        typer.Option("--font-size", help="字号 (0=自动按视频高度缩放)"),
    ] = None,
    font_color: Annotated[
        str | None,
        typer.Option("--font-color", help="字体颜色 #RRGGBB 或颜色名"),
    ] = None,
    outline_color: Annotated[
        str | None,
        typer.Option("--outline-color", help="描边颜色, none 关闭"),
    ] = None,
    outline_width: Annotated[
        int | None,
        typer.Option("--outline-width", help="描边粗细/px (0=自动按字号缩放)"),
    ] = None,
    position: Annotated[
        str | None,
        typer.Option("--position", help="字幕位置: bottom/top/middle"),
    ] = None,
    margin: Annotated[
        int | None,
        typer.Option("--margin", help="底部边距/px"),
    ] = None,
    crf: Annotated[
        int | None,
        typer.Option("--crf", help="CRF 质量 (默认 23, 越小越清晰)"),
    ] = None,
    fonts_dir: Annotated[
        str | None,
        typer.Option("--fonts-dir", help="字体目录"),
    ] = None,
    ffmpeg: Annotated[
        str | None,
        typer.Option("--ffmpeg-path", help="FFmpeg 可执行文件路径"),
    ] = None,
) -> None:
    """将字幕烧录到视频中（硬字幕）。

    示例:
      subflow burn video.mp4 -s video.srt
      subflow burn video.mp4 -s video.en.srt --font "Arial"
      subflow burn video.mp4 -s sub.srt --font-color yellow --outline-color black
    """
    from subflow.burn import burn_subtitle
    from subflow.config import load_config

    # Merge with config file defaults
    cfg = load_config().burn_config

    _font_size = font_size if font_size is not None else cfg.font_size
    _outline_width = outline_width if outline_width is not None else cfg.outline_width
    _font_color = font_color if font_color is not None else cfg.font_color
    _outline_color = outline_color if outline_color is not None else cfg.outline_color
    _position = position if position is not None else cfg.position
    _margin = margin if margin is not None else cfg.margin
    _crf = crf if crf is not None else cfg.crf
    _font = font or cfg.font or None
    _fonts_dir = fonts_dir or cfg.fonts_dir or None

    # Default subtitle path: same stem as video, .srt extension
    if subtitle is None:
        subtitle = video.with_suffix(".srt")

    # Default output path: video.burned.mp4
    if output is None:
        output = str(video.parent / f"{video.stem}.burned{video.suffix}")
    out_path = Path(output).expanduser().resolve()

    burn_subtitle(
        video_path=video,
        subtitle_path=subtitle,
        output_path=out_path,
        font=_font,
        font_size=_font_size,
        font_color=_font_color,
        outline_color=_outline_color,
        outline_width=_outline_width,
        position=_position,
        margin=_margin,
        fonts_dir=_fonts_dir,
        crf=_crf,
        ffmpeg=ffmpeg,
    )


@app.command(name="list-models")
def list_models() -> None:
    """列出可用的 Whisper 模型大小。"""
    models = [
        ("tiny", "~150MB", "最快，精度最低"),
        ("tiny.en", "~150MB", "仅英文，更快"),
        ("base", "~290MB", "速度快，精度一般"),
        ("base.en", "~290MB", "仅英文"),
        ("small", "~970MB", "速度与精度平衡 (小)"),
        ("small.en", "~970MB", "仅英文"),
        ("medium", "~3.1GB", "推荐：速度与精度平衡"),
        ("medium.en", "~3.1GB", "仅英文"),
        ("large-v2", "~6.2GB", "高精度，较慢"),
        ("large-v3", "~6.2GB", "最高精度，最慢"),
    ]
    print(f"{'模型':<15} {'大小':<10} 说明")
    print("-" * 50)
    for name, size, desc in models:
        default = " ★ 默认" if name == "medium" else ""
        print(f"  {name:<13} {size:<10} {desc}{default}")


def main_cli() -> None:
    """Entry point for console_scripts.

    If no subcommand is given, default to 'run' for convenience:
        subflow video.mp4  →  subflow run video.mp4
    """
    # If first positional arg is not a known command, insert 'run'
    known = {cmd.name for cmd in app.registered_commands}
    args = sys.argv[1:]
    if args and not args[0].startswith("-") and args[0] not in known:
        sys.argv.insert(1, "run")
    app()


if __name__ == "__main__":
    main_cli()
