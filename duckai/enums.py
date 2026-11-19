"""
Enums used by the library.
"""

from enum import Enum


class Model(str, Enum):
    """Available Duck.ai models (free tier + common ones)."""

    GPT_6_LUNA = "gpt-5.6-luna"
    GPT_5_6_LUNA = "gpt-5.6-luna"
    GPT_5_4_MINI = "gpt-5.4-mini"
    CLAUDE_HAIKU_4_5 = "claude-haiku-4-5"
    MISTRAL_SMALL_4 = "mistral-small-4"
    GPT_OSS_120B = "gpt-oss-120b"
    GEMMA_4_31B = "gemma-4-31b"
    GPT_4O_MINI = "gpt-4o-mini"
    O3_MINI = "o3-mini"
    CLAUDE_3_HAIKU = "claude-3-haiku-20240307"

    def __str__(self) -> str:
        return self.value
