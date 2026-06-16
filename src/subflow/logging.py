"""Centralized logging configuration for SubFlow."""

from __future__ import annotations

import logging
import sys

# Module-level logger — import and use `logger = get_logger(__name__)` in each module
ROOT_LOGGER = logging.getLogger("subflow")


def get_logger(name: str) -> logging.Logger:
    """Return a child logger of the subflow root logger."""
    return ROOT_LOGGER.getChild(name.rsplit(".", 1)[-1])


def setup_logging(verbose: int = 0) -> None:
    """Configure the root subflow logger based on verbosity level.

    0 (default)  — WARNING and above, no prefix
    1 (-v)       — INFO and above, level prefix
    2+ (-vv)     — DEBUG and above, level+module prefix
    """
    levels = [logging.WARNING, logging.INFO, logging.DEBUG]
    level = levels[min(verbose, len(levels) - 1)]

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)

    if verbose >= 2:
        fmt = "%(levelname)-7s [%(name)s] %(message)s"
    elif verbose == 1:
        fmt = "%(levelname)-7s %(message)s"
    else:
        fmt = "%(message)s"

    handler.setFormatter(logging.Formatter(fmt))
    ROOT_LOGGER.addHandler(handler)
    ROOT_LOGGER.setLevel(level)

    # Suppress noisy third-party loggers unless -vv
    if verbose < 2:
        for name in ("faster_whisper", "huggingface_hub", "httpx", "urllib3"):
            logging.getLogger(name).setLevel(logging.WARNING)
