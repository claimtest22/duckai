"""VQD hash challenge solver via Node vm sandbox."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple

import orjson

from .logging import log

_SOLVER_JS = Path(__file__).resolve().parent / "solver.js"
_NODE = shutil.which("node") or shutil.which("nodejs")


def _solve_sync(challenge_b64: str, user_agent: str) -> str:
    if not _NODE:
        raise RuntimeError("node binary not found — install node to solve duck.ai challenges")
    if not _SOLVER_JS.is_file():
        raise RuntimeError(f"solver.js missing at {_SOLVER_JS}")

    payload = orjson.dumps({"challenge": challenge_b64, "user_agent": user_agent})
    proc = subprocess.run(
        [_NODE, str(_SOLVER_JS)],
        input=payload,
        capture_output=True,
        timeout=15,
        env=dict(os.environ),
    )
    out = proc.stdout or b""
    err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
    if proc.returncode != 0 and not out:
        raise RuntimeError(f"node solver failed rc={proc.returncode} err={err[:300]}")

    try:
        data = orjson.loads(out)
    except Exception as exc:
        raise RuntimeError(f"node solver bad json: {out[:200]!r} err={err[:200]}") from exc

    if not data.get("ok") or not data.get("hash"):
        raise RuntimeError(f"node solver error: {data.get('error') or err or 'unknown'}")

    log.debug("challenge solved len={}", len(data["hash"]))
    return str(data["hash"])


async def solve_static(challenge_b64: str, user_agent: str, **_: object) -> str:
    return await asyncio.to_thread(_solve_sync, challenge_b64, user_agent)


async def solve_from_status(
    headers: Dict[str, str],
    user_agent: str,
    **_: object,
) -> Tuple[Optional[str], Optional[str]]:
    h = {k.lower(): v for k, v in headers.items()}
    challenge = h.get("x-vqd-hash-1")
    vqd4 = h.get("x-vqd-4")
    if not challenge:
        return None, vqd4
    solved = await solve_static(challenge, user_agent)
    return solved, vqd4
