import asyncio
from duckai import Client, Model


async def main() -> None:
    async with Client(model=Model.GPT_6_LUNA, log_level="INFO") as client:
        print("streaming:\n")
        async for chunk in client.stream("say hello in one short sentence"):
            if chunk.content:
                print(chunk.content, end="", flush=True)
        print("\n")


if __name__ == "__main__":
    asyncio.run(main())
