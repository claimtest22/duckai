"""
Custom loguru configuration for the library.
"""

from __future__ import annotations

import sys
from typing import Optional

from loguru import logger


def setup_logging(
    level: str = "INFO",
    *,
    sink=sys.stderr,
    colorize: bool = True,
    diagnose: bool = False,
) -> None:
    """Configure loguru for duckai.

    Parameters
    ----------
    level: str
        Minimum log level.
    sink:
        Output sink.
    colorize: bool
        Enable colors.
    diagnose: bool
        Enable diagnose mode.
    """
    logger.remove()
    fmt = (
        "<green>{time:HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>duckai</cyan> | "
        "<level>{message}</level>"
    )
    logger.add(
        sink,
        level=level.upper(),
        format=fmt,
        colorize=colorize,
        diagnose=diagnose,
        backtrace=False,
        enqueue=False,
    )


log = logger.opt(depth=1)
