"""
High-level Duck.ai client.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from base64 import b64encode
from typing import Any, AsyncIterator, Dict, List, Optional, Sequence, Union

import orjson

from .challenge import solve_from_status
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
from .models import ChatResult, ModelInfo, StreamChunk


BASE = "https://duck.ai"
STATUS_URL = f"{BASE}/duckchat/v1/status"
CHAT_URL = f"{BASE}/duckchat/v1/chat"
MODELS_URL = f"{BASE}/duckchat/v1/models"
AUTH_URL = f"{BASE}/duckchat/v1/auth/token"
CAPABILITIES_URL = f"{BASE}/duckchat/v1/capabilities"

FE_VERSION = "serp_20261117_201536_ET-1fa5b033293521d7ce8eee3f19c13def14a59cf5"


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
    system: str | None
        Optional system prompt (prepended into first user message).
    max_retries: int
        How many times to refresh challenge / rotate on failure.
    log_level: str
        Loguru level.
    """

    __slots__ = (
        "_http",
        "_model",
        "_system",
        "_vqd4",
        "_hash1",
        "_max_retries",
        "_history",
        "_lock",
        "_last_refresh",
        "_journey",
        "_conversation_id",
    )

    def __init__(
        self,
        *,
        impersonate: Optional[str] = None,
        proxy: Optional[str] = None,
        model: Union[str, Model] = Model.GPT_6_LUNA,
        system: Optional[str] = None,
        max_retries: int = 6,
        log_level: str = "INFO",
        pool: Optional[Sequence[str]] = None,
    ) -> None:
        setup_logging(log_level)
        self._http = HTTPClient(
            impersonate=impersonate,
            proxy=proxy,
            pool=pool or IMPERSONATE_POOL,
            origin=BASE,
        )
        self._model = str(model)
        self._system = system
        self._vqd4: Optional[str] = None
        self._hash1: Optional[str] = None
        self._max_retries = max_retries
        self._history: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._last_refresh = 0.0
        self._journey = uuid.uuid4().hex
        self._conversation_id = str(uuid.uuid4())

    @property
    def model(self) -> str:
        return self._model

    @model.setter
    def model(self, value: Union[str, Model]) -> None:
        self._model = str(value)

    @property
    def system(self) -> Optional[str]:
        return self._system

    @system.setter
    def system(self, value: Optional[str]) -> None:
        self._system = value

    @property
    def history(self) -> List[Dict[str, Any]]:
        return list(self._history)

    def clear_history(self) -> None:
        self._history.clear()
        self._conversation_id = str(uuid.uuid4())

    def new_session(self) -> None:
        """Reset guest session (usage limit / memory boundary)."""
        self.clear_history()
        self._journey = uuid.uuid4().hex
        self._hash1 = None
        self._vqd4 = None
        self._last_refresh = 0.0
        log.info("guest session reset")

    @staticmethod
    def _text_content(text: str) -> List[Dict[str, str]]:
        return [{"type": "text", "text": text}]

    def _build_messages(
        self,
        content: str,
        *,
        history: bool,
        system: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        if history:
            messages.extend(self._history)

        sys_prompt = system if system is not None else self._system
        user_text = content
        if sys_prompt and not messages:
            user_text = f"{sys_prompt.strip()}\n\n{content}"

        messages.append({"role": "user", "content": self._text_content(user_text)})
        return messages

    def _fe_signals(self) -> str:
        now = int(time.time() * 1000)
        payload = {
            "start": now - 2000,
            "events": [
                {"name": "startNewChat_free", "delta": 400},
                {"name": "action", "delta": 1200, "trusted": True},
            ],
            "end": 2500,
        }
        return b64encode(orjson.dumps(payload)).decode("ascii")

    async def _refresh_tokens(self, force: bool = False) -> None:
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
                        headers={
                            "x-vqd-accept": "1",
                            "Accept": "*/*",
                            "cache-control": "no-store",
                            "x-ddg-journey-id": self._journey,
                        },
                    )
                    headers = dict(resp.headers)
                    solved, vqd4 = solve_from_status(
                        headers,
                        self._http.user_agent,
                        sec_ch_ua=self._http.sec_ch_ua,
                        origin=BASE,
                    )
                    if not solved and not vqd4:
                        raise ChallengeError("no x-vqd-hash-1 or x-vqd-4 in status")

                    if solved:
                        self._hash1 = solved
                    if vqd4:
                        self._vqd4 = vqd4
                    self._last_refresh = time.monotonic()
                    log.info(
                        "tokens refreshed  imp={}  vqd4={}  hash_len={}",
                        self._http.impersonate,
                        bool(self._vqd4),
                        len(self._hash1 or ""),
                    )
                    return
                except (AuthError, ChallengeError, HTTPException, RateLimitError) as e:
                    log.warning("refresh attempt {} failed: {}", attempt, e)
                    self._http.rotate()
                    await asyncio.sleep(0.4 * attempt)
                except Exception as e:
                    log.warning("refresh unexpected: {}", e)
                    self._http.rotate()
                    await asyncio.sleep(0.5 * attempt)

            raise ChallengeError("failed to obtain valid VQD tokens after retries")

    def _chat_headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            "x-ddg-journey-id": self._journey,
            "x-fe-version": FE_VERSION,
            "x-fe-signals": self._fe_signals(),
            "x-duckai-consent-purposes": "user-location,image-generation,web-search",
        }
        if self._hash1:
            h["x-vqd-hash-1"] = self._hash1
        if self._vqd4:
            h["x-vqd-4"] = self._vqd4
        return h

    async def _ensure_ready(self) -> None:
        if not self._hash1 and not self._vqd4:
            await self._refresh_tokens(force=True)

    async def models(self) -> List[ModelInfo]:
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
        system: Optional[str] = None,
        history: bool = True,
    ) -> ChatResult:
        """Send a message and return the full response."""
        await self._ensure_ready()
        model_s = str(model or self._model)

        messages = self._build_messages(content, history=history, system=system)
        body: Dict[str, Any] = {
            "model": model_s,
            "messages": messages,
            "canUseTools": True,
            "reasoningEffort": "none",
            "canShowGreeting": False,
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

                # usage / guest limit signals in SSE
                if "ERR_USAGE" in (resp.content.decode("utf-8", errors="ignore")):
                    log.warning("usage limit hit — resetting guest session")
                    self.new_session()
                    await self._refresh_tokens(force=True)
                    continue

                if history:
                    self._history.append(
                        {"role": "user", "content": self._text_content(content)}
                    )
                    self._history.append(
                        {"role": "assistant", "content": self._text_content(text)}
                    )

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
                if getattr(e, "status", None) in (400, 418):
                    await self._refresh_tokens(force=True)
                self._http.rotate()
                await asyncio.sleep(0.4 * attempt)

        raise DuckAIException(f"chat failed after retries: {last_err}")

    async def stream(
        self,
        content: str,
        *,
        model: Optional[Union[str, Model]] = None,
        system: Optional[str] = None,
        history: bool = True,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a response as SSE chunks."""
        await self._ensure_ready()
        model_s = str(model or self._model)

        messages = self._build_messages(content, history=history, system=system)
        body: Dict[str, Any] = {
            "model": model_s,
            "messages": messages,
            "canUseTools": True,
            "reasoningEffort": "none",
            "canShowGreeting": False,
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
                    self._history.append(
                        {"role": "user", "content": self._text_content(content)}
                    )
                    self._history.append(
                        {
                            "role": "assistant",
                            "content": self._text_content("".join(full)),
                        }
                    )
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
                    if obj.get("action") == "error":
                        raise HTTPException(
                            f"SSE error: {obj.get('type') or obj}",
                            status=int(obj.get("status") or 400),
                            payload=str(obj),
                        )
                    msg = obj.get("message") or obj.get("content") or ""
                    if isinstance(msg, list):
                        msg = "".join(
                            b.get("text", "") if isinstance(b, dict) else str(b)
                            for b in msg
                        )
                    if msg:
                        parts.append(str(msg))
            except HTTPException:
                raise
            except Exception:
                if data and not data.startswith("{"):
                    parts.append(data)
        return "".join(parts)

    async def _iter_sse(self, resp: Any) -> AsyncIterator[StreamChunk]:
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
                    raw_msg = obj.get("message") or obj.get("content") or ""
                    if isinstance(raw_msg, list):
                        msg = "".join(
                            b.get("text", "") if isinstance(b, dict) else str(b)
                            for b in raw_msg
                        )
                    else:
                        msg = str(raw_msg)
                yield StreamChunk(
                    content=msg, model=self._model, vqd=self._vqd4, raw=obj
                )
            except Exception:
                yield StreamChunk(content=data, vqd=self._vqd4)

    async def close(self) -> None:
        await self._http.close()

    async def __aenter__(self) -> "Client":
        await self._ensure_ready()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
