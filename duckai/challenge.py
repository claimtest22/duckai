"""
Pure-Python VQD hash challenge solver.

Verified against live captures:
  client_hashes[0] = SHA256(user_agent)
  client_hashes[1] = SHA256(dom_score_a)   # e.g. "8471"
  client_hashes[2] = SHA256(dom_score_b)   # e.g. "6878"

Scores are derived from the challenge script constants + a fixed
layout mannequin (offset 24/24) so we never claim webdriver/Selenium.
"""

from __future__ import annotations

import hashlib
import re
import time
from base64 import b64decode, b64encode
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import orjson

from .logging import log


def _sha256_b64(data: str) -> str:
    return b64encode(hashlib.sha256(str(data).encode("utf-8")).digest()).decode("ascii")


def _parse_string_table(script: str) -> List[str]:
    m = re.search(
        r"function\s+_0x[a-f0-9]+\(\)\s*\{\s*const\s+_0x[a-f0-9]+=(\[[\s\S]*?\]);",
        script,
    )
    if not m:
        return []
    try:
        return list(eval(m.group(1)))  # noqa: S307 — controlled challenge source
    except Exception:
        return []


def _parse_server_hashes(script: str) -> List[str]:
    found: List[str] = []
    ret = script[script.rfind("return{") :] if "return{" in script else script

    for h in re.findall(r"'([A-Za-z0-9+/]{40,60}={0,2})'", ret):
        if len(h) >= 40 and h not in found:
            found.append(h)

    # Resolve string-table lookups in the return payload
    table = _parse_string_table(script)
    if table:
        om = re.search(r"_0x[a-f0-9]+=_0x[a-f0-9]+-(0x[0-9a-f]+)", script)
        offset = int(om.group(1), 16) if om else 0
        for m in re.finditer(r"_0x[a-f0-9]+\((0x[0-9a-f]+)\)", ret):
            idx = int(m.group(1), 16) - offset
            if 0 <= idx < len(table):
                val = table[idx]
                if (
                    isinstance(val, str)
                    and len(val) >= 40
                    and re.match(r"^[A-Za-z0-9+/]+={0,2}$", val)
                    and val not in found
                ):
                    found.append(val)

    if len(found) < 2:
        for m in re.finditer(r"[A-Za-z0-9+/]{43,60}={0,2}", script):
            h = m.group(0)
            if h not in found:
                found.append(h)
            if len(found) >= 3:
                break

    return found[:3]


def _parse_meta(script: str) -> Dict[str, str]:
    meta: Dict[str, str] = {
        "v": "4",
        "origin": "https://duck.ai",
        "debug": "HJ",
        "duration": "80",
        "stack": "Error\n    at solve (native)",
    }
    m = re.search(r"'challenge_id':'([^']+)'", script)
    if m:
        meta["challenge_id"] = m.group(1)
    else:
        table = _parse_string_table(script)
        for s in table:
            if isinstance(s, str) and len(s) >= 40 and re.match(r"^[0-9a-f]+", s):
                meta["challenge_id"] = s
                break
    m = re.search(r"'timestamp':'([^']+)'", script)
    if m:
        meta["timestamp"] = m.group(1)
    else:
        table = _parse_string_table(script)
        for s in table:
            if isinstance(s, str) and s.isdigit() and len(s) >= 13:
                meta["timestamp"] = s
                break
        else:
            meta["timestamp"] = str(int(time.time() * 1000))
    return meta


def _layout_scores(script: str) -> Tuple[str, str]:
    """Derive the two DOM mannequin scores embedded in the challenge.

    Live captures used "8471" and "6878". Those come from
    String(BASE + layout) style reductions. We recover candidate
    bases from the script and apply the fixed mannequin layout (48).
    """
    bases: List[int] = []
    for m in re.finditer(r"0x([0-9a-fA-F]+)", script):
        try:
            v = int(m.group(1), 16)
            if 200 <= v <= 30000:
                bases.append(v)
        except ValueError:
            pass
    for m in re.finditer(r"[^a-fA-F0-9]([1-9][0-9]{3,4})[^a-fA-F0-9]", script):
        try:
            v = int(m.group(1))
            if 200 <= v <= 30000:
                bases.append(v)
        except ValueError:
            pass

    layout = 48  # 24+24 mannequin
    scores: List[str] = []
    if bases:
        common = [b for b, _ in Counter(bases).most_common(12)]
        for b in common:
            scores.append(str(b + layout))
            scores.append(str(b))

    # Fallbacks proven against a real browser-solved token
    if "8471" not in scores:
        scores.append("8471")
    if "6878" not in scores:
        scores.append("6878")

    a = scores[0] if scores else "8471"
    b = scores[1] if len(scores) > 1 else "6878"
    return a, b


def solve_static(
    challenge_b64: str,
    user_agent: str,
    *,
    sec_ch_ua: str = "",
    origin: str = "https://duck.ai",
) -> str:
    try:
        script = b64decode(challenge_b64).decode("utf-8", errors="replace")
    except Exception:
        script = ""

    server_hashes = _parse_server_hashes(script)
    meta = _parse_meta(script)
    meta["origin"] = origin

    score_a, score_b = _layout_scores(script)

    # Order verified against browser-captured solved tokens
    client_hashes = [
        _sha256_b64(user_agent),
        _sha256_b64(score_a),
        _sha256_b64(score_b),
    ]

    payload: Dict[str, Any] = {
        "server_hashes": server_hashes,
        "client_hashes": client_hashes,
        "signals": {},
        "meta": meta,
    }

    solved = b64encode(orjson.dumps(payload)).decode("ascii")
    log.debug(
        "pow solved  servers={}  scores={},{}  ua_hash={}  len={}",
        len(server_hashes),
        score_a,
        score_b,
        client_hashes[0][:16],
        len(solved),
    )
    return solved


def solve_from_status(
    headers: Dict[str, str],
    user_agent: str,
    *,
    sec_ch_ua: str = "",
    origin: str = "https://duck.ai",
    prefer_node: bool = False,
) -> Tuple[Optional[str], Optional[str]]:
    h = {k.lower(): v for k, v in headers.items()}
    challenge = h.get("x-vqd-hash-1")
    vqd4 = h.get("x-vqd-4")

    if not challenge:
        return None, vqd4

    return solve_static(
        challenge,
        user_agent,
        sec_ch_ua=sec_ch_ua,
        origin=origin,
    ), vqd4
