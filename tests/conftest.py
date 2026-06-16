"""Shared test fixtures."""

from pathlib import Path

import pytest

from subflow.models import WordTimestamp


@pytest.fixture
def sample_words() -> list[WordTimestamp]:
    """A realistic sequence of word timestamps for testing alignment and formatting."""
    return [
        WordTimestamp("今天", 0.0, 0.3, 0.98),
        WordTimestamp("天气", 0.3, 0.6, 0.95),
        WordTimestamp("真", 0.6, 0.8, 0.92),
        WordTimestamp("好", 0.8, 1.0, 0.97),
        WordTimestamp("。", 1.0, 1.2, 0.5),
        WordTimestamp("我们", 1.5, 1.8, 0.96),
        WordTimestamp("去", 1.8, 2.0, 0.94),
        WordTimestamp("公园", 2.0, 2.3, 0.97),
        WordTimestamp("散步", 2.3, 2.6, 0.95),
        WordTimestamp("吧", 2.6, 2.8, 0.93),
        WordTimestamp("。", 2.8, 3.0, 0.5),
    ]


@pytest.fixture
def test_data_dir() -> Path:
    """Path to test data directory."""
    return Path(__file__).parent / "data"
