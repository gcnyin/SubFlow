"""Tests for audio extraction (mocked ffmpeg)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from subflow.audio import _count_audio_streams, extract_audio, is_audio_file
from subflow.ffmpeg import check_ffmpeg


class TestIsAudioFile:
    """Tests for audio file detection."""

    def test_audio_extensions(self) -> None:
        """Known audio extensions should return True."""
        for ext in [".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".opus"]:
            assert is_audio_file(Path(f"test{ext}"))

    def test_video_extensions(self) -> None:
        """Video extensions should return False."""
        for ext in [".mp4", ".mkv", ".avi", ".mov", ".webm"]:
            assert not is_audio_file(Path(f"test{ext}"))

    def test_case_insensitive(self) -> None:
        """Extension check should be case-insensitive."""
        assert is_audio_file(Path("podcast.MP3"))
        assert is_audio_file(Path("song.WAV"))


class TestCheckFFmpeg:
    """Tests for ffmpeg availability check."""

    def test_ffmpeg_found(self) -> None:
        """Should not raise when ffmpeg is in PATH."""
        with patch("subflow.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg"):
            check_ffmpeg()  # Should not raise

    def test_ffmpeg_not_found_raises(self) -> None:
        """Should raise RuntimeError with install guide when ffmpeg not found."""
        with (
            patch("subflow.ffmpeg.shutil.which", return_value=None),
            patch("subflow.ffmpeg.get_ffmpeg_path", side_effect=RuntimeError("FFmpeg 未找到。")),
            pytest.raises(RuntimeError, match="FFmpeg 未找到"),
        ):
            check_ffmpeg()

    def test_install_guide_covers_all_platforms(self) -> None:
        """Error message should include install instructions for major platforms."""
        msg = (
            "FFmpeg 未找到。\n"
            "  • Ubuntu/Debian: sudo apt install ffmpeg\n"
            "  • Arch Linux:     sudo pacman -S ffmpeg"
        )
        with (
            patch("subflow.ffmpeg.shutil.which", return_value=None),
            patch("subflow.ffmpeg.get_ffmpeg_path", side_effect=RuntimeError(msg)),
            pytest.raises(RuntimeError, match="Ubuntu"),
        ):
            check_ffmpeg()


class TestCountAudioStreams:
    """Tests for audio stream counting."""

    def test_single_stream(self) -> None:
        """Should return 1 for a single audio stream."""
        mock_result = MagicMock()
        mock_result.stdout = "0\n"
        with patch("subprocess.run", return_value=mock_result):
            assert _count_audio_streams(Path("video.mp4"), "ffprobe") == 1

    def test_multiple_streams(self) -> None:
        """Should count multiple audio streams."""
        mock_result = MagicMock()
        mock_result.stdout = "0\n1\n2\n"
        with patch("subprocess.run", return_value=mock_result):
            assert _count_audio_streams(Path("video.mp4"), "ffprobe") == 3

    def test_no_streams(self) -> None:
        """Should return 0 when no audio streams."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            assert _count_audio_streams(Path("video.mp4"), "ffprobe") == 0


class TestExtractAudio:
    """Tests for audio extraction with mocked ffmpeg."""

    def test_extract_audio_success(self, tmp_path: Path) -> None:
        """Should extract audio successfully when ffmpeg runs fine."""
        output = tmp_path / "test.wav"
        output.write_bytes(b"RIFF...")  # Dummy WAV content

        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch("subflow.audio.check_ffmpeg", return_value="/usr/bin/ffmpeg"),
            patch("subflow.audio._count_audio_streams", return_value=1),
            patch("subprocess.run", return_value=mock_result) as mock_run,
        ):
            result = extract_audio(Path("video.mp4"), output_path=output)

        assert result == output
        mock_run.assert_called()
        cmd = mock_run.call_args[0][0]
        # Check key FFmpeg args
        assert "-ac" in cmd
        assert "1" in cmd
        assert "-ar" in cmd
        assert "16000" in cmd

    def test_extract_audio_ffmpeg_failure(self, tmp_path: Path) -> None:
        """Should raise when ffmpeg returns non-zero."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Invalid data found"

        with (
            patch("subflow.audio.check_ffmpeg", return_value="/usr/bin/ffmpeg"),
            patch("subflow.audio._count_audio_streams", return_value=1),
            patch("subprocess.run", return_value=mock_result),
            pytest.raises(RuntimeError, match="音频提取失败"),
        ):
            extract_audio(Path("video.mp4"), output_path=tmp_path / "out.wav")
