"""Audio extraction from video files using FFmpeg."""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _check_ffmpeg() -> None:
    """Verify ffmpeg is installed and accessible. Raises RuntimeError with install guide if not."""
    if shutil.which("ffmpeg") is not None:
        return

    guide_lines = [
        "FFmpeg 未找到。请安装 FFmpeg：",
        "  • Ubuntu/Debian: sudo apt install ffmpeg",
        "  • Arch Linux:     sudo pacman -S ffmpeg",
        "  • Fedora:         sudo dnf install ffmpeg",
        "  • macOS:          brew install ffmpeg",
        "  • Windows:        winget install ffmpeg  或访问 https://ffmpeg.org/download.html",
    ]
    raise RuntimeError("\n".join(guide_lines))


def _count_audio_streams(filepath: Path) -> int:
    """Return the number of audio streams in a media file."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=index",
            "-of", "csv=p=0",
            str(filepath),
        ],
        capture_output=True,
        text=True,
    )
    lines = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
    return len(lines)


def is_audio_file(filepath: Path) -> bool:
    """Check if the file extension indicates an audio-only format."""
    audio_extensions = {".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".opus", ".wma"}
    return filepath.suffix.lower() in audio_extensions


def extract_audio(
    filepath: Path,
    output_path: Path | None = None,
    audio_track: int = 0,
) -> Path:
    """Extract audio from a media file as 16kHz mono WAV.

    Args:
        filepath: Path to the media file (video or audio).
        output_path: Optional output path. If None, a temp file is created.
        audio_track: Index of the audio stream to extract (default 0).

    Returns:
        Path to the extracted audio file.

    Raises:
        RuntimeError: If ffmpeg is not installed or extraction fails.
    """
    _check_ffmpeg()

    stream_count = _count_audio_streams(filepath)
    if stream_count == 0:
        raise RuntimeError(f"文件中未找到音轨: {filepath}")
    if stream_count > 1 and audio_track == 0:
        print(
            f"⚠  检测到 {stream_count} 条音轨，默认使用音轨 0。"
            f"使用 --audio-track 1 切换。",
            file=sys.stderr,
        )

    if output_path is None:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            output_path = Path(tmp.name)

    # FFmpeg command: extract audio, resample to 16kHz mono, output PCM WAV
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(filepath),
        "-map", f"0:a:{audio_track}",
        "-ac", "1",  # mono
        "-ar", "16000",  # 16kHz
        "-sample_fmt", "s16",  # 16-bit PCM
        "-f", "wav",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        output_path.unlink(missing_ok=True)
        raise RuntimeError(f"音频提取失败:\n{result.stderr.strip()}")

    return output_path
