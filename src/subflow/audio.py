"""Audio extraction from video files using FFmpeg."""

import subprocess
import tempfile
from pathlib import Path

from subflow.ffmpeg import check_ffmpeg
from subflow.logging import get_logger

logger = get_logger(__name__)


def _count_audio_streams(filepath: Path, ffmpeg_path: str = "ffprobe") -> int:
    """Return the number of audio streams in a media file."""
    # Use ffprobe from same directory as ffmpeg
    ffprobe = str(Path(ffmpeg_path).parent / "ffprobe") if ffmpeg_path != "ffprobe" else "ffprobe"
    result = subprocess.run(
        [
            ffprobe,
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
    ffmpeg: str | None = None,
) -> Path:
    """Extract audio from a media file as 16kHz mono WAV.

    Args:
        filepath: Path to the media file (video or audio).
        output_path: Optional output path. If None, a temp file is created.
        audio_track: Index of the audio stream to extract (default 0).
        ffmpeg: Explicit path to ffmpeg executable.

    Returns:
        Path to the extracted audio file.

    Raises:
        RuntimeError: If ffmpeg is not installed or extraction fails.
    """
    ffmpeg_path = check_ffmpeg(ffmpeg)

    stream_count = _count_audio_streams(filepath, ffmpeg_path)
    if stream_count == 0:
        raise RuntimeError(f"文件中未找到音轨: {filepath}")
    if stream_count > 1 and audio_track == 0:
        logger.warning(
            "检测到 %d 条音轨，默认使用音轨 0。使用 --audio-track 切换。",
            stream_count,
        )

    if output_path is None:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            output_path = Path(tmp.name)

    # FFmpeg command: extract audio, resample to 16kHz mono, output PCM WAV
    cmd = [
        ffmpeg_path,
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
