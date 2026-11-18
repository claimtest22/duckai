# ddgai

High-performance reverse-engineered **Duck.ai** client.

Made by **frat**.

## Install

```bash
pip install -U ddgai
```

**PoW solver (required for reliable chat):**

```bash
# Node 18+ and jsdom
npm install -g jsdom
# or in project: npm install jsdom
```

The library shells out to `node duckai/solver.js` to execute the live
`x-vqd-hash-1` challenge. Pure-Python fallback exists but usually gets 418.

## Quick start

```python
import asyncio
from duckai import Client, Model

async def main():
    async with Client(model=Model.GPT_6_LUNA, log_level="DEBUG") as client:
        r = await client.chat("say hi")
        print(r.content)

asyncio.run(main())
```

## Streaming

```python
async with Client(impersonate="chrome131_android") as client:
    async for chunk in client.stream("explain async in one sentence"):
        if chunk.content:
            print(chunk.content, end="", flush=True)
```

## Android / Acode

1. Install Node (Termux: `pkg install nodejs`)
2. `npm install -g jsdom`
3. `pip install -U ddgai`
4. Run as usual — solver uses Node automatically

## Manual hash (no Node)

Capture `x-vqd-hash-1` from browser Network tab on a successful chat:

```python
async with Client(solved_hash="eyJ...") as client:
    print((await client.chat("hi")).content)
```

## Notes

- Host: `https://duck.ai`
- Message content blocks: `[{"type":"text","text":"..."}]`
- Default model: `gpt-6-luna`
- Datacenter IPs may get `ERR_BN_LIMIT` even with a valid PoW — use residential

## License

MIT — made by frat
