"""Simple typed dict wrapper that supports both .key and ["key"] access."""
from __future__ import annotations
from typing import Any


class Result(dict):
    """Dict subclass that also supports attribute access."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'Result' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value

    def __delattr__(self, name: str) -> None:
        try:
            del self[name]
        except KeyError:
            raise AttributeError(f"'Result' object has no attribute '{name}'")
