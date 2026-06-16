"""Tests for SRT/VTT subtitle formatting."""

import tempfile
from pathlib import Path

import pytest

from subflow.models import SubtitleItem, WordTimestamp
from subflow.subtitle import (
    format_subtitle,
    to_srt,
    to_vtt,
    write_subtitle,
)


def _make_items() -> list[SubtitleItem]:
    """Create a standard set of subtitle items for testing."""
    return [
        SubtitleItem(
            index=1,
            start=0.0,
            end=2.5,
            text="今天天气真好。",
            words=[
                WordTimestamp("今天", 0.0, 0.3, 0.98),
                WordTimestamp("天气", 0.3, 0.6, 0.95),
                WordTimestamp("真", 0.6, 0.8, 0.92),
                WordTimestamp("好", 0.8, 1.0, 0.97),
                WordTimestamp("。", 1.0, 1.2, 0.5),
            ],
        ),
        SubtitleItem(
            index=2,
            start=3.0,
            end=5.5,
            text="我们去公园散步吧。",
            words=[
                WordTimestamp("我们", 3.0, 3.3, 0.96),
                WordTimestamp("去", 3.3, 3.5, 0.94),
                WordTimestamp("公园", 3.5, 3.8, 0.97),
                WordTimestamp("散步", 3.8, 4.1, 0.95),
                WordTimestamp("吧", 4.1, 4.3, 0.93),
                WordTimestamp("。", 4.3, 4.5, 0.5),
            ],
        ),
    ]


class TestSRTFormatting:
    """Tests for SRT output format."""

    def test_basic_srt(self) -> None:
        """Basic SRT structure should be correct."""
        items = _make_items()
        srt = to_srt(items)

        # Should contain two entries
        assert srt.count("-->") == 2
        assert "1\n" in srt
        assert "2\n" in srt

        # Timestamps should use comma for milliseconds
        assert "00:00:00,000 --> 00:00:02,500" in srt
        assert "00:00:03,000 --> 00:00:05,500" in srt

        # Should contain the text
        assert "今天天气真好。" in srt
        assert "我们去公园散步吧。" in srt

    def test_empty_srt(self) -> None:
        """Empty item list should produce empty string."""
        assert to_srt([]) == ""

    def test_timestamp_format(self) -> None:
        """Validate timestamp format: HH:MM:SS,mmm"""
        item = SubtitleItem(
            index=1,
            start=3661.123,  # 1h 1m 1s 123ms
            end=7322.456,  # 2h 2m 2s 456ms
            text="Test",
            words=[],
        )
        srt = to_srt([item])
        assert "01:01:01,123 --> 02:02:02,456" in srt


class TestVTTFormatting:
    """Tests for WebVTT output format."""

    def test_basic_vtt(self) -> None:
        """Basic VTT structure should be correct."""
        items = _make_items()
        vtt = to_vtt(items)

        # Must start with WEBVTT header
        assert vtt.startswith("WEBVTT\n")

        # Timestamps should use period for milliseconds
        assert "00:00:00.000 --> 00:00:02.500" in vtt
        assert "00:00:03.000 --> 00:00:05.500" in vtt

        # Should contain the text
        assert "今天天气真好。" in vtt
        assert "我们去公园散步吧。" in vtt

    def test_empty_vtt(self) -> None:
        """Empty VTT should still have the header."""
        vtt = to_vtt([])
        assert vtt == "WEBVTT\n\n"


class TestFormatSubtitle:
    """Tests for the format_subtitle dispatcher."""

    def test_format_srt(self) -> None:
        """format_subtitle with 'srt' should return SRT content."""
        items = _make_items()
        result = format_subtitle(items, "srt")
        assert "00:00:00,000 -->" in result
        assert not result.startswith("WEBVTT")

    def test_format_vtt(self) -> None:
        """format_subtitle with 'vtt' should return VTT content."""
        items = _make_items()
        result = format_subtitle(items, "vtt")
        assert result.startswith("WEBVTT")

    def test_format_unknown(self) -> None:
        """Unknown format should raise ValueError."""
        with pytest.raises(ValueError, match="不支持的字幕格式"):
            format_subtitle([], "ass")


class TestWriteSubtitle:
    """Tests for write_subtitle function."""

    def test_write_srt_file(self) -> None:
        """Should write a valid SRT file."""
        items = _make_items()
        with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as f:
            out = Path(f.name)
        try:
            result = write_subtitle(items, out, fmt="srt")
            assert result == out
            assert out.exists()
            content = out.read_text(encoding="utf-8")
            assert "今天天气真好。" in content
            assert "00:00:00,000" in content
        finally:
            out.unlink(missing_ok=True)

    def test_write_vtt_file(self) -> None:
        """Should write a valid VTT file."""
        items = _make_items()
        with tempfile.NamedTemporaryFile(suffix=".vtt", delete=False) as f:
            out = Path(f.name)
        try:
            write_subtitle(items, out, fmt="vtt")
            assert out.exists()
            content = out.read_text(encoding="utf-8")
            assert content.startswith("WEBVTT")
        finally:
            out.unlink(missing_ok=True)
