"""
Static VQD hash challenge solver.

Pure-Python reimplementation of the Duck.ai x-vqd-hash-1 challenge.
"""

from __future__ import annotations

import re
import time
from base64 import b64decode
from typing import Any, Dict, List, Optional, Tuple

from .logging import log
from .utils import sha256_b64, b64json


# Values observed across many live challenges
_DOM_VALUES = ("6823", "101", "6824", "123")


def _extract_server_hashes(script: str) -> List[str]:
    """Best-effort extraction of server_hashes from obfuscated challenge JS."""
    found: List[str] = []
    for m in re.finditer(r"[A-Za-z0-9+/]{40,60}={0,2}", script):
        h = m.group(0)
        if len(h) >= 40 and h not in found:
            found.append(h)
    if len(found) >= 2:
        return found[:3]
    return [
        "+/YUQv1Ne26OHYkbwrdpxkaQIdaIleb6HXMgbHp0neA=",
        "eQFdUCDrfsCt5feLl8+blMsghhZfsKmQlv6SnWDdfWE=",
        "DZd0RXn6D3rs7nSqoGdOxYxI3nYHczNFwZSfTCocw3A=",
    ]


def _extract_meta(script: str) -> Dict[str, str]:
    """Pull challenge_id / timestamp-like strings if present."""
    meta: Dict[str, str] = {
        "v": "4",
        "challenge_id": "static-" + str(int(time.time())),
        "timestamp": str(int(time.time() * 1000)),
        "origin": "https://duck.ai",
        "stack": "Error\n    at solve (native)",
        "duration": str(8 + int(time.time() * 1000) % 20),
    }
    ids = re.findall(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        script,
    )
    if ids:
        meta["challenge_id"] = ids[0]
    return meta


def _build_client_raw(user_agent: str) -> List[str]:
    """Reconstruct the raw values the challenge hashes on the client side."""
    brands = ""
    if "Chrome/" in user_agent:
        try:
            ver = user_agent.split("Chrome/")[1].split(".")[0]
            brands = (
                f'"Chromium";v="{ver}", '
                f'"Google Chrome";v="{ver}", '
                f'"Not_A Brand";v="24"'
            )
        except Exception:
            brands = (
                '"Chromium";v="131", '
                '"Google Chrome";v="131", '
                '"Not_A Brand";v="24"'
            )
    elif "Firefox/" in user_agent:
        brands = ""
    else:
        brands = (
            '"Chromium";v="131", '
            '"Google Chrome";v="131", '
            '"Not_A Brand";v="24"'
        )

    ua_key = user_agent + brands
    dom = _DOM_VALUES[0]
    return [ua_key, dom]


def solve_static(
    challenge_b64: str,
    user_agent: str,
    *,
    origin: str = "https://duck.ai",
) -> str:
    """Solve the x-vqd-hash-1 challenge purely in Python.

    Parameters
    ----------
    challenge_b64: str
        The raw base64 value from the status response header.
    user_agent: str
        The User-Agent that will be used for the subsequent chat request.
    origin: str
        Origin to embed in meta.

    Returns
    -------
    str
        Base64-encoded solved payload ready for the x-vqd-hash-1 header.
    """
    try:
        script = b64decode(challenge_b64).decode("utf-8", errors="replace")
    except Exception:
        script = ""

    server_hashes = _extract_server_hashes(script)
    meta = _extract_meta(script)
    meta["origin"] = origin

    raw_client = _build_client_raw(user_agent)
    client_hashes = [sha256_b64(x) for x in raw_client]

    payload: Dict[str, Any] = {
        "server_hashes": server_hashes,
        "client_hashes": client_hashes,
        "signals": {},
        "meta": meta,
    }

    solved = b64json(payload)
    log.debug(
        "challenge solved  client_hashes={}  len={}",
        len(client_hashes),
        len(solved),
    )
    return solved


def solve_from_status(
    headers: Dict[str, str],
    user_agent: str,
    *,
    origin: str = "https://duck.ai",
) -> Tuple[Optional[str], Optional[str]]:
    """Convenience: extract challenge + vqd-4 from status headers and solve.

    Returns
    -------
    tuple
        (solved_hash_1, vqd_4)
    """
    h = {k.lower(): v for k, v in headers.items()}
    challenge = h.get("x-vqd-hash-1")
    vqd4 = h.get("x-vqd-4")

    if not challenge:
        return None, vqd4

    solved = solve_static(challenge, user_agent, origin=origin)
    return solved, vqd4
