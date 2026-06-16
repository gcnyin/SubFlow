"""Tests for alignment and smart splitting."""

from subflow.align import split_and_align
from subflow.models import WordTimestamp


class TestSplitAndAlign:
    """Tests for split_and_align function."""

    def test_empty_input(self) -> None:
        """Empty word list should return empty result."""
        assert split_and_align([]) == []

    def test_single_word(self) -> None:
        """Single word should produce one subtitle item."""
        words = [WordTimestamp("Hello", 0.0, 1.0, 1.0)]
        result = split_and_align(words)
        assert len(result) == 1
        assert result[0].index == 1
        assert result[0].text == "Hello"
        assert result[0].start == 0.0
        assert result[0].end == 1.0

    def test_splits_on_sentence_boundary(self, sample_words: list[WordTimestamp]) -> None:
        """Should split at Chinese sentence-ending punctuation (。)."""
        result = split_and_align(sample_words)
        assert len(result) == 2
        # First group: "今天天气真好。" — 5 words
        assert result[0].text.startswith("今天天气真好")
        assert result[0].start == 0.0
        # Second group: "我们去公园散步吧。" — 6 words
        assert result[1].text.startswith("我们去公园散步吧")
        assert result[1].start == 1.5

    def test_splits_on_max_words(self) -> None:
        """Should split when word count exceeds max_words."""
        # 20 words, no punctuation — should split at 15
        words = [WordTimestamp(f"word{i}", i * 0.1, i * 0.1 + 0.1, 1.0) for i in range(20)]
        result = split_and_align(words, max_words=15)
        assert len(result) == 2
        # First group: 15 words
        assert len(result[0].words) <= 15
        # Second group: remaining 5 words
        assert len(result[1].words) == 5

    def test_splits_on_max_duration(self) -> None:
        """Should split when group duration exceeds max_duration."""
        # Words spread over 10 seconds
        words = [
            WordTimestamp(f"word{i}", i * 2.0, i * 2.0 + 0.5, 1.0) for i in range(5)
        ]
        result = split_and_align(words, max_duration=3.0, max_words=100)
        # Each word is 2 seconds apart, so after 2 words we exceed 3 seconds
        assert len(result) >= 2

    def test_index_is_sequential(self, sample_words: list[WordTimestamp]) -> None:
        """Subtitle indices should be 1-based and sequential."""
        result = split_and_align(sample_words)
        indices = [item.index for item in result]
        assert indices == list(range(1, len(result) + 1))

    def test_text_no_extra_spaces(self) -> None:
        """Merged text should not have double spaces."""
        words = [
            WordTimestamp("Hello", 0.0, 0.5, 1.0),
            WordTimestamp(" ", 0.5, 0.6, 1.0),
            WordTimestamp("world", 0.6, 1.0, 1.0),
        ]
        result = split_and_align(words, max_words=10)
        assert len(result) == 1
        assert result[0].text == "Hello world"

    def test_skips_empty_words(self) -> None:
        """Empty or whitespace-only words should be skipped."""
        words = [
            WordTimestamp("Hello", 0.0, 0.5, 1.0),
            WordTimestamp("", 0.5, 0.5, 1.0),
            WordTimestamp(" world", 0.6, 1.0, 1.0),
        ]
        result = split_and_align(words, max_words=10)
        assert len(result) == 1
        # faster-whisper includes leading spaces on English words;
        # the empty string is skipped, "Hello" + " world" → "Hello world"
        assert result[0].text == "Hello world"

    def test_boundary_only_when_enough_content(self) -> None:
        """Should not split on boundary if group has too few words (< 3)."""
        words = [
            WordTimestamp("Hi", 0.0, 0.5, 1.0),
            WordTimestamp(".", 0.5, 0.6, 1.0),
            WordTimestamp("Bye", 0.7, 1.0, 1.0),
            WordTimestamp(".", 1.0, 1.1, 1.0),
        ]
        result = split_and_align(words, max_words=10)
        # With a group of just "Hi." we won't split because < 3 content words
        # But "Hi . Bye ." totals 4 content words — need to check how boundary works
        # Actually: Hi (1) + . (punct, not counted) + Bye (2) ... still < 3 when hitting first "."
        # So it won't split. Then "Hi . Bye ." has 2 content words, no split needed.
        assert len(result) == 1
