"""
High-level Duck.ai client.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from base64 import b64encode, urlsafe_b64encode
from typing import Any, AsyncIterator, Dict, List, Optional, Sequence, Union

import orjson

from .challenge import solve_from_status
from .enums import Model
from .errors import (
    AuthError,
    BanLimitError,
    ChallengeError,
    DuckAIException,
    HTTPException,
    RateLimitError,
)
from .http import HTTPClient, IMPERSONATE_POOL
from .logging import log, setup_logging
from .models import ChatResult, StreamChunk


BASE = "https://duck.ai"
STATUS_URL = f"{BASE}/duckchat/v1/status"
CHAT_URL = f"{BASE}/duckchat/v1/chat"
MODELS_URL = f"{BASE}/duckchat/v1/models"
CAPABILITIES_URL = f"{BASE}/duckchat/v1/capabilities"
AUTH_TOKEN_URL = f"{BASE}/duckchat/v1/auth/token"
COUNTRY_URL = f"{BASE}/country.json"


def _b64url_int(n: int) -> str:
    length = (n.bit_length() + 7) // 8
    return urlsafe_b64encode(n.to_bytes(length, "big")).rstrip(b"=").decode("ascii")


def make_durable_stream(conversation_id: str) -> Dict[str, Any]:
    """
    Exact shape the live frontend sends (Nov 2026 capture):

    {
      "messageId": "<uuid>",
      "conversationId": "<uuid>",
      "publicKey": {
        "alg": "RSA-OAEP-256",
        "e": "AQAB",
        "ext": true,
        "key_ops": ["encrypt"],
        "kty": "RSA",
        "n": "<base64url modulus>",
        "use": "enc"
      }
    }
    """
    try:
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend

        priv = rsa.generate_private_key(
            public_exponent=65537, key_size=2048, backend=default_backend()
        )
        nums = priv.public_key().public_numbers()
        public_key = {
            "alg": "RSA-OAEP-256",
            "e": _b64url_int(nums.e),
            "ext": True,
            "key_ops": ["encrypt"],
            "kty": "RSA",
            "n": _b64url_int(nums.n),
            "use": "enc",
        }
    except Exception:
        public_key = {
            "alg": "RSA-OAEP-256",
            "e": "AQAB",
            "ext": True,
            "key_ops": ["encrypt"],
            "kty": "RSA",
            "n": (
                "oOF1zWL1dy752wuJMUveQ74NE_AmTYteY87GOTsx80VntjZkDz3bOQ1-5WsF-zU0jA9Lh_"
                "rdSDEBwhbe5VjsgHhqODAmJIG3rjg5IILAwbXRLxpxUwmioSq7TFank8NnLQkcJCGQiQEqo"
                "bQ39opqSDUQjjf_aXo2GobviOU2MPwbsUqji3qd_iwvOlbentk7LsYwJxsgCOQjuAjkFVnW"
                "EUr1tHBafVWfC0qOiMJn_gF6m6POs3SVb_BMvbtfGUXZseOPVLBJtQ0DIyUGoQvhy2VjfOF"
                "nwnhNGbKR4UJRXHi_tXWbi0bviqi42H-VKRmrVV6ToyUQtqn0FvKmgUGQoQ"
            ),
            "use": "enc",
        }

    return {
        "messageId": str(uuid.uuid4()),
        "conversationId": conversation_id,
        "publicKey": public_key,
    }


class Client:
    """Async client for Duck.ai."""

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
        "_solved_hash",
        "_conversation_id",
        "_journey_id",
        "_fe_version",
        "_warmed",
    )

    def __init__(
        self,
        *,
        impersonate: Optional[str] = "chrome131_android",
        proxy: Optional[str] = None,
        model: Union[str, Model] = Model.GPT_6_LUNA,
        system: Optional[str] = None,
        max_retries: int = 4,
        log_level: str = "INFO",
        pool: Optional[Sequence[str]] = None,
        solved_hash: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        setup_logging(log_level)
        pool = list(pool) if pool else [
            "chrome131_android",
            "chrome131",
            "chrome124",
            "chrome99_android",
        ]
        self._http = HTTPClient(
            impersonate=impersonate or "chrome131_android",
            proxy=proxy,
            pool=pool,
            user_agent=user_agent,
        )
        self._model = str(model)
        self._system = system
        self._vqd4: Optional[str] = None
        self._hash1: Optional[str] = solved_hash
        self._solved_hash = solved_hash
        self._max_retries = max_retries
        self._history: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._last_refresh = 0.0
        self._conversation_id = str(uuid.uuid4())
        self._journey_id = uuid.uuid4().hex
        self._fe_version: Optional[str] = None
        self._warmed = False

    @property
    def model(self) -> str:
        return self._model

    @model.setter
    def model(self, value: Union[str, Model]) -> None:
        self._model = str(value)

    @property
    def history(self) -> List[Dict[str, Any]]:
        return list(self._history)

    def clear_history(self) -> None:
        self._history.clear()
        self._conversation_id = str(uuid.uuid4())

    def reset_session(self) -> None:
        self._hash1 = self._solved_hash
        self._vqd4 = None
        self._last_refresh = 0.0
        self._warmed = False
        self.clear_history()
        self._journey_id = uuid.uuid4().hex

    @staticmethod
    def _content_blocks(text: str) -> List[Dict[str, str]]:
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

        messages.append(
            {"role": "user", "content": self._content_blocks(user_text)}
        )
        return messages

    def _fe_signals(self) -> str:
        now = int(time.time() * 1000)
        payload = {
            "start": now - 1500,
            "events": [
                {"name": "startNewChat_free", "delta": 261},
                {"name": "action", "delta": 1458, "trusted": True},
            ],
            "end": 4050,
        }
        return b64encode(orjson.dumps(payload)).decode("ascii")

    async def _warmup(self) -> None:
        if self._warmed and self._fe_version:
            return
        try:
            home = await self._http.get(BASE + "/")
            text = (
                home.text
                if hasattr(home, "text")
                else home.content.decode("utf-8", "replace")
            )
            import re

            tag = re.search(r'data-version-tag="([^"]+)"', text)
            sha = re.search(r'data-version-sha="([^"]+)"', text)
            if tag and sha:
                self._fe_version = f"{tag.group(1)}-{sha.group(1)}"
                log.debug("fe_version={}", self._fe_version)
        except Exception as exc:
            log.debug("home warmup failed: {}", exc)

        for url in (CAPABILITIES_URL, AUTH_TOKEN_URL, COUNTRY_URL):
            try:
                await self._http.get(url)
            except Exception:
                pass
        self._warmed = True

    async def _refresh_tokens(self, force: bool = False) -> None:
        if self._solved_hash and not force:
            self._hash1 = self._solved_hash
            return

        now = time.monotonic()
        if not force and self._hash1 and (now - self._last_refresh) < 600:
            return

        async with self._lock:
            now = time.monotonic()
            if not force and self._hash1 and (now - self._last_refresh) < 600:
                return

            await self._warmup()
            for attempt in range(1, self._max_retries + 1):
                try:
                    resp = await self._http.get(
                        STATUS_URL,
                        headers={
                            "x-vqd-accept": "1",
                            "Accept": "text/event-stream",
                        },
                    )
                    headers = dict(resp.headers)
                    solved, vqd4 = solve_from_status(
                        headers,
                        self._http.user_agent,
                        sec_ch_ua=getattr(self._http, "sec_ch_ua", None),
                        origin=BASE,
                    )
                    if not solved and not self._solved_hash:
                        raise ChallengeError("no challenge tokens in status")

                    self._hash1 = self._solved_hash or solved
                    if vqd4:
                        self._vqd4 = vqd4
                    self._last_refresh = time.monotonic()
                    log.info(
                        "tokens refreshed  imp={}  ua={}...  vqd4={}  hash_len={}",
                        self._http.impersonate,
                        self._http.user_agent[:50],
                        bool(self._vqd4),
                        len(self._hash1 or ""),
                    )
                    return
                except BanLimitError:
                    log.warning("refresh BN_LIMIT attempt {}", attempt)
                    await asyncio.sleep(3.0 * attempt)
                except RateLimitError:
                    log.warning("refresh rate limited attempt {}", attempt)
                    await asyncio.sleep(1.5 * attempt)
                except (AuthError, ChallengeError, HTTPException) as e:
                    log.warning("refresh attempt {} failed: {}", attempt, e)
                    await asyncio.sleep(0.4 * attempt)
                except Exception as e:
                    log.warning("refresh unexpected: {}", e)
                    await asyncio.sleep(0.5 * attempt)

            if self._solved_hash:
                self._hash1 = self._solved_hash
                return
            raise ChallengeError("failed to obtain valid VQD tokens after retries")

    def _chat_headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            "x-fe-version": self._fe_version or "",
            "x-fe-signals": self._fe_signals(),
            "x-ddg-journey-id": self._journey_id,
            "x-duckai-response-id": str(uuid.uuid4()),
            "x-duckai-tool-approval": "web-search",
            "x-duckai-consent-purposes": "user-location,image-generation,web-search",
            "priority": "u=1, i",
        }
        if self._hash1:
            h["x-vqd-hash-1"] = self._hash1
        if self._vqd4:
            h["x-vqd-4"] = self._vqd4
        return h

    def _chat_body(
        self,
        messages: List[Dict[str, Any]],
        model: str,
    ) -> Dict[str, Any]:
        # Exact shape from live Moto G / Chrome 157 capture (Nov 19 2026)
        return {
            "model": model,
            "messages": messages,
            "canUseTools": True,
            "reasoningEffort": "none",
            "canUseApproxLocation": None,
            "canDelegateImageGeneration": None,
            "canShowGreeting": True,
            "durableStream": make_durable_stream(self._conversation_id),
        }

    async def _ensure_ready(self) -> None:
        await self._warmup()
        if not self._hash1 and not self._vqd4:
            await self._refresh_tokens(force=True)

    async def chat(
        self,
        content: str,
        *,
        model: Optional[Union[str, Model]] = None,
        system: Optional[str] = None,
        history: bool = True,
    ) -> ChatResult:
        await self._ensure_ready()
        model_s = str(model or self._model)
        messages = self._build_messages(content, history=history, system=system)
        body = self._chat_body(messages, model_s)

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
                    self._history.append(
                        {"role": "user", "content": self._content_blocks(content)}
                    )
                    self._history.append(
                        {"role": "assistant", "content": self._content_blocks(text)}
                    )
                return ChatResult(content=text, model=model_s, vqd=self._vqd4)
            except BanLimitError as e:
                last_err = e
                log.warning(
                    "BN_LIMIT attempt {} — body/headers still mismatched or IP flagged",
                    attempt,
                )
                if attempt >= 2:
                    break
                await asyncio.sleep(4.0 * attempt)
            except AuthError as e:
                last_err = e
                log.warning("chat auth fail attempt {} — refreshing", attempt)
                self._hash1 = None
                await self._refresh_tokens(force=True)
            except RateLimitError as e:
                last_err = e
                log.warning("rate limited — reset guest session")
                self.reset_session()
                await self._refresh_tokens(force=True)
                await asyncio.sleep(1.2 * attempt)
            except HTTPException as e:
                last_err = e
                log.warning("http error attempt {}: {}", attempt, e)
                if getattr(e, "status", None) in (400, 418):
                    self._hash1 = None
                    await self._refresh_tokens(force=True)
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
        await self._ensure_ready()
        model_s = str(model or self._model)
        messages = self._build_messages(content, history=history, system=system)
        body = self._chat_body(messages, model_s)

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
                        {"role": "user", "content": self._content_blocks(content)}
                    )
                    self._history.append(
                        {
                            "role": "assistant",
                            "content": self._content_blocks("".join(full)),
                        }
                    )
                return
            except BanLimitError:
                log.warning("stream BN_LIMIT attempt {}", attempt)
                if attempt >= 2:
                    break
                await asyncio.sleep(4.0 * attempt)
            except AuthError:
                log.warning("stream auth fail — refresh")
                self._hash1 = None
                await self._refresh_tokens(force=True)
            except RateLimitError:
                log.warning("stream rate limited — reset")
                self.reset_session()
                await self._refresh_tokens(force=True)
                await asyncio.sleep(1.2 * attempt)
            except Exception as e:
                log.warning("stream error: {}", e)
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
                    msg = obj.get("message") or obj.get("content") or ""
                    if isinstance(msg, list):
                        msg = "".join(
                            b.get("text", "") if isinstance(b, dict) else str(b)
                            for b in msg
                        )
                    if msg:
                        parts.append(str(msg))
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
