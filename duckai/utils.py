"""
Utility helpers.
"""

from __future__ import annotations

import hashlib
import time
from base64 import b64encode, b64decode
from typing import Any, Dict, List, Optional

import orjson


def sha256_b64(data: str | bytes) -> str:
    """Return base64-encoded SHA-256 digest."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return b64encode(hashlib.sha256(data).digest()).decode("ascii")


def b64json(obj: Any) -> str:
    """Serialize with orjson and base64 encode."""
    return b64encode(orjson.dumps(obj)).decode("ascii")


def parse_b64json(data: str) -> Any:
    """Decode base64 then orjson."""
    return orjson.loads(b64decode(data))


def now_ms() -> int:
    return int(time.time() * 1000)


def build_ua_brands(ua: str) -> str:
    """Build a realistic sec-ch-ua brands string from a UA."""
    if "Chrome/" in ua:
        try:
            ver = ua.split("Chrome/")[1].split(".")[0]
            return f'"Chromium";v="{ver}", "Google Chrome";v="{ver}", "Not_A Brand";v="24"'
        except Exception:
            pass
    return '"Chromium";v="131", "Google Chrome";v="131", "Not_A Brand";v="24"'
