# duckai

High-performance reverse-engineered **Duck.ai** (DuckDuckGo AI Chat) client.

Made by **frat**.

## Features

- Pure-Python static solver for the `x-vqd-hash-1` challenge
- Automatic token refresh + impersonation rotation on 418 / 429
- Full `curl_cffi` browser impersonation pool (desktop + mobile)
- Streaming + non-streaming chat
- Conversation history
- orjson + async for minimal overhead
- loguru logging
- discord.py-style structure & type hints

## Install

```bash
pip install duckai
# or from source
pip install -e .
```

## Quick start

```python
import asyncio
from duckai import Client, Model

async def main():
    async with Client(model=Model.GPT_4O_MINI, log_level="INFO") as client:
        result = await client.chat("ping")
        print(result.content)

asyncio.run(main())
```

## Streaming

```python
async with Client() as client:
    async for chunk in client.stream("explain quantum computing in one sentence"):
        if chunk.content:
            print(chunk.content, end="", flush=True)
```

## Models

```python
models = await client.models()
for m in models:
    print(m.model, m.model_name)
```

## Notes

- The challenge solver is a pure-Python static reimplementation. It works for the current generation of challenges. When DuckDuckGo rotates the challenge heavily the client auto-retries and rotates fingerprints.
- Datacenter IPs are frequently blocked or rate-limited. Prefer residential proxies for production use.
- Respect DuckDuckGo ToS.

## License

MIT — made by frat
