"""Configuration management — TOML config file + defaults."""

from __future__ import annotations

import os
import platform
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from subflow.logging import get_logger

logger = get_logger(__name__)


def _default_config_dir() -> Path:
    """Return the platform-appropriate config directory.

    Linux:   ~/.config/subflow/      (XDG)
    macOS:   ~/Library/Application Support/subflow/
    Windows: %APPDATA%\\subflow\
    """
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA", str(Path.home()))
        return Path(base) / "subflow"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "subflow"
    # Linux / XDG
    xdg = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(xdg) / "subflow"


def _default_cache_dir() -> Path:
    """Return the platform-appropriate cache directory.

    Linux:   ~/.cache/subflow/       (XDG)
    macOS:   ~/Library/Caches/subflow/
    Windows: %LOCALAPPDATA%\\subflow\
    """
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("LOCALAPPDATA", str(Path.home()))
        return Path(base) / "subflow"
    if system == "Darwin":
        return Path.home() / "Library" / "Caches" / "subflow"
    # Linux / XDG
    xdg = os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))
    return Path(xdg) / "subflow"


@dataclass
class TranslatorConfig:
    """Configuration for the translation engine.

    API key priority: CLI flag > env SUBFLOW_TRANSLATOR_API_KEY > config file.
    """

    provider: str = "openai"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    api_key: str = ""
    temperature: float = 0.2
    extra_params: dict[str, Any] = field(default_factory=dict)


@dataclass
class BurnConfig:
    """Configuration for subtitle burning (hard subtitles).

    Zero values for font_size / outline_width mean "auto"
    (font_size derived from video height, outline_width from font_size).
    """

    font: str = ""
    font_size: int = 0
    font_color: str = "white"
    outline_color: str = "black"
    outline_width: int = 0
    position: str = "bottom"
    margin: int = 12
    crf: int = 23
    fonts_dir: str = ""


@dataclass
class SubFlowConfig:
    """Configuration for the SubFlow pipeline.

    Values are resolved in priority order: CLI flag > config file > default.
    """

    # Model settings
    model: str = "medium"
    model_dir: str = ""
    device: str = "auto"
    beam_size: int = 5
    language: str | None = None

    # Splitting settings
    max_words_per_line: int = 15
    max_duration_seconds: float = 3.0

    # Output settings
    default_format: str = "srt"
    output: str | None = None
    output_dir: str | None = None

    # Translation settings
    target_langs: list[str] = field(default_factory=list)
    no_source: bool = False
    translator: TranslatorConfig = field(default_factory=TranslatorConfig)

    # Burn settings
    burn: bool = False
    burn_lang: str | None = None
    burn_source: bool = True
    burn_config: BurnConfig = field(default_factory=BurnConfig)

    # Misc
    audio_track: int = 0
    max_duration: float | None = None
    keep_audio: str | None = None
    ffmpeg_path: str | None = None
    dump_json: bool = False
    verbose: int = 0

    # Computed paths (set after config dirs are resolved)
    _config_dir: Path = field(default_factory=_default_config_dir)
    _cache_dir: Path = field(default_factory=_default_cache_dir)

    def __post_init__(self) -> None:
        if not self.model_dir:
            self.model_dir = str(self._cache_dir / "models")

    def model_path(self) -> str:
        """Return the full path to the model directory."""
        return str(Path(self.model_dir).expanduser().resolve())

    def cache_path(self, *parts: str) -> Path:
        """Return a path within the cache directory, creating dirs as needed."""
        p = self._cache_dir.joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def merge_cli(self, **kwargs: Any) -> SubFlowConfig:
        """Return a new config with CLI overrides applied."""
        for key, value in kwargs.items():
            if value is not None and hasattr(self, key):
                setattr(self, key, value)
        return self


def load_config(config_path: str | None = None) -> SubFlowConfig:
    """Load configuration from TOML file, falling back to defaults.

    Priority: CLI flag > environment variable > config file > default.

    Env vars:
        SUBFLOW_TRANSLATOR_API_KEY  — override translator.api_key
        SUBFLOW_TRANSLATOR_BASE_URL — override translator.base_url
        SUBFLOW_TRANSLATOR_MODEL    — override translator.model

    Args:
        config_path: Optional explicit path to config file.

    Returns:
        SubFlowConfig with loaded or default values.
    """
    config = SubFlowConfig()

    if config_path is None:
        config_path = str(_default_config_dir() / "config.toml")

    config_file = Path(config_path).expanduser()

    if config_file.exists():
        try:
            with open(config_file, "rb") as f:
                data = tomllib.load(f)

            if isinstance(data, dict):
                for key, value in data.items():
                    if key == "translator" and isinstance(value, dict):
                        for tk, tv in value.items():
                            if hasattr(config.translator, tk) and tv is not None:
                                setattr(config.translator, tk, tv)
                    elif key == "burn" and isinstance(value, dict):
                        for bk, bv in value.items():
                            if hasattr(config.burn_config, bk) and bv is not None:
                                setattr(config.burn_config, bk, bv)
                    elif hasattr(config, key) and value is not None:
                        setattr(config, key, value)
        except Exception as e:
            logger.warning("配置文件读取失败 (%s): %s，使用默认配置", config_file, e)

    # Environment variable overrides for sensitive translator settings
    for env_var, attr in [
        ("SUBFLOW_TRANSLATOR_API_KEY", "api_key"),
        ("SUBFLOW_TRANSLATOR_BASE_URL", "base_url"),
        ("SUBFLOW_TRANSLATOR_MODEL", "model"),
    ]:
        env_val = os.environ.get(env_var)
        if env_val:
            setattr(config.translator, attr, env_val)

    # Re-resolve model_dir after loading
    config.__post_init__()
    return config
