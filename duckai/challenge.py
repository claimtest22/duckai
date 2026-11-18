"""
Static VQD hash challenge solver.

Pure-Python reimplementation of the Duck.ai x-vqd-hash-1 challenge.
"""

from __future__ import annotations

import hashlib
import re
from base64 import b64decode, b64encode
from typing import Any, Dict, List, Optional, Tuple

import orjson

from .logging import log


def _sha256_b64(data: str) -> str:
    digest = hashlib.sha256(data.encode("utf-8")).digest()
    return b64encode(digest).decode("ascii")


def _parse_server_hashes(js_text: str) -> List[str]:
    """Extract server_hashes array from challenge JS."""
    try:
        part = js_text.split('server_hashes: ["', maxsplit=1)[1]
        part = part.split('"]', maxsplit=1)[0]
        return [h for h in part.split('","') if h]
    except (IndexError, ValueError):
        pass

    found: List[str] = []
    for m in re.finditer(r"[A-Za-z0-9+/]{40,60}={0,2}", js_text):
        h = m.group(0)
        if len(h) >= 40 and h not in found:
            found.append(h)
        if len(found) >= 3:
            break
    return found[:3] if found else []


def _parse_dom_fingerprint(js_text: str) -> str:
    """Reconstruct the DOM fingerprint string the challenge hashes.

    The challenge does roughly:
        const e = document.createElement('div');
        e.innerHTML = '<div><div></div><div></div';
        return String(BASE + e.innerHTML.length);
    """
    # Common hardcoded bases observed in live challenges
    for base in (101, 3393, 3426, 0x11A0, 6823, 6824, 123):
        # innerHTML length of '<div><div></div><div></div' is ~27-28 depending on trailing
        for length in (27, 28, 23, 24, 31):
            candidate = str(base + length)
            if candidate in js_text or str(base) in js_text:
                return candidate

    # Try to pull numeric literals near createElement / innerHTML
    nums = re.findall(r"(?:String\()?(\d{2,5})\s*\+", js_text)
    if nums:
        try:
            base = int(nums[0])
            return str(base + 27)
        except ValueError:
            pass

    return "128"  # safe fallback seen in some static solvers


def solve_static(
    challenge_b64: str,
    user_agent: str,
    *,
    sec_ch_ua: str = "",
    origin: str = "https://duckduckgo.com",
) -> str:
    """Solve the x-vqd-hash-1 challenge purely in Python.

    Parameters
    ----------
    challenge_b64: str
        The raw base64 value from the status response header.
    user_agent: str
        The User-Agent that will be used for the subsequent chat request.
    sec_ch_ua: str
        Optional sec-ch-ua header value (brands string).
    origin: str
        Origin embedded in meta (unused by newest challenges but kept).

    Returns
    -------
    str
        Base64-encoded solved payload ready for the x-vqd-hash-1 header.
    """
    try:
        script = b64decode(challenge_b64).decode("utf-8", errors="replace")
    except Exception:
        script = ""

    server_hashes = _parse_server_hashes(script)
    dom_fp = _parse_dom_fingerprint(script)

    ua_fp = user_agent + (sec_ch_ua or "")
    client_hashes = [
        _sha256_b64(ua_fp),
        _sha256_b64(dom_fp),
    ]

    payload: Dict[str, Any] = {
        "server_hashes": server_hashes,
        "client_hashes": client_hashes,
        "signals": {},
    }

    solved = b64encode(orjson.dumps(payload)).decode("ascii")
    log.debug(
        "challenge solved  servers={}  clients={}  dom={}  len={}",
        len(server_hashes),
        len(client_hashes),
        dom_fp,
        len(solved),
    )
    return solved


def solve_from_status(
    headers: Dict[str, str],
    user_agent: str,
    *,
    sec_ch_ua: str = "",
    origin: str = "https://duckduckgo.com",
) -> Tuple[Optional[str], Optional[str]]:
    """Extract challenge + vqd-4 from status headers and solve.

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

    solved = solve_static(
        challenge,
        user_agent,
        sec_ch_ua=sec_ch_ua,
        origin=origin,
    )
    return solved, vqd4
