"""
VQD hash challenge solver.

Primary path: Node.js + jsdom (ships solver.js) — executes the real challenge.
Fallback: pure-Python static approximation (often 418 on current PoW).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
from base64 import b64decode, b64encode
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import orjson

from .logging import log

_SOLVER_JS = Path(__file__).resolve().parent / "solver.js"


def _sha256_b64(data: str) -> str:
    return b64encode(hashlib.sha256(str(data).encode("utf-8")).digest()).decode(
        "ascii"
    )


def _parse_server_hashes(script: str) -> List[str]:
    found: List[str] = []
    ret = script[script.rfind("return{") :] if "return{" in script else script
    for h in re.findall(r"'([A-Za-z0-9+/]{40,60}={0,2})'", ret):
        if len(h) >= 40 and h not in found:
            found.append(h)
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
    m = re.search(r"'timestamp':'([^']+)'", script)
    if m:
        meta["timestamp"] = m.group(1)
    else:
        meta["timestamp"] = str(int(time.time() * 1000))
    return meta


def solve_with_node(challenge_b64: str, user_agent: str) -> Optional[str]:
    """Execute challenge via Node + jsdom (solver.js)."""
    if not shutil.which("node"):
        log.debug("node not on PATH")
        return None
    if not _SOLVER_JS.is_file():
        log.debug("solver.js missing at {}", _SOLVER_JS)
        return None

    try:
        script = b64decode(challenge_b64)
    except Exception:
        return None

    try:
        with tempfile.NamedTemporaryFile(suffix=".js", delete=False) as tmp:
            tmp.write(script)
            tmp_path = tmp.name
        try:
            proc = subprocess.run(
                ["node", str(_SOLVER_JS), tmp_path, user_agent],
                capture_output=True,
                timeout=12,
                check=False,
            )
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass

        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or b"").decode("utf-8", "replace")[:300]
            log.debug("node solver rc={} err={}", proc.returncode, err)
            return None

        raw = proc.stdout.decode("utf-8", "replace").strip()
        result = json.loads(raw)
        if result.get("__error"):
            log.debug("node solver error: {}", result["__error"][:200])
            return None
        if not isinstance(result.get("client_hashes"), list):
            log.debug("node solver bad shape")
            return None

        hashed = [_sha256_b64(x) for x in result["client_hashes"]]
        meta = dict(result.get("meta") or {})
        meta.setdefault("origin", "https://duck.ai")
        meta.setdefault("stack", "Error\n    at solve (native)")
        meta.setdefault("duration", "15")

        payload: Dict[str, Any] = {
            "server_hashes": result.get("server_hashes") or [],
            "client_hashes": hashed,
            "signals": result.get("signals") or {},
            "meta": meta,
        }
        solved = b64encode(orjson.dumps(payload)).decode("ascii")
        log.debug(
            "node pow ok  raw={}  servers={}  len={}",
            result["client_hashes"][1:3] if len(result["client_hashes"]) > 1 else [],
            len(payload["server_hashes"]),
            len(solved),
        )
        return solved
    except FileNotFoundError:
        return None
    except Exception as e:
        log.debug("node solver exception: {}", e)
        return None


def solve_static(
    challenge_b64: str,
    user_agent: str,
    *,
    sec_ch_ua: str = "",
    origin: str = "https://duck.ai",
) -> str:
    """Best-effort pure Python (often rejected by current PoW)."""
    try:
        script = b64decode(challenge_b64).decode("utf-8", errors="replace")
    except Exception:
        script = ""

    server_hashes = _parse_server_hashes(script)
    meta = _parse_meta(script)
    meta["origin"] = origin

    # Verified shape: [UA, score_a, score_b] then SHA-256 each
    client_hashes = [
        _sha256_b64(user_agent),
        _sha256_b64("2733"),
        _sha256_b64("4169"),
    ]

    payload: Dict[str, Any] = {
        "server_hashes": server_hashes,
        "client_hashes": client_hashes,
        "signals": {},
        "meta": meta,
    }
    return b64encode(orjson.dumps(payload)).decode("ascii")


def solve_from_status(
    headers: Dict[str, str],
    user_agent: str,
    *,
    sec_ch_ua: str = "",
    origin: str = "https://duck.ai",
    prefer_node: bool = True,
) -> Tuple[Optional[str], Optional[str]]:
    h = {k.lower(): v for k, v in headers.items()}
    challenge = h.get("x-vqd-hash-1")
    vqd4 = h.get("x-vqd-4")

    if not challenge:
        return None, vqd4

    if prefer_node:
        solved = solve_with_node(challenge, user_agent)
        if solved:
            return solved, vqd4

    return (
        solve_static(
            challenge, user_agent, sec_ch_ua=sec_ch_ua, origin=origin
        ),
        vqd4,
    )
