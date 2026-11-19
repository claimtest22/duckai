"""
Low-level HTTP session with curl_cffi impersonation.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any, Dict, List, Optional, Sequence

import orjson
from curl_cffi.requests import AsyncSession, Response

from .logging import log
from .errors import HTTPException, RateLimitError, AuthError, BanLimitError


IMPERSONATE_POOL: List[str] = [
    "chrome131",
    "chrome124",
    "chrome120",
    "chrome131_android",
    "chrome99_android",
]

UA_FOR_IMPERSONATE: Dict[str, str] = {
    "chrome131_android": (
        "Mozilla/5.0 (Linux; Android 14; Pixel 7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Mobile Safari/537.36"
    ),
    "chrome99_android": (
        "Mozilla/5.0 (Linux; Android 12; Pixel 5) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/99.0.4844.88 Mobile Safari/537.36"
    ),
    "chrome131": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "chrome124": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "chrome120": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


def _sec_ch_ua_for(impersonate: str) -> str:
    ver = "131"
    for token in ("131", "124", "120", "116", "110", "99"):
        if token in impersonate:
            ver = token
            break
    return (
        f'"Chromium";v="{ver}", '
        f'"Google Chrome";v="{ver}", '
        f'"Not_A Brand";v="24"'
    )


class HTTPClient:
    """Async HTTP wrapper. UA always matches impersonate profile."""

    __slots__ = (
        "_session",
        "_impersonate",
        "_proxy",
        "_timeout",
        "_ua",
        "_sec_ch_ua",
        "_headers",
        "_pool",
        "_fixed_ua",
    )

    def __init__(
        self,
        *,
        impersonate: Optional[str] = None,
        proxy: Optional[str] = None,
        timeout: float = 30.0,
        pool: Optional[Sequence[str]] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        self._pool = list(pool or IMPERSONATE_POOL)
        self._impersonate = impersonate or "chrome131"
        if self._impersonate not in self._pool:
            self._pool.insert(0, self._impersonate)
        self._proxy = proxy
        self._timeout = timeout
        self._fixed_ua = user_agent
        self._ua = user_agent or UA_FOR_IMPERSONATE.get(
            self._impersonate,
            UA_FOR_IMPERSONATE["chrome131"],
        )
        self._sec_ch_ua = _sec_ch_ua_for(self._impersonate)
        mobile = "android" in self._impersonate
        self._headers: Dict[str, str] = {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://duck.ai",
            "Referer": "https://duck.ai/",
            "sec-ch-ua": self._sec_ch_ua,
            "sec-ch-ua-mobile": "?1" if mobile else "?0",
            "sec-ch-ua-platform": '"Android"' if mobile else '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        }
        self._session: Optional[AsyncSession] = None

    async def _ensure(self) -> AsyncSession:
        if self._session is None:
            try:
                self._session = AsyncSession(
                    impersonate=self._impersonate,
                    proxy=self._proxy,
                    timeout=self._timeout,
                )
            except Exception as e:
                log.warning("impersonate {} failed: {} — rotating", self._impersonate, e)
                self.rotate()
                self._session = AsyncSession(
                    impersonate=self._impersonate,
                    proxy=self._proxy,
                    timeout=self._timeout,
                )
        return self._session

    def rotate(self) -> None:
        if self._fixed_ua:
            candidates = [p for p in self._pool if p != self._impersonate] or self._pool[:]
            self._impersonate = random.choice(candidates)
            log.debug("rotated impersonate -> {} (UA pinned)", self._impersonate)
        else:
            candidates = [p for p in self._pool if p != self._impersonate] or self._pool[:]
            self._impersonate = random.choice(candidates)
            self._ua = UA_FOR_IMPERSONATE.get(
                self._impersonate,
                UA_FOR_IMPERSONATE["chrome131"],
            )
            self._sec_ch_ua = _sec_ch_ua_for(self._impersonate)
            mobile = "android" in self._impersonate
            self._headers["sec-ch-ua"] = self._sec_ch_ua
            self._headers["sec-ch-ua-mobile"] = "?1" if mobile else "?0"
            self._headers["sec-ch-ua-platform"] = (
                '"Android"' if mobile else '"Windows"'
            )
            log.debug("rotated impersonate -> {}", self._impersonate)

        if self._session is not None:
            try:
                asyncio.get_event_loop().create_task(self._session.close())
            except Exception:
                pass
            self._session = None

    @property
    def user_agent(self) -> str:
        return self._ua

    @property
    def sec_ch_ua(self) -> str:
        return self._sec_ch_ua

    @property
    def impersonate(self) -> str:
        return self._impersonate

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        json: Any = None,
        data: Any = None,
        params: Any = None,
    ) -> Response:
        session = await self._ensure()
        hdrs = dict(self._headers)
        hdrs["User-Agent"] = self._ua
        if headers:
            hdrs.update(headers)
        hdrs["User-Agent"] = self._ua

        kwargs: Dict[str, Any] = {"headers": hdrs, "params": params}
        if json is not None:
            kwargs["data"] = orjson.dumps(json)
            hdrs["Content-Type"] = "application/json"
        elif data is not None:
            kwargs["data"] = data

        try:
            resp = await session.request(method, url, **kwargs)
        except Exception as e:
            msg = str(e)
            log.warning("request error {} {} -> {}", method, url, msg)
            if "not supported" in msg.lower() or "impersonat" in msg.lower():
                self.rotate()
            raise HTTPException(msg) from e

        body = ""
        try:
            body = resp.text or ""
        except Exception:
            body = ""
        if resp.status_code == 429:
            raise RateLimitError("rate limited", status=429, payload=body[:300])
        if resp.status_code == 418 or "ERR_BN_LIMIT" in body or "unsupported entrypoint" in body:
            if "ERR_BN_LIMIT" in body or "unsupported entrypoint" in body:
                log.warning("BN_LIMIT body: {}", body[:220])
                raise BanLimitError(
                    "IP / entrypoint blocked (ERR_BN_LIMIT)",
                    status=resp.status_code or 418,
                    payload=body[:400],
                )
            log.warning("418 body: {}", body[:220])
            raise AuthError(
                f"challenge rejected (418): {body[:180]}",
                status=418,
                payload=body[:400],
            )
        if resp.status_code >= 400:
            raise HTTPException(
                f"HTTP {resp.status_code}: {body[:300]}",
                status=resp.status_code,
                payload=body[:300],
            )
        return resp

    async def get(self, url: str, **kwargs: Any) -> Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> Response:
        return await self.request("POST", url, **kwargs)

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
