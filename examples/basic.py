"""Minimal example — one-shot chat."""

import asyncio
from duckai import Client, Model


async def main() -> None:
    async with Client(model=Model.GPT_4O_MINI) as client:
        result = await client.chat("Reply with exactly the word PONG.")
        print(result.content)


if __name__ == "__main__":
    asyncio.run(main())
