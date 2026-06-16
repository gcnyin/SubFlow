"""Subtitle burning — embed subtitles into video using FFmpeg."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import time
from pathlib import Path

from subflow.ffmpeg import check_ffmpeg
from subflow.logging import get_logger

logger = get_logger(__name__)

# ── Constants ──

_DEFAULT_FONT_URL_BASE = (
    "https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese"
)
_REQUIRED_FONTS = {
    "NotoSansCJKsc-Regular.otf": _DEFAULT_FONT_URL_BASE + "/NotoSansCJKsc-Regular.otf",
    "NotoSansCJKsc-Bold.otf": _DEFAULT_FONT_URL_BASE + "/NotoSansCJKsc-Bold.otf",
}

# Map user-friendly position names to FFmpeg Alignment values (1-9 grid, 2=bottom-center)
_POSITION_MAP = {"bottom": 2, "top": 8, "middle": 5}

# Map user-friendly color names to #RRGGBB
_COLOR_MAP = {
    "white": "#FFFFFF",
    "black": "#000000",
    "red": "#FF0000",
    "green": "#00FF00",
    "blue": "#0000FF",
    "yellow": "#FFFF00",
    "cyan": "#00FFFF",
    "magenta": "#FF00FF",
    "orange": "#FFA500",
    "gray": "#808080",
    "grey": "#808080",
}


def _resolve_color(color: str) -> str:
    """Resolve a color name or #RRGGBB to the FFmpeg ASS format (&HAABBGGRR)."""
    if color.lower() == "none":
        return ""
    hex_color = _COLOR_MAP.get(color.lower(), color)
    if not hex_color.startswith("#"):
        hex_color = f"#{hex_color}"
    # #RRGGBB → &H00BBGGRR (FFmpeg ASS format, no alpha)
    r, g, b = hex_color[1:3], hex_color[3:5], hex_color[5:7]
    return f"&H00{b}{g}{r}"


def _ensure_fonts(fonts_dir: Path) -> Path:
    """Ensure CJK fonts exist, downloading if necessary.

    Returns the fonts_dir path for use in FFmpeg's fontsdir option.

    Raises:
        RuntimeError: If font download fails with friendly install guide.
    """
    import httpx

    fonts_dir.mkdir(parents=True, exist_ok=True)

    for font_name, url in _REQUIRED_FONTS.items():
        font_path = fonts_dir / font_name
        if font_path.exists():
            continue

        logger.info("Downloading font %s (~16MB)...", font_name)
        try:
            resp = httpx.get(url, follow_redirects=True, timeout=120.0)
            resp.raise_for_status()
            font_path.write_bytes(resp.content)
        except Exception as e:
            raise RuntimeError(
                f"字体下载失败: {font_name}\n"
                f"  错误: {e}\n"
                f"  手动下载: {url}\n"
                f"  放到: {font_path}\n"
                f"  macOS: brew install font-noto-sans-cjk-sc\n"
                f"  Arch:  sudo pacman -S noto-fonts-cjk\n"
                f"  Ubuntu: sudo apt install fonts-noto-cjk"
            ) from e

    return fonts_dir


def _build_force_style(
    font: str | None = None,
    font_size: int = 24,
    font_color: str = "white",
    outline_color: str = "black",
    outline_width: int = 2,
    position: str = "bottom",
    margin: int = 12,
) -> str:
    """Build the FFmpeg force_style string for the subtitles filter."""
    primary = _resolve_color(font_color)
    alignment = _POSITION_MAP.get(position, 2)
    margin_v = margin

    parts = [
        f"FontSize={font_size}",
        f"Alignment={alignment}",
        f"MarginV={margin_v}",
    ]

    if font:
        parts.append(f"FontName={font}")

    if primary:
        parts.append(f"PrimaryColour={primary}")

    if outline_color.lower() != "none" and outline_width > 0:
        outline = _resolve_color(outline_color)
        if outline:
            parts.append(f"OutlineColour={outline}")
        parts.append("BorderStyle=1")
        parts.append(f"Outline={outline_width}")

    return ",".join(parts)


def detect_encoder() -> str:
    """Detect the best available H.264 hardware encoder.

    Returns:
        'h264_nvenc' for NVIDIA, 'h264_vaapi' for AMD on Linux,
        'libx264' as universal CPU fallback.
    """
    # NVIDIA: nvidia-smi available → NVENC
    if shutil.which("nvidia-smi"):
        return "h264_nvenc"

    # AMD on Linux: /dev/dri/render* exists + AMD vendor → VA-API
    if platform.system() == "Linux":
        dri_devices = list(Path("/dev/dri").glob("renderD*"))
        if dri_devices:
            # Check vendor: amdgpu driver loaded or AMD PCI device present
            try:
                vendor = (Path("/sys/class/drm") / dri_devices[0].name / "device" / "vendor")
                vendor_id = vendor.read_text().strip()
                if vendor_id == "0x1002":  # AMD vendor ID
                    return "h264_vaapi"
            except (OSError, FileNotFoundError):
                pass

    return "libx264"


def burn_subtitle(
    video_path: Path,
    subtitle_path: Path,
    output_path: Path,
    font: str | None = None,
    font_size: int = 24,
    font_color: str = "white",
    outline_color: str = "black",
    outline_width: int = 2,
    position: str = "bottom",
    margin: int = 12,
    fonts_dir: str | None = None,
    crf: int = 23,
    ffmpeg: str | None = None,
) -> Path:
    """Burn a subtitle file into a video using FFmpeg.

    Automatically selects the best available encoder:
    NVIDIA → h264_nvenc, AMD Linux → h264_vaapi, fallback → libx264.

    Args:
        video_path: Path to the source video file.
        subtitle_path: Path to the SRT subtitle file.
        output_path: Path for the output video.
        font: Font name or path to .ttf/.otf file. Auto-detect CJK font if None.
        font_size: Font size in pixels.
        font_color: Font color (#RRGGBB or name).
        outline_color: Outline color (#RRGGBB or name, 'none' to disable).
        outline_width: Outline width in pixels.
        position: Subtitle position (bottom/top/middle).
        margin: Bottom margin in pixels.
        fonts_dir: Directory containing font files.
        crf: Constant Rate Factor (quality, lower = better).
        ffmpeg: Explicit path to FFmpeg executable.

    Returns:
        Path to the output video file.

    Raises:
        RuntimeError: If FFmpeg fails or subtitles are unsupported.
    """
    if subtitle_path.suffix.lower() not in (".srt", ".ass"):
        raise RuntimeError(
            f"不支持的字幕格式: {subtitle_path.suffix}\n"
            f"请使用 SRT 格式，或手动用 FFmpeg 处理: "
            f"ffmpeg -i video.mp4 -vf \"subtitles={subtitle_path}\" out.mp4"
        )

    if not video_path.exists():
        raise RuntimeError(f"视频文件不存在: {video_path}")
    if not subtitle_path.exists():
        raise RuntimeError(f"字幕文件不存在: {subtitle_path}")

    ffmpeg_path = check_ffmpeg(ffmpeg)

    # Font setup
    if fonts_dir:
        font_dir_path = Path(fonts_dir)
    else:
        system = platform.system()
        if system == "Windows":
            base = os.environ.get("LOCALAPPDATA", str(Path.home()))
            font_dir_path = Path(base) / "subflow" / "fonts"
        elif system == "Darwin":
            font_dir_path = Path.home() / "Library" / "Caches" / "subflow" / "fonts"
        else:
            xdg = os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))
            font_dir_path = Path(xdg) / "subflow" / "fonts"

    # If no explicit font, ensure default CJK fonts exist
    if font is None:
        _ensure_fonts(font_dir_path)
        font = "Noto Sans CJK SC"

    style = _build_force_style(
        font=font,
        font_size=font_size,
        font_color=font_color,
        outline_color=outline_color,
        outline_width=outline_width,
        position=position,
        margin=margin,
    )

    # Auto-detect best encoder
    encoder = detect_encoder()

    # Build FFmpeg command
    # Use absolute path for subtitle file (FFmpeg subtitles filter needs it)
    sub_abs = subtitle_path.resolve()
    # Escape special characters in the path for the filter string
    sub_escaped = str(sub_abs).replace("\\", "\\\\").replace(":", "\\:")

    vf = f"subtitles={sub_escaped}"
    if style:
        vf += f":force_style='{style}'"

    cmd = [
        ffmpeg_path,
        "-y",
        "-i", str(video_path),
        "-vf", vf,
        "-c:v", encoder,
        "-crf", str(crf),
        "-c:a", "copy",
        "-preset", "medium",
        str(output_path),
    ]

    if fonts_dir:
        # Insert fontsdir before -vf
        idx = cmd.index("-vf")
        cmd.insert(idx, f"-fontsdir={fonts_dir}")

    logger.info(
        "Burning subtitles (encoder: %s): %s -> %s",
        encoder, subtitle_path.name, output_path.name,
    )
    t0 = time.time()

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(f"FFmpeg 烧录失败:\n{stderr[:500]}")

    elapsed = time.time() - t0
    size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info("Done (%.1fs, %.1fMB)", elapsed, size_mb)

    return output_path
