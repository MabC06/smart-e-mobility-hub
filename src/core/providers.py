"""Provider ports: the few calls that go from ``core`` to another module (core-api-spec.md, 6.1).

``core`` defines the ports, the module that implements one registers it at start-up, so every
import still points into ``core`` (NFR-22). The registry knows the ports and nothing about their
methods yet: the method signatures are proposals until the design review settles them, and a
module that calls a port passes the call as a function.

If no provider is registered, or the provider fails, the caller gets RESOURCE_UNAVAILABLE and
must not assume an answer.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

from core.errors import ErrorCode
from core.result import Err, Result

logger = logging.getLogger("core.providers")


class ProviderPort(StrEnum):
    """One port per implementing module (D-020): ReservationDemand and HoldConsumer (M2),
    ChargingDemand (M3), AlternativeHubProvider and AlternativeChargingProvider (M4)."""

    RESERVATION_DEMAND = "ReservationDemand"
    CHARGING_DEMAND = "ChargingDemand"
    ALTERNATIVE_HUB = "AlternativeHubProvider"
    ALTERNATIVE_CHARGING = "AlternativeChargingProvider"
    HOLD_CONSUMER = "HoldConsumer"


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[ProviderPort, object] = {}

    def register(self, port: ProviderPort, provider: object) -> None:
        """One provider per port. A second registration is a start-up mistake, so it raises."""
        if port in self._providers:
            raise ValueError(f"a provider for {port.value} is already registered")
        self._providers[port] = provider

    def is_registered(self, port: ProviderPort) -> bool:
        return port in self._providers

    def call[T](self, port: ProviderPort, work: Callable[[Any], Result[T]]) -> Result[T]:
        """Run ``work(provider)``; no provider or a failing one gives RESOURCE_UNAVAILABLE."""
        provider = self._providers.get(port)
        if provider is None:
            return Err(
                ErrorCode.RESOURCE_UNAVAILABLE, f"no provider is registered for {port.value}"
            )
        try:
            return work(provider)
        except Exception:
            logger.exception("provider %s failed", port.value)
            return Err(ErrorCode.RESOURCE_UNAVAILABLE, f"the provider for {port.value} failed")


@dataclass(frozen=True, slots=True)
class ScheduledChargingSessionRow:
    """Typed row representing exposed scheduled charging sessions (D-020)."""

    session_id: str
    vehicle_id: str
    charger_id: str | None
    energy_kwh: float
    start_time: datetime
    end_time: datetime


class ChargingDemand(Protocol):
    """The provider port for Module M3 Charging Demand (D-020)."""

    def scheduled_sessions(
        self, hub_id: str, horizon: timedelta
    ) -> Result[list[ScheduledChargingSessionRow]]: ...
