"""
Static VQD hash challenge solver.

Pure-Python best-effort reimplementation of the Duck.ai x-vqd-hash-1 challenge.
When the live challenge requires real DOM metrics the static path can fail with
418 ERR_CHALLENGE; callers may inject a browser-captured solved hash instead.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import tempfile
from base64 import b64decode, b64encode
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import orjson

from .logging import log


def _sha256_b64(data: str) -> str:
    return b64encode(hashlib.sha256(data.encode("utf-8")).digest()).decode("ascii")


def _parse_server_hashes(script: str) -> List[str]:
    """Pull server_hashes from the challenge return payload / string table."""
    found: List[str] = []

    ret = script[script.rfind("return{"):] if "return{" in script else script
    for h in re.findall(r"'([A-Za-z0-9+/]{40,60}={0,2})'", ret):
        if h not in found:
            found.append(h)

    if len(found) < 2:
        try:
            part = script.split('server_hashes: ["', maxsplit=1)[1]
            part = part.split('"]', maxsplit=1)[0]
            for h in part.split('","'):
                if h and h not in found:
                    found.append(h)
        except (IndexError, ValueError):
            pass

    if len(found) < 2:
        for m in re.finditer(r"[A-Za-z0-9+/]{40,60}={0,2}", script):
            h = m.group(0)
            if len(h) >= 40 and h not in found:
                found.append(h)
            if len(found) >= 3:
                break

    return found[:3]


def _parse_dom_fingerprint(script: str) -> str:
    """Best-effort DOM fingerprint string."""
    htmlish = re.findall(r"'(<(?:br|div)[^']*>)'", script)
    tmpl = htmlish[0] if htmlish else "<div><div></div><div></div>"
    for base in (101, 0, 128, 3393, 3426, 0x11A0):
        if str(base) in script:
            return str(base + len(tmpl))
    return str(101 + len(tmpl))


def _parse_meta(script: str) -> Dict[str, str]:
    meta: Dict[str, str] = {"v": "4"}
    m = re.search(r"'challenge_id':'([^']+)'", script)
    if m:
        meta["challenge_id"] = m.group(1)
    m = re.search(r"'timestamp':'([^']+)'", script)
    if m:
        meta["timestamp"] = m.group(1)
    return meta


def solve_static(
    challenge_b64: str,
    user_agent: str,
    *,
    sec_ch_ua: str = "",
    origin: str = "https://duckduckgo.com",
) -> str:
    """Solve the x-vqd-hash-1 challenge with a pure-Python approximation."""
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
    meta = _parse_meta(script)
    if meta:
        meta.setdefault("origin", origin)
        payload["meta"] = meta

    solved = b64encode(orjson.dumps(payload)).decode("ascii")
    log.debug(
        "static solve  servers={}  dom={}  len={}",
        len(server_hashes),
        dom_fp,
        len(solved),
    )
    return solved


def solve_with_node(challenge_b64: str, user_agent: str) -> Optional[str]:
    """Execute the challenge in Node.js when available."""
    try:
        script = b64decode(challenge_b64).decode("utf-8", errors="replace")
    except Exception:
        return None

    wrapper = f"""
global.navigator = {{
  userAgent: {user_agent!r},
  webdriver: false,
  userAgentData: {{ brands: [] }},
}};
global.document = {{
  createElement: () => ({{
    style: {{}},
    innerHTML: '',
    textContent: '',
    offsetHeight: 1,
    offsetWidth: 1,
    getBoundingClientRect: () => ({{ width: 1, height: 1, top: 0, left: 0 }}),
    appendChild: () => {{}},
    removeChild: () => {{}},
  }}),
  body: {{ appendChild: () => {{}}, removeChild: () => {{}} }},
  documentElement: {{}},
}};
global.window = global;
global.self = global;
global.Promise = Promise;
(async () => {{
  const result = await ({script});
  if (result && result.client_hashes) {{
    const crypto = require('crypto');
    result.client_hashes = result.client_hashes.map((v) => {{
      if (typeof v === 'string' && v.length > 20 && v.endsWith('=')) return v;
      return crypto.createHash('sha256').update(String(v)).digest('base64');
    }});
  }}
  process.stdout.write(Buffer.from(JSON.stringify(result)).toString('base64'));
}})().catch((e) => {{ console.error(e); process.exit(1); }});
"""
    try:
        proc = subprocess.run(
            ["node", "-e", wrapper],
            capture_output=True,
            timeout=8,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout:
            out = proc.stdout.decode("ascii", errors="ignore").strip()
            if out:
                log.debug("node solve ok len={}", len(out))
                return out
        log.debug("node solve failed: {}", proc.stderr[:200] if proc.stderr else "")
    except FileNotFoundError:
        log.debug("node not available")
    except Exception as e:
        log.debug("node solve error: {}", e)
    return None


def solve_from_status(
    headers: Dict[str, str],
    user_agent: str,
    *,
    sec_ch_ua: str = "",
    origin: str = "https://duckduckgo.com",
    prefer_node: bool = True,
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

    solved: Optional[str] = None
    if prefer_node:
        solved = solve_with_node(challenge, user_agent)
    if not solved:
        solved = solve_static(
            challenge,
            user_agent,
            sec_ch_ua=sec_ch_ua,
            origin=origin,
        )
    return solved, vqd4
