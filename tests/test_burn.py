"""Tests for subtitle burning."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from subflow.burn import (
    _POSITION_MAP,
    _build_force_style,
    _resolve_color,
    burn_subtitle,
)


class TestResolveColor:
    """Tests for color name → FFmpeg ASS format conversion."""

    def test_named_color(self) -> None:
        """Named colors should be converted to ASS format."""
        assert _resolve_color("white") == "&H00FFFFFF"
        assert _resolve_color("black") == "&H00000000"
        assert _resolve_color("red") == "&H000000FF"

    def test_hex_color(self) -> None:
        """#RRGGBB colors should be converted to ASS format."""
        assert _resolve_color("#FF0000") == "&H000000FF"  # red
        assert _resolve_color("#00FF00") == "&H0000FF00"  # green
        assert _resolve_color("#0000FF") == "&H00FF0000"  # blue
        assert _resolve_color("#FFD700") == "&H0000D7FF"  # gold

    def test_none_color(self) -> None:
        """'none' should return empty string."""
        assert _resolve_color("none") == ""


class TestBuildForceStyle:
    """Tests for FFmpeg force_style string construction."""

    def test_default_style(self) -> None:
        """Default parameters should produce basic style."""
        style = _build_force_style()
        assert "FontSize=24" in style
        assert "Alignment=2" in style
        assert "MarginV=12" in style
        assert "PrimaryColour=" in style
        assert "OutlineColour=" in style
        assert "BorderStyle=1" in style
        assert "Outline=2" in style

    def test_custom_font_and_size(self) -> None:
        """Custom font and size should appear in style."""
        style = _build_force_style(font="Arial", font_size=32)
        assert "FontName=Arial" in style
        assert "FontSize=32" in style

    def test_no_outline(self) -> None:
        """When outline is 'none' or width is 0, no border style."""
        style = _build_force_style(outline_color="none", outline_width=0)
        assert "BorderStyle" not in style
        assert "OutlineColour" not in style

    def test_position_map(self) -> None:
        """Position names should map to correct alignment values."""
        assert _POSITION_MAP["bottom"] == 2
        assert _POSITION_MAP["top"] == 8
        assert _POSITION_MAP["middle"] == 5


class TestBurnSubtitle:
    """Tests for the burn_subtitle function (mocked FFmpeg)."""

    def _setup_files(self, tmp_path: Path) -> tuple[Path, Path, Path]:
        """Create dummy video and subtitle files."""
        video = tmp_path / "test.mp4"
        video.write_bytes(b"fake video")
        sub = tmp_path / "test.srt"
        sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
        out = tmp_path / "burned.mp4"
        return video, sub, out

    def test_unsupported_subtitle_format(self, tmp_path: Path) -> None:
        """Non-SRT subtitles should raise an error."""
        vtt = tmp_path / "test.vtt"
        vtt.write_text("WEBVTT\n")
        with pytest.raises(RuntimeError, match="不支持的字幕格式"):
            burn_subtitle(
                video_path=tmp_path / "fake.mp4",
                subtitle_path=vtt,
                output_path=tmp_path / "out.mp4",
                ffmpeg="/fake/ffmpeg",
            )

    def test_missing_video_file(self, tmp_path: Path) -> None:
        """Missing video should raise."""
        sub = tmp_path / "test.srt"
        sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
        with pytest.raises(RuntimeError, match="视频文件不存在"):
            burn_subtitle(
                video_path=tmp_path / "missing.mp4",
                subtitle_path=sub,
                output_path=tmp_path / "out.mp4",
                ffmpeg="/fake/ffmpeg",
            )

    def test_missing_subtitle_file(self, tmp_path: Path) -> None:
        """Missing subtitle should raise."""
        video = tmp_path / "test.mp4"
        video.write_bytes(b"fake")
        with pytest.raises(RuntimeError, match="字幕文件不存在"):
            burn_subtitle(
                video_path=video,
                subtitle_path=tmp_path / "missing.srt",
                output_path=tmp_path / "out.mp4",
                ffmpeg="/fake/ffmpeg",
            )

    def test_successful_burn(self, tmp_path: Path) -> None:
        """Successful FFmpeg run should return output path."""
        video, sub, out = self._setup_files(tmp_path)
        out.write_bytes(b"fake burned video")

        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch("subflow.burn.check_ffmpeg", return_value="/fake/ffmpeg"),
            patch("subflow.burn._ensure_fonts", return_value=tmp_path),
            patch("subprocess.run", return_value=mock_result) as mock_run,
        ):
            result = burn_subtitle(
                video_path=video,
                subtitle_path=sub,
                output_path=out,
                font="Arial",
                ffmpeg="/fake/ffmpeg",
            )

        assert result == out
        mock_run.assert_called()
        cmd = mock_run.call_args[0][0]
        assert "-c:v" in cmd
        assert "-c:a" in cmd
        assert "copy" in cmd
        assert "subtitles=" in " ".join(cmd)

    def test_burn_ffmpeg_failure(self, tmp_path: Path) -> None:
        """Non-zero FFmpeg exit should raise."""
        video, sub, out = self._setup_files(tmp_path)

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Error processing"

        with (
            patch("subflow.burn.check_ffmpeg", return_value="/fake/ffmpeg"),
            patch("subflow.burn._ensure_fonts", return_value=tmp_path),
            patch("subprocess.run", return_value=mock_result),
            pytest.raises(RuntimeError, match="FFmpeg 烧录失败"),
        ):
            burn_subtitle(
                    video_path=video,
                    subtitle_path=sub,
                    output_path=out,
                    ffmpeg="/fake/ffmpeg",
                )
