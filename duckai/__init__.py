"""
Duck.ai (DuckDuckGo AI Chat) reverse-engineered client.

Package: ddgai
Made by frat.
"""

from .client import Client
from .errors import *
from .models import *
from .enums import Model

__version__ = "1.6.1"
__author__ = "frat"

__all__ = (
    "Client",
    "Model",
)
