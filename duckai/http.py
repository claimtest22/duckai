"""
Low-level HTTP session with curl_cffi impersonation rotation.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any, Dict, List, Optional, Sequence

import orjson
from curl_cffi.requests import AsyncSession, Response

from .logging import log
from .errors import HTTPException, RateLimitError, AuthError


IMPERSONATE_POOL: List[str] = [
    "chrome131",
    "chrome124",
    "chrome120",
    "chrome119",
    "chrome116",
    "chrome110",
    "chrome99",
    "chrome131_android",
    "chrome99_android",
    "safari17_0",
    "safari15_5",
]


def _sec_ch_ua_for(impersonate: str) -> str:
    if "android" in impersonate or "chrome" in impersonate:
        ver = "131"
        for token in ("131", "124", "120", "119", "116", "110", "99"):
            if token in impersonate:
                ver = token
                break
        return (
            f'"Chromium";v="{ver}", '
            f'"Google Chrome";v="{ver}", '
            f'"Not_A Brand";v="24"'
        )
    return ""


class HTTPClient:
    """Thin async HTTP wrapper with automatic impersonation rotation."""

    __slots__ = (
        "_session",
        "_impersonate",
        "_proxy",
        "_timeout",
        "_ua",
        "_sec_ch_ua",
        "_headers",
        "_pool",
    )

    def __init__(
        self,
        *,
        impersonate: Optional[str] = None,
        proxy: Optional[str] = None,
        timeout: float = 30.0,
        pool: Optional[Sequence[str]] = None,
    ) -> None:
        self._pool = list(pool or IMPERSONATE_POOL)
        self._impersonate = impersonate or random.choice(self._pool)
        self._proxy = proxy
        self._timeout = timeout
        self._ua = self._ua_for(self._impersonate)
        self._sec_ch_ua = _sec_ch_ua_for(self._impersonate)
        self._headers: Dict[str, str] = {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://duck.ai",
            "Referer": "https://duck.ai/",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        }
        if self._sec_ch_ua:
            self._headers["sec-ch-ua"] = self._sec_ch_ua
            self._headers["sec-ch-ua-mobile"] = (
                "?1" if "android" in self._impersonate else "?0"
            )
            self._headers["sec-ch-ua-platform"] = (
                '"Android"' if "android" in self._impersonate else '"Windows"'
            )
        self._session: Optional[AsyncSession] = None

    @staticmethod
    def _ua_for(impersonate: str) -> str:
        if "android" in impersonate:
            return (
                "Mozilla/5.0 (Linux; Android 16; moto g play - 2026) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Mobile Safari/537.36"
            )
        if "safari" in impersonate:
            return (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.0 Mobile/15E148 Safari/604.1"
            )
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        )

    async def _ensure(self) -> AsyncSession:
        if self._session is None:
            try:
                self._session = AsyncSession(
                    impersonate=self._impersonate,
                    proxy=self._proxy,
                    timeout=self._timeout,
                    headers=self._headers,
                )
            except Exception:
                self.rotate()
                self._session = AsyncSession(
                    impersonate=self._impersonate,
                    proxy=self._proxy,
                    timeout=self._timeout,
                    headers=self._headers,
                )
        return self._session

    def rotate(self) -> None:
        candidates = [p for p in self._pool if p != self._impersonate] or self._pool[:]
        self._impersonate = random.choice(candidates)
        self._ua = self._ua_for(self._impersonate)
        self._sec_ch_ua = _sec_ch_ua_for(self._impersonate)
        self._headers["sec-ch-ua"] = self._sec_ch_ua
        self._headers["sec-ch-ua-mobile"] = (
            "?1" if "android" in self._impersonate else "?0"
        )
        self._headers["sec-ch-ua-platform"] = (
            '"Android"' if "android" in self._impersonate else '"Windows"'
        )
        if self._session is not None:
            try:
                asyncio.get_event_loop().create_task(self._session.close())
            except Exception:
                pass
            self._session = None
        log.debug("rotated impersonate -> {}", self._impersonate)

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

        if resp.status_code == 429:
            raise RateLimitError("rate limited", status=429)
        if resp.status_code == 418:
            raise AuthError("challenge rejected (418)", status=418)
        if resp.status_code >= 400:
            body = resp.text[:300] if resp.text else ""
            raise HTTPException(
                f"HTTP {resp.status_code}: {body}",
                status=resp.status_code,
                payload=body,
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

    async def __aenter__(self) -> "HTTPClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
