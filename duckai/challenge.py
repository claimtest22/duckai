"""
VQD hash challenge solver.

Runs the obfuscated duck.ai challenge script inside a Node.js vm sandbox
and returns the base64 payload for the x-vqd-hash-1 header.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple

import orjson

from .logging import log


_SOLVER_JS = Path(__file__).resolve().parent / 'solver.js'
_NODE = shutil.which('node') or shutil.which('nodejs')


def solve_static(
    challenge_b64: str,
    user_agent: str,
    *,
    origin: str = 'https://duck.ai',
    sec_ch_ua: Optional[str] = None,
) -> str:
    """Solve the x-vqd-hash-1 challenge via Node vm.

    Parameters
    ----------
    challenge_b64:
        Raw base64 challenge from the status response header.
    user_agent:
        User-Agent string that will be sent on the subsequent chat request.
    origin:
        Origin embedded in the solved meta payload.
    sec_ch_ua:
        Optional sec-ch-ua brands string (unused by node solver, kept for API compat).
    """
    if not _NODE:
        raise RuntimeError('node binary not found — install node to solve duck.ai challenges')
    if not _SOLVER_JS.is_file():
        raise RuntimeError(f'solver.js missing at {_SOLVER_JS}')

    payload = orjson.dumps(
        {
            'challenge': challenge_b64,
            'user_agent': user_agent,
            'origin': origin,
            'sec_ch_ua': sec_ch_ua or '',
        }
    )
    env = dict(os.environ)
    proc = subprocess.run(
        [_NODE, str(_SOLVER_JS)],
        input=payload,
        capture_output=True,
        timeout=12,
        env=env,
    )
    out = proc.stdout or b''
    err = (proc.stderr or b'').decode('utf-8', errors='replace').strip()
    if proc.returncode != 0 and not out:
        raise RuntimeError(f'node solver failed rc={proc.returncode} err={err[:300]}')

    try:
        data = orjson.loads(out)
    except Exception as exc:
        raise RuntimeError(f'node solver bad json: {out[:200]!r} err={err[:200]}') from exc

    if not data.get('ok') or not data.get('hash'):
        raise RuntimeError(f'node solver error: {data.get("error") or err or "unknown"}')

    solved = str(data['hash'])
    log.debug('challenge solved len={} origin={}', len(solved), origin)
    return solved


def solve_from_status(
    headers: Dict[str, str],
    user_agent: str,
    *,
    origin: str = 'https://duck.ai',
    sec_ch_ua: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Extract challenge + vqd-4 from status headers and solve.

    Returns
    -------
    tuple
        ``(solved_hash_1, vqd_4)``
    """
    h = {k.lower(): v for k, v in headers.items()}
    challenge = h.get('x-vqd-hash-1')
    vqd4 = h.get('x-vqd-4')
    if not challenge:
        return None, vqd4
    solved = solve_static(
        challenge,
        user_agent,
        origin=origin,
        sec_ch_ua=sec_ch_ua,
    )
    return solved, vqd4
