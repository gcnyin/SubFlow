"""Word-level alignment and smart splitting into subtitle items."""

import re
import time
from collections.abc import Callable

from subflow.logging import get_logger
from subflow.models import SubtitleItem, WordTimestamp

logger = get_logger(__name__)

# Characters that signal a natural break point for subtitle splitting
_SENTENCE_BOUNDARY = re.compile(r"[。！？，、；：.!?,;:\"')}\]】》）»]")


def _is_boundary(word: str) -> bool:
    """Check if a word ends with a sentence-boundary punctuation character."""
    return bool(_SENTENCE_BOUNDARY.search(word))


def _is_punctuation_only(word: str) -> bool:
    """Check if a word is only punctuation/whitespace."""
    stripped = word.strip()
    return len(stripped) > 0 and all(
        ch in "。！？，、；：.!?,;:\"'()[]{}【】《》（）»«…—–-" for ch in stripped
    )


def split_and_align(
    words: list[WordTimestamp],
    max_words: int = 15,
    max_duration: float = 3.0,
    boundary_detector: Callable[[str], bool] = _is_boundary,
) -> list[SubtitleItem]:
    """Split word timestamps into subtitle items intelligently.

    Splits when:
    1. The current group reaches max_words words.
    2. The current group's duration exceeds max_duration seconds.
    3. A sentence boundary punctuation is encountered (preferred break point).

    Args:
        words: Word-level timestamps from ASR.
        max_words: Maximum words per subtitle line.
        max_duration: Maximum duration per subtitle in seconds.
        boundary_detector: Function to detect sentence boundaries.

    Returns:
        List of SubtitleItem ready for formatting.
    """
    if not words:
        return []

    t0 = time.time()
    logger.info("   输入: %d 个词级时间戳", len(words))

    items: list[SubtitleItem] = []
    group: list[WordTimestamp] = []
    index = 1
    break_reasons: dict[str, int] = {"boundary": 0, "words": 0, "duration": 0}

    def _flush(reason: str = "") -> None:
        nonlocal index
        if not group:
            return
        # Join words with spaces, then remove spaces between CJK characters
        raw = " ".join(w.word for w in group)
        # Remove spaces between CJK chars (Chinese, Japanese, Korean)
        cjk = r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]"
        text = re.sub(f"(?<={cjk})\\s+(?={cjk})", "", raw)
        # Remove space before CJK punctuation
        text = re.sub(r"\s+([，。！？、；：」』）】])", r"\1", text)
        # Collapse remaining whitespace
        text = re.sub(r"\s+", " ", text).strip()
        items.append(
            SubtitleItem(
                index=index,
                start=group[0].start,
                end=group[-1].end,
                text=text,
                words=list(group),
            )
        )
        group.clear()
        index += 1

    for word in words:
        # Skip truly empty words (keep whitespace tokens for spacing)
        if not word.word:
            continue

        group.append(word)
        group_duration = group[-1].end - group[0].start
        group_word_count = sum(1 for w in group if not _is_punctuation_only(w.word))

        # Determine if we should break
        should_break = False
        reason = ""

        # Hard limits (max words/duration) or soft limit (sentence boundary with enough content)
        if group_word_count >= max_words:
            should_break = True
            reason = "words"
        elif group_duration >= max_duration:
            should_break = True
            reason = "duration"
        elif group_word_count >= 3 and _is_boundary(word.word):
            should_break = True
            reason = "boundary"

        if should_break:
            break_reasons[reason] = break_reasons.get(reason, 0) + 1
            _flush(reason)

    # Flush remaining words
    _flush("final")

    elapsed = time.time() - t0
    logger.info("   拆分完成: %d 条字幕 (%.2fs)", len(items), elapsed)
    logger.info("   拆分原因: 标点=%d, 词数=%d, 时长=%d",
                 break_reasons.get("boundary", 0),
                 break_reasons.get("words", 0),
                 break_reasons.get("duration", 0))

    return items
