"""Core data models for SubFlow subtitle pipeline."""

from dataclasses import dataclass, field


@dataclass
class WordTimestamp:
    """A single word with its time boundaries and confidence."""

    word: str
    start: float  # start time in seconds
    end: float  # end time in seconds
    probability: float = 1.0


@dataclass
class SubtitleItem:
    """A single subtitle entry with index, time range, text, and word-level data."""

    index: int  # 1-based SRT index
    start: float  # start time in seconds
    end: float  # end time in seconds
    text: str  # subtitle text for this entry
    words: list[WordTimestamp] = field(default_factory=list)
