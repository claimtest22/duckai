"""
Logging helpers. Prefers loguru, falls back to stdlib logging.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Optional


try:
    from loguru import logger as _loguru

    def setup_logging(
        level: str = 'INFO',
        *,
        sink: Any = sys.stderr,
        colorize: bool = True,
        diagnose: bool = False,
    ) -> None:
        _loguru.remove()
        fmt = (
            '<green>{time:HH:mm:ss.SSS}</green> | '
            '<level>{level: <8}</level> | '
            '<cyan>duckai</cyan> | '
            '<level>{message}</level>'
        )
        _loguru.add(
            sink,
            level=level.upper(),
            format=fmt,
            colorize=colorize,
            diagnose=diagnose,
            backtrace=False,
            enqueue=False,
        )

    log = _loguru.opt(depth=1)

except ImportError:
    _std = logging.getLogger('duckai')
    if not _std.handlers:
        _h = logging.StreamHandler(sys.stderr)
        _h.setFormatter(logging.Formatter('%(asctime)s | %(levelname)-8s | duckai | %(message)s'))
        _std.addHandler(_h)
        _std.setLevel(logging.INFO)

    class _StdProxy:
        def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
            _std.debug(msg.format(*args) if args else msg)

        def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
            _std.info(msg.format(*args) if args else msg)

        def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
            _std.warning(msg.format(*args) if args else msg)

        def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
            _std.error(msg.format(*args) if args else msg)

        def opt(self, **kwargs: Any) -> '_StdProxy':
            return self

    log = _StdProxy()

    def setup_logging(
        level: str = 'INFO',
        *,
        sink: Any = sys.stderr,
        colorize: bool = True,
        diagnose: bool = False,
    ) -> None:
        _std.setLevel(getattr(logging, level.upper(), logging.INFO))
