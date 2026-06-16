"""Tests for configuration loading."""

import tempfile
from pathlib import Path

from subflow.config import SubFlowConfig, load_config


class TestSubFlowConfig:
    """Tests for SubFlowConfig defaults and merging."""

    def test_default_values(self) -> None:
        """Config should have sensible defaults."""
        config = SubFlowConfig()
        assert config.model == "medium"
        assert config.default_format == "srt"
        assert config.beam_size == 5
        assert config.max_words_per_line == 15
        assert config.max_duration_seconds == 3.0
        assert config.device == "auto"
        assert config.language is None

    def test_merge_cli_overrides(self) -> None:
        """CLI overrides should take precedence over defaults."""
        config = SubFlowConfig()
        config.merge_cli(
            model="large-v3",
            language="zh",
            default_format="vtt",
            beam_size=10,
        )
        assert config.model == "large-v3"
        assert config.language == "zh"
        assert config.default_format == "vtt"
        assert config.beam_size == 10
        # Unchanged defaults
        assert config.max_words_per_line == 15

    def test_merge_ignores_none(self) -> None:
        """None values should not override existing config."""
        config = SubFlowConfig()
        config.merge_cli(language=None, output=None)
        assert config.language is None  # stays as default
        assert config.output is None

    def test_model_path(self) -> None:
        """model_path should resolve to a sensible path."""
        config = SubFlowConfig()
        path = config.model_path()
        assert "subflow" in path
        assert "models" in path


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_defaults_when_no_file(self) -> None:
        """Should return defaults when config file doesn't exist."""
        config = load_config("/nonexistent/path/config.toml")
        assert config.model == "medium"

    def test_load_from_file(self) -> None:
        """Should load values from a valid TOML file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".toml", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                'model = "large-v3"\n'
                'default_format = "vtt"\n'
                'max_words_per_line = 20\n'
            )
            f.flush()
            config = load_config(f.name)

        try:
            assert config.model == "large-v3"
            assert config.default_format == "vtt"
            assert config.max_words_per_line == 20
            # Unset keys remain at defaults
            assert config.beam_size == 5
        finally:
            Path(f.name).unlink(missing_ok=True)

    def test_load_malformed_file(self) -> None:
        """Malformed TOML should fall back to defaults with a warning."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".toml", delete=False, encoding="utf-8"
        ) as f:
            f.write("this is not valid toml {{{")
            f.flush()
            config = load_config(f.name)

        try:
            # Should fall back to defaults
            assert config.model == "medium"
        finally:
            Path(f.name).unlink(missing_ok=True)
