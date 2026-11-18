"""
High-level Duck.ai client.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator, Dict, List, Optional, Sequence, Union

import orjson

from .challenge import solve_from_status, solve_static
from .enums import Model
from .errors import (
    AuthError,
    ChallengeError,
    DuckAIException,
    HTTPException,
    RateLimitError,
)
from .http import HTTPClient, IMPERSONATE_POOL
from .logging import log, setup_logging
from .models import ChatResult, Message, ModelInfo, StreamChunk


STATUS_URL = "https://duckduckgo.com/duckchat/v1/status"
CHAT_URL = "https://duckduckgo.com/duckchat/v1/chat"
MODELS_URL = "https://duckduckgo.com/duckchat/v1/models"


class Client:
    """Async client for Duck.ai (DuckDuckGo AI Chat).

    Parameters
    ----------
    impersonate: str | None
        Preferred curl_cffi impersonation target.
    proxy: str | None
        Optional proxy URL.
    model: str | Model
        Default model.
    max_retries: int
        How many times to refresh challenge / rotate on failure.
    log_level: str
        Loguru level.
    """

    __slots__ = (
        "_http",
        "_model",
        "_vqd4",
        "_hash1",
        "_max_retries",
        "_history",
        "_lock",
        "_last_refresh",
    )

    def __init__(
        self,
        *,
        impersonate: Optional[str] = None,
        proxy: Optional[str] = None,
        model: Union[str, Model] = Model.GPT_4O_MINI,
        max_retries: int = 6,
        log_level: str = "INFO",
        pool: Optional[Sequence[str]] = None,
    ) -> None:
        setup_logging(log_level)
        self._http = HTTPClient(
            impersonate=impersonate,
            proxy=proxy,
            pool=pool or IMPERSONATE_POOL,
        )
        self._model = str(model)
        self._vqd4: Optional[str] = None
        self._hash1: Optional[str] = None
        self._max_retries = max_retries
        self._history: List[Dict[str, str]] = []
        self._lock = asyncio.Lock()
        self._last_refresh = 0.0

    @property
    def model(self) -> str:
        return self._model

    @model.setter
    def model(self, value: Union[str, Model]) -> None:
        self._model = str(value)

    @property
    def history(self) -> List[Dict[str, str]]:
        return list(self._history)

    def clear_history(self) -> None:
        self._history.clear()

    async def _refresh_tokens(self, force: bool = False) -> None:
        """Fetch status and solve challenge."""
        now = time.monotonic()
        if not force and self._hash1 and (now - self._last_refresh) < 30:
            return

        async with self._lock:
            now = time.monotonic()
            if not force and self._hash1 and (now - self._last_refresh) < 30:
                return

            for attempt in range(1, self._max_retries + 1):
                try:
                    resp = await self._http.get(
                        STATUS_URL,
                        headers={"x-vqd-accept": "1"},
                    )
                    headers = dict(resp.headers)
                    solved, vqd4 = solve_from_status(
                        headers,
                        self._http.user_agent,
                    )
                    if not solved:
                        raise ChallengeError("no x-vqd-hash-1 in status response")

                    self._hash1 = solved
                    if vqd4:
                        self._vqd4 = vqd4
                    self._last_refresh = time.monotonic()
                    log.info(
                        "tokens refreshed  imp={}  vqd4={}  hash_len={}",
                        self._http.impersonate,
                        bool(self._vqd4),
                        len(self._hash1),
                    )
                    return
                except (AuthError, ChallengeError, HTTPException, RateLimitError) as e:
                    log.warning("refresh attempt {} failed: {}", attempt, e)
                    self._http.rotate()
                    await asyncio.sleep(0.3 * attempt)
                except Exception as e:
                    log.warning("refresh unexpected: {}", e)
                    self._http.rotate()
                    await asyncio.sleep(0.5 * attempt)

            raise ChallengeError("failed to obtain valid VQD tokens after retries")

    def _chat_headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            "x-vqd-hash-1": self._hash1 or "",
        }
        if self._vqd4:
            h["x-vqd-4"] = self._vqd4
        return h

    async def _ensure_ready(self) -> None:
        if not self._hash1:
            await self._refresh_tokens(force=True)

    async def models(self) -> List[ModelInfo]:
        """Return the list of currently available models."""
        await self._ensure_ready()
        resp = await self._http.get(MODELS_URL, headers=self._chat_headers())
        data = orjson.loads(resp.content)
        out: List[ModelInfo] = []
        for item in data if isinstance(data, list) else data.get("models", []):
            out.append(
                ModelInfo(
                    model=item.get("model", ""),
                    model_name=item.get("modelName", ""),
                    input_char_limit=str(item.get("inputCharLimit", "")),
                    created_by=item.get("createdBy", ""),
                    is_open_source=bool(item.get("isOpenSource", False)),
                    raw=item,
                )
            )
        return out

    async def chat(
        self,
        content: str,
        *,
        model: Optional[Union[str, Model]] = None,
        history: bool = True,
    ) -> ChatResult:
        """Send a message and return the full response.

        Parameters
        ----------
        content: str
            User message.
        model: str | Model | None
            Override default model.
        history: bool
            Whether to keep conversation history.
        """
        await self._ensure_ready()
        model_s = str(model or self._model)

        messages = list(self._history) if history else []
        messages.append({"role": "user", "content": content})

        body = {
            "model": model_s,
            "messages": messages,
        }

        last_err: Optional[Exception] = None
        for attempt in range(1, self._max_retries + 1):
            try:
                resp = await self._http.post(
                    CHAT_URL,
                    headers=self._chat_headers(),
                    json=body,
                )
                new_vqd = resp.headers.get("x-vqd-4") or resp.headers.get("X-Vqd-4")
                if new_vqd:
                    self._vqd4 = new_vqd

                text = self._parse_sse(resp.content)
                if history:
                    self._history.append({"role": "user", "content": content})
                    self._history.append({"role": "assistant", "content": text})

                return ChatResult(
                    content=text,
                    model=model_s,
                    vqd=self._vqd4,
                )
            except AuthError as e:
                last_err = e
                log.warning("chat auth fail attempt {} — refreshing", attempt)
                await self._refresh_tokens(force=True)
                self._http.rotate()
            except RateLimitError as e:
                last_err = e
                log.warning("rate limited, rotating + sleep")
                self._http.rotate()
                await asyncio.sleep(1.5 * attempt)
            except HTTPException as e:
                last_err = e
                log.warning("http error attempt {}: {}", attempt, e)
                self._http.rotate()
                await asyncio.sleep(0.4 * attempt)

        raise DuckAIException(f"chat failed after retries: {last_err}")

    async def stream(
        self,
        content: str,
        *,
        model: Optional[Union[str, Model]] = None,
        history: bool = True,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a response as SSE chunks."""
        await self._ensure_ready()
        model_s = str(model or self._model)

        messages = list(self._history) if history else []
        messages.append({"role": "user", "content": content})

        body = {
            "model": model_s,
            "messages": messages,
        }

        for attempt in range(1, self._max_retries + 1):
            try:
                resp = await self._http.post(
                    CHAT_URL,
                    headers=self._chat_headers(),
                    json=body,
                )
                new_vqd = resp.headers.get("x-vqd-4") or resp.headers.get("X-Vqd-4")
                if new_vqd:
                    self._vqd4 = new_vqd

                full: List[str] = []
                async for chunk in self._iter_sse(resp):
                    if chunk.content:
                        full.append(chunk.content)
                    yield chunk

                if history and full:
                    self._history.append({"role": "user", "content": content})
                    self._history.append({"role": "assistant", "content": "".join(full)})
                return
            except AuthError:
                log.warning("stream auth fail — refresh")
                await self._refresh_tokens(force=True)
                self._http.rotate()
            except RateLimitError:
                self._http.rotate()
                await asyncio.sleep(1.2 * attempt)
            except Exception as e:
                log.warning("stream error: {}", e)
                self._http.rotate()
                await asyncio.sleep(0.4 * attempt)

        raise DuckAIException("stream failed after retries")

    def _parse_sse(self, raw: bytes) -> str:
        """Parse a full SSE body into a single string."""
        text = raw.decode("utf-8", errors="replace")
        parts: List[str] = []
        for line in text.splitlines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                obj = orjson.loads(data)
                if isinstance(obj, dict):
                    msg = obj.get("message") or obj.get("content") or ""
                    if msg:
                        parts.append(str(msg))
            except Exception:
                if data and not data.startswith("{"):
                    parts.append(data)
        return "".join(parts)

    async def _iter_sse(self, resp: Any) -> AsyncIterator[StreamChunk]:
        """Yield StreamChunk from response content (already buffered by curl_cffi)."""
        text = resp.content.decode("utf-8", errors="replace")
        for line in text.splitlines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                yield StreamChunk(done=True, vqd=self._vqd4)
                return
            if not data:
                continue
            try:
                obj = orjson.loads(data)
                msg = ""
                if isinstance(obj, dict):
                    msg = str(obj.get("message") or obj.get("content") or "")
                yield StreamChunk(content=msg, model=self._model, vqd=self._vqd4, raw=obj)
            except Exception:
                yield StreamChunk(content=data, vqd=self._vqd4)

    async def close(self) -> None:
        await self._http.close()

    async def __aenter__(self) -> "Client":
        await self._ensure_ready()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
