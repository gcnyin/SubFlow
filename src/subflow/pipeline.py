"""Pipeline orchestration — connects all stages of subtitle generation."""

from __future__ import annotations

import contextlib
import json
import os
import time
from pathlib import Path
from typing import Any

from subflow.align import split_and_align
from subflow.audio import extract_audio, is_audio_file
from subflow.burn import burn_subtitle
from subflow.config import SubFlowConfig
from subflow.logging import get_logger
from subflow.subtitle import write_subtitle
from subflow.transcribe import create_transcriber, detect_device
from subflow.translate import create_translator

logger = get_logger(__name__)


def _source_output_path(input_file: Path, config: SubFlowConfig) -> Path:
    """Determine the output subtitle path for the source (original) language."""
    fmt = config.default_format

    if config.output:
        return Path(config.output).expanduser().resolve()

    if config.output_dir:
        out_dir = Path(config.output_dir).expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir / f"{input_file.stem}.{fmt}"

    return input_file.parent / f"{input_file.stem}.{fmt}"


def _translated_output_path(input_file: Path, config: SubFlowConfig, target_lang: str) -> Path:
    """Determine the output subtitle path for a translated language."""
    fmt = config.default_format

    if config.output_dir:
        out_dir = Path(config.output_dir).expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir / f"{input_file.stem}.{target_lang}.{fmt}"

    return input_file.parent / f"{input_file.stem}.{target_lang}.{fmt}"


def _dump_transcript_json(words: list[Any], output_path: Path, source_lang: str) -> None:
    """Write word-level transcript to a JSON file."""
    data = {
        "language": source_lang,
        "words": [
            {"word": w.word, "start": w.start, "end": w.end, "probability": w.probability}
            for w in words
        ],
    }
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Transcript 已保存: %s", output_path)


def run_pipeline(input_file: Path, config: SubFlowConfig) -> Path:
    """Run the full subtitle generation pipeline for a single file.

    Pipeline:
        1. Extract audio (skip if already audio)
        2. Transcribe with faster-whisper
        3. Align and split into subtitle items
        4. Output source subtitles
        5. Translate (optional, if target_langs is set)
        6. Burn subtitles (optional, if --burn is set)

    Args:
        input_file: Path to video or audio file.
        config: Pipeline configuration.

    Returns:
        Path to the generated output file.

    Raises:
        RuntimeError: On any pipeline failure.
    """
    start_time = time.time()
    audio_file: Path | None = None
    temp_audio = False

    try:
        # ═══════════════════════════════════════════
        # Step 1/5: Audio extraction
        # ═══════════════════════════════════════════
        logger.info("")
        logger.info("━" * 50)
        logger.info("Step 1/5: 音频提取")
        logger.info("━" * 50)
        if is_audio_file(input_file):
            audio_file = input_file
            logger.info("   检测到音频文件, 跳过提取")
        else:
            logger.info("   从视频提取音频...")
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
            logger.info("   完成 (%.1fs, %.1fMB)", elapsed, size_mb)

        # ═══════════════════════════════════════════
        # Step 2/5: Load transcription model
        # ═══════════════════════════════════════════
        logger.info("")
        logger.info("━" * 50)
        logger.info("Step 2/5: 加载模型")
        logger.info("━" * 50)
        device_desc = detect_device()
        logger.info("   计算设备: %s", device_desc)
        logger.info("   模型: %s", config.model)

        t0 = time.time()
        transcriber = create_transcriber(
            model_size=config.model,
            device=config.device,
            model_dir=config.model_path(),
        )
        logger.info("   模型加载完成 (%.1fs)", time.time() - t0)

        # ═══════════════════════════════════════════
        # Step 3/5: Speech recognition
        # ═══════════════════════════════════════════
        logger.info("")
        logger.info("━" * 50)
        logger.info("Step 3/5: 语音识别")
        logger.info("━" * 50)
        t0 = time.time()

        words, detected_lang = transcriber.transcribe(
            audio_file,
            language=config.language,
            beam_size=config.beam_size,
        )

        source_lang = config.language or detected_lang
        elapsed = time.time() - t0
        logger.info("   识别完成 (%.1fs, %d 词, 语言: %s)", elapsed, len(words), source_lang)

        if not words:
            raise RuntimeError("未识别到任何语音内容")

        # Optional: dump transcript JSON
        if config.dump_json:
            json_path = _source_output_path(input_file, config).with_suffix(".transcript.json")
            _dump_transcript_json(words, json_path, source_lang)
            logger.info("   Transcript JSON -> %s", json_path)

        # ═══════════════════════════════════════════
        # Step 4/5: Align and split into subtitles
        # ═══════════════════════════════════════════
        logger.info("")
        logger.info("━" * 50)
        logger.info("Step 4/5: 字幕拆分与对齐")
        logger.info("━" * 50)
        logger.info("   参数: 每行 <=%d 词, 每行 <=%.1fs",
                     config.max_words_per_line, config.max_duration_seconds)
        t0 = time.time()

        items = split_and_align(
            words,
            max_words=config.max_words_per_line,
            max_duration=config.max_duration_seconds,
        )
        logger.info("   拆分为 %d 条字幕 (%.1fs)", len(items), time.time() - t0)

        # ── Write source subtitles ──
        source_path = _source_output_path(input_file, config)
        result_path: Path | None = source_path
        if not config.no_source:
            write_subtitle(items, source_path, fmt=config.default_format)
            logger.info("   原文字幕 -> %s", source_path)
        else:
            result_path = None

        # ═══════════════════════════════════════════
        # Step 5/5: Translation (optional)
        # ═══════════════════════════════════════════
        if config.target_langs:
            logger.info("")
            logger.info("━" * 50)
            logger.info("Step 5/5: AI 翻译")
            logger.info("━" * 50)
            translator = create_translator(config.translator)
            logger.info("   API: %s", config.translator.base_url)
            logger.info("   模型: %s", config.translator.model)
            logger.info("   温度: %.1f", config.translator.temperature)
            for target_lang in config.target_langs:
                logger.info("   %s -> %s", source_lang, target_lang)
                t_t0 = time.time()
                try:
                    translated = translator.translate(items, source_lang, target_lang)
                    trans_path = _translated_output_path(input_file, config, target_lang)
                    write_subtitle(translated, trans_path, fmt=config.default_format)
                    t_elapsed = time.time() - t_t0
                    logger.info("   译文字幕 -> %s (%.1fs)", trans_path, t_elapsed)
                    if result_path is None:
                        result_path = trans_path
                except Exception as e:
                    logger.error("   翻译失败 (%s->%s): %s", source_lang, target_lang, e)

        # ═══════════════════════════════════════════
        # Bonus: Burn subtitles (optional)
        # ═══════════════════════════════════════════
        if config.burn:
            logger.info("")
            logger.info("━" * 50)
            logger.info("Bonus: 字幕烧录")
            logger.info("━" * 50)
            to_burn: list[tuple[Path, str]] = []
            if not config.no_source and config.burn_source:
                to_burn.append((source_path, ""))

            if config.target_langs:
                langs_to_burn = config.target_langs
                if config.burn_lang:
                    langs_to_burn = [config.burn_lang]
                for lang in langs_to_burn:
                    srt_path = _translated_output_path(input_file, config, lang)
                    if srt_path.exists():
                        to_burn.append((srt_path, f".{lang}"))

            for srt_path, kind in to_burn:
                out_name = f"{input_file.stem}{kind}.burned.mp4"
                if config.output_dir:
                    out_video = Path(config.output_dir).expanduser().resolve() / out_name
                else:
                    out_video = input_file.parent / out_name

                logger.info("   烧录 %s -> %s", srt_path.name, out_video.name)
                try:
                    t0 = time.time()
                    bc = config.burn_config
                    burn_subtitle(
                        video_path=input_file,
                        subtitle_path=srt_path,
                        output_path=out_video,
                        font=bc.font or None,
                        font_size=bc.font_size,
                        font_color=bc.font_color,
                        outline_color=bc.outline_color,
                        outline_width=bc.outline_width,
                        position=bc.position,
                        margin=bc.margin,
                        fonts_dir=bc.fonts_dir or None,
                        crf=bc.crf,
                        ffmpeg=config.ffmpeg_path,
                    )
                    logger.info("   烧录完成 (%.1fs)", time.time() - t0)
                    if result_path is None:
                        result_path = out_video
                except Exception as e:
                    logger.error("   烧录失败: %s", e)

        total_elapsed = time.time() - start_time
        logger.info("")
        logger.info("═" * 50)
        logger.info("管线完成! 总耗时: %.1fs", total_elapsed)
        logger.info("═" * 50)

        return result_path if result_path is not None else source_path

    finally:
        if temp_audio and audio_file is not None:
            with contextlib.suppress(OSError):
                os.unlink(audio_file)
