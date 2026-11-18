"""
Model identifiers.
"""

from __future__ import annotations

from enum import Enum


class Model(str, Enum):
    """Known Duck.ai model ids."""

    GPT_6_LUNA = "gpt-6-luna"
    GPT_4O_MINI = "gpt-4o-mini"
    O3_MINI = "o3-mini"
    CLAUDE_3_HAIKU = "claude-3-haiku-20240307"
    LLAMA_3_3_70B = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
    MISTRAL_SMALL = "mistralai/Mistral-Small-24B-Instruct-2501"

    def __str__(self) -> str:
        return self.value
