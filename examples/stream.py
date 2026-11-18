"""Streaming example."""

import asyncio
from duckai import Client, Model


async def main() -> None:
    async with Client(model=Model.GPT_4O_MINI) as client:
        print("Assistant: ", end="", flush=True)
        async for chunk in client.stream(
            "Write a 2-sentence explanation of what a Python generator is."
        ):
            if chunk.content:
                print(chunk.content, end="", flush=True)
        print()


if __name__ == "__main__":
    asyncio.run(main())
