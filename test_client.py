"""
Quick smoke test for the static challenge solver + client structure.
Does not require live network if status is blocked.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from duckai.challenge import solve_static
from duckai.utils import sha256_b64, b64json
from duckai.logging import setup_logging, log
from duckai import Client, Model


def test_solver_offline():
    setup_logging("DEBUG")
    challenge_path = Path(__file__).resolve().parent / "vqd_challenge.js"
    if not challenge_path.exists():
        log.warning("no captured challenge, generating synthetic")
        fake = b64json({"server_hashes": ["a", "b"], "client_hashes": [], "signals": {}, "meta": {"v": "4"}})
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        solved = solve_static(fake, ua)
        assert len(solved) > 50
        log.info("synthetic solve ok  len={}", len(solved))
        return

    import base64
    raw = challenge_path.read_text()
    challenge_b64 = base64.b64encode(raw.encode()).decode()
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    solved = solve_static(challenge_b64, ua)
    assert isinstance(solved, str) and len(solved) > 80
    log.info("offline solve ok  len={}", len(solved))
    from duckai.utils import parse_b64json
    payload = parse_b64json(solved)
    assert "server_hashes" in payload
    assert "client_hashes" in payload
    assert len(payload["client_hashes"]) >= 1
    log.info("payload keys ok  client_hashes={}", len(payload["client_hashes"]))


async def test_live():
    setup_logging("INFO")
    try:
        async with Client(model=Model.GPT_4O_MINI, max_retries=3, log_level="INFO") as client:
            log.info("client ready  imp={}", client._http.impersonate)
            result = await client.chat("Reply with exactly the word PONG and nothing else.")
            log.info("response: {}", result.content[:200])
            print("LIVE OK:", result.content[:120])
    except Exception as e:
        log.warning("live test skipped / failed (expected on blocked IPs): {}", e)
        print("LIVE SKIPPED:", type(e).__name__, str(e)[:120])


if __name__ == "__main__":
    test_solver_offline()
    print("---")
    asyncio.run(test_live())
    print("done")
