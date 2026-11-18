"""
Duck.ai (DuckDuckGo AI Chat) reverse-engineered client.

Made by frat.
"""

from .client import Client
from .errors import *
from .models import *
from .enums import Model

__version__ = "1.1.3"
__author__ = "frat"

__all__ = (
    "Client",
    "Model",
)
