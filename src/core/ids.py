"""Identifier generation. Sequential, so the same run gives the same IDs (NFR-13)."""

from collections.abc import Iterable
from typing import Protocol


class IdGenerator(Protocol):
    def next_id(self, prefix: str) -> str: ...


class SequentialIdGenerator:
    """``next_id("C")`` gives ``C-000001``, ``C-000002``, ... one counter per prefix."""

    def __init__(self, existing_ids: Iterable[str] = ()) -> None:
        """Resume above persisted numeric suffixes; ignore opaque non-sequential IDs.

        A fresh store still starts at one. Explicitly injected generators remain
        the caller's responsibility; CoreFacade supplies persisted IDs by default.
        """
        self._counters: dict[str, int] = {}
        for value in existing_ids:
            prefix, separator, suffix = value.rpartition("-")
            if separator and prefix and suffix.isascii() and suffix.isdecimal():
                self._counters[prefix] = max(self._counters.get(prefix, 0), int(suffix))

    def next_id(self, prefix: str) -> str:
        number = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = number
        return f"{prefix}-{number:06d}"
