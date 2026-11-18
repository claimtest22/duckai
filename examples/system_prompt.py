"""Custom system prompt example."""

import asyncio
from duckai import Client, Model


SYSTEM = """You are a concise senior Python engineer.
Answer in short bullet points only. No fluff."""


async def main() -> None:
    async with Client(
        model=Model.GPT_4O_MINI,
        system=SYSTEM,
        log_level="INFO",
    ) as client:
        result = await client.chat("How do I make an async HTTP request with httpx?")
        print(result.content)

        # one-off override
        result2 = await client.chat(
            "Same question but pretend you are a pirate.",
            system="You speak only like a pirate. Keep it under 3 sentences.",
            history=False,
        )
        print("---")
        print(result2.content)


if __name__ == "__main__":
    asyncio.run(main())
