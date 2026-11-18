import asyncio
from duckai import Client, Model


async def main() -> None:
    async with Client(model=Model.GPT_6_LUNA) as client:
        r = await client.chat("say hi in one word")
        print(r.content)


if __name__ == "__main__":
    asyncio.run(main())
