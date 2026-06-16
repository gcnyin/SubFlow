"""SRT and VTT subtitle formatting and output."""

from pathlib import Path

from subflow.models import SubtitleItem


def _format_timestamp_srt(seconds: float) -> str:
    """Format seconds as SRT timestamp: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _format_timestamp_vtt(seconds: float) -> str:
    """Format seconds as VTT timestamp: HH:MM:SS.mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def to_srt(items: list[SubtitleItem]) -> str:
    """Convert SubtitleItem list to SRT format string.

    SRT format:
        1
        00:00:01,000 --> 00:00:03,000
        Hello world
        <blank line>
    """
    lines: list[str] = []
    for item in items:
        lines.append(str(item.index))
        start_str = _format_timestamp_srt(item.start)
        end_str = _format_timestamp_srt(item.end)
        lines.append(f"{start_str} --> {end_str}")
        lines.append(item.text)
        lines.append("")  # blank separator line
    return "\n".join(lines)


def to_vtt(items: list[SubtitleItem]) -> str:
    """Convert SubtitleItem list to WebVTT format string.

    VTT format:
        WEBVTT

        1
        00:00:01.000 --> 00:00:03.000
        Hello world
        <blank line>
    """
    lines: list[str] = ["WEBVTT", ""]  # header + blank line
    for item in items:
        lines.append(str(item.index))
        start_str = _format_timestamp_vtt(item.start)
        end_str = _format_timestamp_vtt(item.end)
        lines.append(f"{start_str} --> {end_str}")
        lines.append(item.text)
        lines.append("")
    # Ensure trailing blank line (join adds separator between elements,
    # and the final "" gives us the trailing \n)
    result = "\n".join(lines)
    if not result.endswith("\n\n"):
        result += "\n"
    return result


def format_subtitle(items: list[SubtitleItem], fmt: str) -> str:
    """Format subtitle items in the specified format.

    Args:
        items: Subtitle items to format.
        fmt: Format name — 'srt' or 'vtt'.

    Returns:
        Formatted subtitle string.

    Raises:
        ValueError: If format is unsupported.
    """
    if fmt == "srt":
        return to_srt(items)
    if fmt == "vtt":
        return to_vtt(items)
    raise ValueError(f"不支持的字幕格式: {fmt}，可选: srt, vtt")


def write_subtitle(items: list[SubtitleItem], output_path: Path, fmt: str = "srt") -> Path:
    """Format and write subtitle items to a file.

    Args:
        items: Subtitle items.
        output_path: Output file path.
        fmt: Format — 'srt' or 'vtt'.

    Returns:
        The output path.
    """
    content = format_subtitle(items, fmt)
    output_path.write_text(content, encoding="utf-8")
    return output_path
