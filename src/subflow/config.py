"""Configuration management — TOML config file + defaults."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _default_config_dir() -> Path:
    """Return the default config directory: ~/.config/subflow/"""
    xdg_config = Path.home() / ".config" / "subflow"
    return xdg_config


def _default_cache_dir() -> Path:
    """Return the default cache directory: ~/.cache/subflow/"""
    xdg_cache = Path.home() / ".cache" / "subflow"
    return xdg_cache


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

    # Misc
    audio_track: int = 0
    max_duration: float | None = None
    keep_audio: str | None = None
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

    Looks for config at:
    1. Explicit config_path argument
    2. ~/.config/subflow/config.toml
    3. Defaults if neither exists

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
                    if hasattr(config, key) and value is not None:
                        setattr(config, key, value)
        except Exception as e:
            print(f"⚠  配置文件读取失败 ({config_file}): {e}，使用默认配置")

    # Re-resolve model_dir after loading
    config.__post_init__()
    return config
