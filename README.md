# ddgai

High-performance reverse-engineered **Duck.ai** client.

Made by **frat**.

## Features

- Node `vm` solver for `x-vqd-hash-1` (no browser automation)
- Fingerprint-aligned DOM stubs (matches accepted Chrome hashes)
- `curl_cffi` impersonation + auto refresh on 418 / 429
- Streaming + non-streaming chat
- Conversation history
- orjson + async
- loguru logging

## Requirements

- Python 3.10+
- **Node.js** on `PATH` (challenge solver only)

## Install

```bash
pip install ddgai
```

## Quick start

```python
import asyncio
from duckai import Client, Model

async def main():
    async with Client(model=Model.MISTRAL_SMALL, log_level="INFO") as client:
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

Common free ids: `gpt-6-luna`, `gpt-5.4-mini`, `mistral-small-2603`, `tinfoil/gemma4-31b`.

## License

MIT
