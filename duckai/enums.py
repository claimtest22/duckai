"""Enums used by the library."""

from enum import Enum


class Model(str, Enum):
    """Available Duck.ai models."""

    GPT_6_LUNA = "gpt-6-luna"
    GPT_5_4_MINI = "gpt-5.4-mini"
    GPT_5_6_TERRA = "gpt-5.6-terra"
    GPT_5_6_SOL = "gpt-5.6-sol"
    CLAUDE_HAIKU_5_5 = "claude-haiku-5-5"
    CLAUDE_SONNET_5_5 = "claude-sonnet-5-5"
    CLAUDE_OPUS_5_5 = "claude-opus-5-5"
    MISTRAL_SMALL = "mistral-small-2603"
    TINFOIL_GEMMA = "tinfoil/gemma4-31b"
    TINFOIL_GPT_OSS = "tinfoil/gpt-oss-120b"

    # legacy aliases
    GPT_4O_MINI = "gpt-5.4-mini"
    GPT_5_6_LUNA = "gpt-6-luna"

    def __str__(self) -> str:
        return self.value
