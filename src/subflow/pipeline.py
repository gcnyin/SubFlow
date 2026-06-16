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
    logger.info("Transcript saved: %s", output_path)


def run_pipeline(input_file: Path, config: SubFlowConfig) -> Path:
    """Run the full subtitle generation pipeline for a single file.

    Pipeline:
        1. Extract audio (skip if already audio)
        2. Transcribe with faster-whisper
        3. Align and split into subtitle items
        4. Output source subtitles
        5. Translate (optional, if target_langs is set)
        6. Output translated subtitles

    Args:
        input_file: Path to video or audio file.
        config: Pipeline configuration.

    Returns:
        Path to the generated source subtitle file.

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
            logger.info("Detected audio file, skipping extraction")
        else:
            logger.info("Extracting audio...")
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
            logger.info("Done (%.1fs, %.1fMB)", elapsed, size_mb)

        # ── Step 2: Create transcriber ──
        device_desc = detect_device()
        logger.info("Device: %s", device_desc)

        transcriber = create_transcriber(
            model_size=config.model,
            device=config.device,
            model_dir=config.model_path(),
        )

        # ── Step 3: Transcription ──
        logger.info("Transcribing (model: %s)...", config.model)
        t0 = time.time()

        words, detected_lang = transcriber.transcribe(
            audio_file,
            language=config.language,
            beam_size=config.beam_size,
        )

        source_lang = config.language or detected_lang
        elapsed = time.time() - t0
        logger.info("Done (%.1fs, %d words)", elapsed, len(words))

        if not words:
            raise RuntimeError("未识别到任何语音内容")

        # Optional: dump transcript JSON
        if config.dump_json:
            json_path = _source_output_path(input_file, config).with_suffix(".transcript.json")
            _dump_transcript_json(words, json_path, source_lang)

        # ── Step 4: Alignment and splitting ──
        logger.info("Generating subtitles...")
        t0 = time.time()

        items = split_and_align(
            words,
            max_words=config.max_words_per_line,
            max_duration=config.max_duration_seconds,
        )

        # ── Step 5: Output source subtitles ──
        source_path = _source_output_path(input_file, config)
        result_path: Path | None = source_path
        if not config.no_source:
            write_subtitle(items, source_path, fmt=config.default_format)
            logger.info("%d lines -> %s", len(items), source_path)
        else:
            result_path = None  # Reset — source was not actually written

        # ── Step 6: Translation (optional) ──
        if config.target_langs:
            translator = create_translator(config.translator)
            for target_lang in config.target_langs:
                logger.info(
                    "Translating %s->%s (%d sentences)...",
                    source_lang, target_lang, len(items),
                )
                t_t0 = time.time()
                try:
                    translated = translator.translate(items, source_lang, target_lang)
                    trans_path = _translated_output_path(input_file, config, target_lang)
                    write_subtitle(translated, trans_path, fmt=config.default_format)
                    t_elapsed = time.time() - t_t0
                    logger.info("Done (%.1fs) -> %s", t_elapsed, trans_path)
                    if result_path is None:
                        result_path = trans_path
                except Exception as e:
                    logger.error("Translation failed (%s->%s): %s", source_lang, target_lang, e)

        # ── Step 7: Burn subtitles (optional) ──
        if config.burn:
            # Collect subtitle files to burn
            to_burn: list[tuple[Path, str]] = []  # (srt_path, kind label)
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

                try:
                    burn_subtitle(
                        video_path=input_file,
                        subtitle_path=srt_path,
                        output_path=out_video,
                        ffmpeg=config.ffmpeg_path,
                    )
                    if result_path is None:
                        result_path = out_video
                except Exception as e:
                    logger.error("Burn failed: %s", e)

        total_elapsed = time.time() - start_time
        logger.info("Total time: %.1fs", total_elapsed)

        return result_path if result_path is not None else source_path

    finally:
        # Clean up temp audio file
        if temp_audio and audio_file is not None:
            with contextlib.suppress(OSError):
                os.unlink(audio_file)
