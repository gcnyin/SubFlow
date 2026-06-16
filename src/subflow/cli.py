"""CLI entry point for SubFlow — AI-powered subtitle generation."""

import logging
import sys
from pathlib import Path
from typing import Annotated

import typer

from subflow.config import load_config
from subflow.pipeline import run_pipeline

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


# ── Logging setup ──
logger = logging.getLogger("subflow")


def _setup_logging(verbose: int) -> None:
    """Configure logging level based on verbosity."""
    levels = [logging.WARNING, logging.INFO, logging.DEBUG]
    level = levels[min(verbose, len(levels) - 1)]
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s" if verbose > 0 else "%(message)s",
        stream=sys.stderr,
    )
    # Suppress noisy third-party loggers unless -vv
    if verbose < 2:
        for name in ("faster_whisper", "huggingface_hub", "httpx", "urllib3"):
            logging.getLogger(name).setLevel(logging.WARNING)


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
      subflow *.mp4                        # 批量处理
      subflow podcast.mp3 --lang zh        # 指定语言
      subflow video.mp4 -vv --dump-json    # 调试模式
    """
    _setup_logging(verbose)

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
                print(f"❌ 处理失败: {error_msg}", file=sys.stderr)

    # ── Summary ──
    if total > 1:
        print(f"\n{'─' * 60}")
        print(f"✅ 完成: {success}/{total}")
        if failed:
            print(f"❌ 失败: {len(failed)}")
            for f, err in failed:
                print(f"   • {f.name}: {err}")


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
