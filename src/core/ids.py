"""Identifier generation. Sequential, so the same run gives the same IDs (NFR-13)."""

from typing import Protocol


class IdGenerator(Protocol):
    def next_id(self, prefix: str) -> str: ...


class SequentialIdGenerator:
    """``next_id("C")`` gives ``C-000001``, ``C-000002``, ... one counter per prefix."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}

    def next_id(self, prefix: str) -> str:
        number = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = number
        return f"{prefix}-{number:06d}"
