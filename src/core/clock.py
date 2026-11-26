"""Injectable clock (D-005): code never reads the system clock directly. All times are UTC."""

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """A clock that only moves when told to; used by tests and by the What-if simulation."""

    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None:
            raise ValueError("clock time must be timezone-aware (UTC)")
        self._now = start.astimezone(UTC)

    def now(self) -> datetime:
        return self._now

    def set(self, value: datetime) -> None:
        if value.tzinfo is None:
            raise ValueError("clock time must be timezone-aware (UTC)")
        self._now = value.astimezone(UTC)

    def advance(self, delta: timedelta) -> None:
        self._now = self._now + delta
