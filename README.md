# duckchat

High-performance reverse-engineered **Duck.ai** (DuckDuckGo AI Chat) client.

Made by **frat**.

## Features

- Pure-Python static solver for the `x-vqd-hash-1` challenge
- Automatic token refresh + impersonation rotation on 418 / 429
- Full `curl_cffi` browser impersonation pool (desktop + mobile)
- Custom system prompts (per-client or per-call)
- Streaming + non-streaming chat
- Conversation history
- orjson + async for minimal overhead
- loguru logging
- discord.py-style structure & type hints

## Install

```bash
pip install duckchat
# or from source
pip install -e .
```

## Quick start

```python
import asyncio
from duckai import Client, Model

async def main():
    async with Client(model=Model.GPT_4O_MINI) as client:
        result = await client.chat("ping")
        print(result.content)

asyncio.run(main())
```

## System prompts

```python
async with Client(
    model=Model.GPT_4O_MINI,
    system="You are a concise senior engineer. Answer in short bullets only.",
) as client:
    r = await client.chat("How do I read a file asynchronously in Python?")
    print(r.content)

    # one-off override
    r2 = await client.chat(
        "Explain generators",
        system="You only speak like a pirate. Max 2 sentences.",
        history=False,
    )
```

## Streaming

```python
async with Client() as client:
    async for chunk in client.stream("explain quantum computing in one sentence"):
        if chunk.content:
            print(chunk.content, end="", flush=True)
```

## Multi-turn history

```python
async with Client() as client:
    await client.chat("My name is Alex")
    r = await client.chat("What is my name?")
    print(r.content)
    client.clear_history()
```

## Models

```python
models = await client.models()
for m in models:
    print(m.model, m.model_name)
```

## Examples

See the `examples/` directory:

- `basic.py` — one-shot chat
- `system_prompt.py` — custom system prompts
- `stream.py` — streaming
- `history.py` — multi-turn

## Notes

- The challenge solver is a pure-Python static reimplementation. It works for the current generation of challenges. When DuckDuckGo rotates the challenge heavily the client auto-retries and rotates fingerprints.
- Datacenter IPs are frequently blocked or rate-limited. Prefer residential proxies for production use.
- Respect DuckDuckGo ToS.

## License

MIT — made by frat
