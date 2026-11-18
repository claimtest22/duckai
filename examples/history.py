"""Multi-turn conversation with history."""

import asyncio
from duckai import Client, Model


async def main() -> None:
    async with Client(model=Model.GPT_4O_MINI) as client:
        r1 = await client.chat("My name is Alex and I like Rust.")
        print("Bot:", r1.content)

        r2 = await client.chat("What is my name and what language do I like?")
        print("Bot:", r2.content)

        print("\nHistory length:", len(client.history))
        client.clear_history()
        print("After clear:", len(client.history))


if __name__ == "__main__":
    asyncio.run(main())
