"""FFmpeg discovery — system PATH, env var, config, and bundled fallback."""

from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import tarfile
from pathlib import Path

import httpx

from subflow.logging import get_logger

logger = get_logger(__name__)

# ── Bundled FFmpeg download ──

_BASE_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest"

_PLATFORM_ARCHIVE: dict[str, str] = {
    "linux-x86_64": "ffmpeg-master-latest-linux64-gpl.tar.xz",
    "linux-aarch64": "ffmpeg-master-latest-linuxarm64-gpl.tar.xz",
    "win32-amd64": "ffmpeg-master-latest-win64-gpl.zip",
    "darwin-x86_64": "ffmpeg-master-latest-macos64-gpl.tar.xz",
    "darwin-arm64": "ffmpeg-master-latest-macos64-gpl.tar.xz",
}


def _platform_key() -> str:
    """Return the platform key for FFmpeg download (e.g. 'linux-x86_64')."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    # Normalize: Python returns 'windows' but BtbN uses 'win32'
    if system == "windows":
        system = "win32"
    if machine in ("x86_64", "amd64"):
        arch = "x86_64"
    elif machine in ("aarch64", "arm64"):
        arch = "arm64"
    else:
        arch = "x86_64"  # best-effort fallback
    return f"{system}-{arch}"


def _ensure_bundled_ffmpeg(cache_dir: Path) -> Path:
    """Download bundled FFmpeg to cache_dir if not present.

    Returns the path to the ffmpeg executable.

    Raises:
        RuntimeError: If download fails.
    """
    is_windows = platform.system() == "Windows"
    exe_name = "ffmpeg.exe" if is_windows else "ffmpeg"
    ffmpeg_path = cache_dir / exe_name
    if ffmpeg_path.exists():
        return ffmpeg_path

    key = _platform_key()
    archive_name = _PLATFORM_ARCHIVE.get(key)
    if archive_name is None:
        raise RuntimeError(f"不支持的平台: {key}，请手动安装 FFmpeg")

    url = f"{_BASE_URL}/{archive_name}"
    logger.info("下载 FFmpeg 中 (~80MB)...")
    logger.info("来源: %s", url)

    cache_dir.mkdir(parents=True, exist_ok=True)

    # Download to temp file
    tmp_path = cache_dir / f"{archive_name}.tmp"
    try:
        try:
            with httpx.stream("GET", url, follow_redirects=True, timeout=300.0) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0))
                downloaded = 0
                with open(tmp_path, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=1024 * 1024):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = downloaded / total * 100
                            mb = downloaded / (1024 * 1024)
                            print(f"\r   {mb:.0f}MB ({pct:.0f}%)", end="", flush=True)  # noqa: T201
                print()  # newline after progress

            # Extract ffmpeg binary from archive
            logger.info("解压中...")
            if archive_name.endswith(".tar.xz"):
                with tarfile.open(tmp_path) as tar:
                    for member in tar.getmembers():
                        if member.name.endswith("/ffmpeg") and member.isfile():
                            tar.extract(member, path=cache_dir, filter="data")
                            extracted = cache_dir / member.name
                            extracted.rename(ffmpeg_path)
                            break
                    else:
                        raise RuntimeError("FFmpeg 压缩包中未找到 ffmpeg 可执行文件")
            else:
                raise RuntimeError(f"不支持的压缩格式: {archive_name}")

            # Make executable (Unix only; Windows doesn't need this)
            if not is_windows:
                ffmpeg_path.chmod(ffmpeg_path.stat().st_mode | stat.S_IEXEC)
            logger.info("FFmpeg 就绪: %s", ffmpeg_path)

        except Exception as e:
            raise RuntimeError(
                f"FFmpeg 下载失败: {e}\n"
                f"  请手动安装 FFmpeg：\n"
                f"  • Ubuntu/Debian: sudo apt install ffmpeg\n"
                f"  • Arch Linux:     sudo pacman -S ffmpeg\n"
                f"  • Fedora:         sudo dnf install ffmpeg\n"
                f"  • macOS:          brew install ffmpeg\n"
                f"  或手动下载 ffmpeg 放到: {ffmpeg_path}"
            ) from e

    finally:
        tmp_path.unlink(missing_ok=True)

    return ffmpeg_path


def get_ffmpeg_path(
    ffmpeg_path: str | None = None,
    cache_dir: Path | None = None,
) -> str:
    """Resolve the path to the FFmpeg executable.

    Priority:
        1. Explicit path argument
        2. SUBFLOW_FFMPEG_PATH env var
        3. System PATH (shutil.which)
        4. Bundled download in cache_dir

    Args:
        ffmpeg_path: Explicit path from config/CLI.
        cache_dir: Cache directory for bundled download.

    Returns:
        Path to the FFmpeg executable.

    Raises:
        RuntimeError: If FFmpeg cannot be found or downloaded.
    """
    # 1. Explicit path
    if ffmpeg_path:
        p = Path(ffmpeg_path).expanduser()
        if p.exists():
            return str(p.resolve())
        raise RuntimeError(f"指定的 FFmpeg 路径不存在: {ffmpeg_path}")

    # 2. Environment variable
    env_path = os.environ.get("SUBFLOW_FFMPEG_PATH")
    if env_path:
        p = Path(env_path).expanduser()
        if p.exists():
            return str(p.resolve())

    # 3. System PATH
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    # 4. Bundled download
    if cache_dir is None:
        system = platform.system()
        if system == "Windows":
            base = os.environ.get("LOCALAPPDATA", str(Path.home()))
            cache_dir = Path(base) / "subflow"
        elif system == "Darwin":
            cache_dir = Path.home() / "Library" / "Caches" / "subflow"
        else:
            xdg = os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))
            cache_dir = Path(xdg) / "subflow"

    try:
        return str(_ensure_bundled_ffmpeg(cache_dir))
    except Exception as e:
        raise RuntimeError(
            "FFmpeg 未找到。\n"
            "  安装方法:\n"
            "  • Ubuntu/Debian: sudo apt install ffmpeg\n"
            "  • Arch Linux:     sudo pacman -S ffmpeg\n"
            "  • Fedora:         sudo dnf install ffmpeg\n"
            "  • macOS:          brew install ffmpeg\n"
            "  • Windows:        winget install ffmpeg\n"
            f"\n自动下载也失败了: {e}"
        ) from e


def check_ffmpeg(ffmpeg_path: str | None = None) -> str:
    """Verify FFmpeg works by checking version. Returns the resolved path.

    Raises RuntimeError with install guide if FFmpeg is unavailable.
    """
    path = get_ffmpeg_path(ffmpeg_path)
    result = subprocess.run(
        [path, "-version"], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg 可执行但异常: {result.stderr.strip()}")
    return path
