# ddgai

High-performance reverse-engineered **Duck.ai** client.

Made by **frat**.

## Install

```bash
pip install -U ddgai
```

## Quick start

```python
import asyncio
from duckai import Client, Model

async def main():
    async with Client(model=Model.GPT_6_LUNA) as client:
        r = await client.chat("say hi")
        print(r.content)

asyncio.run(main())
```

## Streaming

```python
async with Client() as client:
    async for chunk in client.stream("explain async in one sentence"):
        if chunk.content:
            print(chunk.content, end="", flush=True)
```

## System prompts

Duck.ai has no `system` role. Prompts are prepended into the first user message.

```python
async with Client(system="Answer in 3 words max.") as client:
    print((await client.chat("What is Python?")).content)
```

## Usage limit / guest reset

When free-tier usage is exhausted the client resets the guest session automatically.
You can also force it:

```python
client.reset_session()
```

## Challenge / 418 ERR_CHALLENGE

The live `x-vqd-hash-1` PoW needs real DOM metrics. Pure-Python is best-effort.

**Most reliable:** capture a solved hash from your browser (Network tab → chat request → `x-vqd-hash-1`) and pass it in:

```python
async with Client(solved_hash="eyJ...") as client:
    print((await client.chat("hi")).content)
```

Optional Node.js fallback is used automatically when `node` is on PATH.

Acode does **not** run browser JS for this. Termux + Node can.

## Notes

- Host: `https://duck.ai`
- Message content is typed blocks: `{"type":"text","text":"..."}`
- Default model: `gpt-6-luna`

## License

MIT — made by frat
