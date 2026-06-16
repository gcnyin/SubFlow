"""Translate an existing SRT file using SubFlow's translation engine.

Usage:
    uv run python scripts/translate_srt.py <input.srt> [--target zh] [-v]
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

# Add project src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from subflow.models import SubtitleItem
from subflow.config import load_config
from subflow.translate import OpenAITranslator, create_translator
from subflow.subtitle import write_subtitle
from subflow.logging import setup_logging, get_logger

logger = get_logger(__name__)


def parse_srt(text: str) -> list[SubtitleItem]:
    """Parse SRT text into SubtitleItem list."""
    items: list[SubtitleItem] = []
    blocks = re.split(r"\n\s*\n", text.strip())
    
    ts_pattern = re.compile(
        r"(\d{2}):(\d{2}):(\d{2})[,.]\s*(\d{3})\s*-->\s*"
        r"(\d{2}):(\d{2}):(\d{2})[,.]\s*(\d{3})"
    )

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n")
        if len(lines) < 3:
            continue
        
        idx_line = lines[0].strip()
        ts_line = lines[1].strip()
        text_line = " ".join(line.strip() for line in lines[2:])

        try:
            index = int(idx_line)
        except ValueError:
            continue

        m = ts_pattern.search(ts_line)
        if not m:
            continue

        h1, m1, s1, ms1, h2, m2, s2, ms2 = map(int, m.groups())
        start = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000
        end = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000

        items.append(SubtitleItem(
            index=index,
            start=start,
            end=end,
            text=text_line,
        ))

    return items


def main():
    if len(sys.argv) < 2:
        print("Usage: python translate_srt.py <input.srt> [--target zh] [--source en] [-v] [-vv]")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    if not input_path.exists():
        print(f"File not found: {input_path}")
        sys.exit(1)

    target_lang = "zh"
    source_lang = "en"
    verbose = 0
    
    # Parse CLI args
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--target" and i + 1 < len(args):
            target_lang = args[i + 1]
            i += 2
        elif args[i] == "--source" and i + 1 < len(args):
            source_lang = args[i + 1]
            i += 2
        elif args[i] in ("-v", "--verbose"):
            verbose = 1
            i += 1
        elif args[i] == "-vv":
            verbose = 2
            i += 1
        else:
            i += 1

    # Set up logging so we see translate module's messages too
    setup_logging(verbose)

    logger.info("═" * 50)
    logger.info("SubFlow SRT 翻译工具")
    logger.info("═" * 50)

    # ── Parse SRT ──
    logger.info("")
    logger.info("━" * 50)
    logger.info("Step 1/3: 解析 SRT")
    logger.info("━" * 50)
    t0 = time.time()
    srt_text = input_path.read_text(encoding="utf-8")
    items = parse_srt(srt_text)
    logger.info("   文件: %s", input_path)
    logger.info("   解析完成: %d 条字幕 (%.2fs)", len(items), time.time() - t0)
    
    if not items:
        logger.error("   未解析到任何字幕条目")
        sys.exit(1)

    # ── Show preview ──
    logger.info("   前 3 条原文:")
    for item in items[:3]:
        logger.info("     [%d] %s", item.index, item.text[:80])

    # ── Load config & create translator ──
    logger.info("")
    logger.info("━" * 50)
    logger.info("Step 2/3: 初始化翻译器")
    logger.info("━" * 50)
    config = load_config()
    translator = create_translator(config.translator)
    logger.info("   API: %s", translator.base_url)
    logger.info("   模型: %s", translator.model)
    logger.info("   批次大小: <=%d 句/批", translator.batch_size)

    # ── Translate ──
    logger.info("")
    logger.info("━" * 50)
    logger.info("Step 3/3: AI 翻译 %s -> %s", source_lang, target_lang)
    logger.info("━" * 50)

    try:
        translated = translator.translate(items, source_lang, target_lang)
    except Exception as e:
        logger.error("翻译失败: %s", e)
        sys.exit(1)

    # ── Write output ──
    output_path = input_path.parent / f"{input_path.stem}.{target_lang}.srt"
    write_subtitle(translated, output_path, fmt="srt")
    logger.info("   输出文件: %s", output_path)

    # ── Preview ──
    logger.info("")
    logger.info("翻译预览 (前 5 条):")
    for i, item in enumerate(translated[:5]):
        orig = items[i]
        logger.info("   [%d] EN: %s", item.index, orig.text[:70])
        logger.info("   [%d] ZH: %s", item.index, item.text[:70])
        logger.info("")

    logger.info("═" * 50)
    logger.info("完成! 输出: %s", output_path)
    logger.info("═" * 50)


if __name__ == "__main__":
    main()
