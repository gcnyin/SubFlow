"""Pipeline orchestration — connects all stages of subtitle generation."""

import contextlib
import os
import time
from pathlib import Path

from subflow.align import split_and_align
from subflow.audio import extract_audio, is_audio_file
from subflow.config import SubFlowConfig
from subflow.subtitle import write_subtitle
from subflow.transcribe import create_transcriber, detect_device


def _resolve_output_path(input_file: Path, config: SubFlowConfig) -> Path:
    """Determine the output subtitle file path."""
    fmt = config.default_format

    if config.output:
        return Path(config.output).expanduser().resolve()

    if config.output_dir:
        out_dir = Path(config.output_dir).expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir / f"{input_file.stem}.{fmt}"

    return input_file.parent / f"{input_file.stem}.{fmt}"


def run_pipeline(input_file: Path, config: SubFlowConfig) -> Path:
    """Run the full subtitle generation pipeline for a single file.

    Pipeline:
        1. Extract audio (skip if already audio)
        2. Transcribe with faster-whisper
        3. Align and split into subtitle items
        4. Format and write output

    Args:
        input_file: Path to video or audio file.
        config: Pipeline configuration.

    Returns:
        Path to the generated subtitle file.

    Raises:
        RuntimeError: On any pipeline failure.
    """
    start_time = time.time()
    audio_file: Path | None = None
    temp_audio = False

    try:
        # ── Step 1: Audio extraction ──
        if is_audio_file(input_file):
            audio_file = input_file
            print("🎵 检测到音频文件，跳过提取")
        else:
            print("🎵 提取音频...")
            t0 = time.time()
            audio_file = extract_audio(
                input_file,
                audio_track=config.audio_track,
                output_path=(
                    Path(config.keep_audio) if config.keep_audio else None
                ),
            )
            temp_audio = config.keep_audio is None
            size_mb = audio_file.stat().st_size / (1024 * 1024)
            elapsed = time.time() - t0
            print(f"   ✓ 完成 ({elapsed:.1f}s, {size_mb:.1f}MB)")

        # ── Step 2: Create transcriber ──
        device_desc = detect_device()
        emoji = "🎮" if "CUDA" in device_desc else "🖥️"
        print(f"{emoji}  使用设备: {device_desc}")

        transcriber = create_transcriber(
            model_size=config.model,
            device=config.device,
            model_dir=config.model_path(),
        )

        # ── Step 3: Transcription ──
        print(f"🧠 语音识别 (模型: {config.model})...")
        t0 = time.time()

        words = transcriber.transcribe(
            audio_file,
            language=config.language,
            beam_size=config.beam_size,
        )

        elapsed = time.time() - t0
        print(f"   ✓ 识别完成 ({elapsed:.1f}s, {len(words)} 词)")

        if not words:
            raise RuntimeError("未识别到任何语音内容")

        # Optional: dump transcript JSON
        if config.dump_json:
            json_path = _resolve_output_path(input_file, config).with_suffix(".transcript.json")
            import json
            data = {
                "language": config.language or "auto-detected",
                "words": [
                    {"word": w.word, "start": w.start, "end": w.end, "probability": w.probability}
                    for w in words
                ],
            }
            json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"📄 Transcript 已保存到: {json_path}")

        # ── Step 4: Alignment and splitting ──
        print("📝 生成字幕...")
        t0 = time.time()

        items = split_and_align(
            words,
            max_words=config.max_words_per_line,
            max_duration=config.max_duration_seconds,
        )

        output_path = _resolve_output_path(input_file, config)
        write_subtitle(items, output_path, fmt=config.default_format)

        elapsed = time.time() - t0
        total_elapsed = time.time() - start_time

        print(f"   ✓ {len(items)} 条字幕 → {output_path}")
        print(f"⏱️  总耗时: {total_elapsed:.1f}s")

        return output_path

    finally:
        # Clean up temp audio file
        if temp_audio and audio_file is not None:
            with contextlib.suppress(OSError):
                os.unlink(audio_file)
