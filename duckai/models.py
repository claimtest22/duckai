"""
Data models returned by the API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class Message:
    """A single chat message."""

    role: str
    content: str

    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(slots=True)
class ChatResult:
    """Result of a non-streaming chat call."""

    content: str
    model: str
    vqd: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


@dataclass(slots=True)
class StreamChunk:
    """A single SSE chunk from a streaming response."""

    content: str = ""
    done: bool = False
    model: Optional[str] = None
    vqd: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


@dataclass(slots=True)
class ModelInfo:
    """Information about a model."""

    model: str
    model_name: str = ""
    input_char_limit: str = ""
    created_by: str = ""
    is_open_source: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)
