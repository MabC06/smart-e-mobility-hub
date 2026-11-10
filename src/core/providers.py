"""Provider ports: the few calls that go from ``core`` to another module (core-api-spec.md, 6.1).

``core`` defines the ports, the module that implements one registers it at start-up, so every
import still points into ``core`` (NFR-22). The registry knows the ports and nothing about their
methods yet: the method signatures are proposals until the design review settles them, and a
module that calls a port passes the call as a function.

If no provider is registered, or the provider fails, the caller gets RESOURCE_UNAVAILABLE and
must not assume an answer.
"""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from core.domain.enums import VehicleType
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


# ------------------------------------------------------------------ allocation ports (M4, D-020)


@dataclass(frozen=True, slots=True)
class AlternativeHubRequest:
    """Read-only lookup request for alternative hubs (UC-M4-05, BR-M4-10)."""

    requested_hub_id: str
    vehicle_type: VehicleType | None = None
    require_vehicle: bool = True
    require_parking: bool = False
    limit: int = 3


@dataclass(frozen=True, slots=True)
class HubAlternative:
    """One candidate hub ranked by closeness, available capacity, battery and hub ID."""

    hub_id: str
    hub_name: str
    closeness: int
    available_vehicles: int
    free_spaces: int
    best_battery_level: float


@dataclass(frozen=True, slots=True)
class AlternativeHubResult:
    """Ranked alternative hubs with read timestamp and BR-M4-10 reason code."""

    candidates: tuple[HubAlternative, ...]
    as_of: datetime
    reason_code: str


class AlternativeHubProvider(Protocol):
    """M4 read port (UC-M4-05, D-020). Suggests alternative hubs without holding resources."""

    def suggest_alternative_hubs(
        self, request: AlternativeHubRequest
    ) -> Result[AlternativeHubResult]: ...


@dataclass(frozen=True, slots=True)
class DisplacedChargingRequest:
    """One charging request displaced from a hub with no free charging bay."""

    request_id: str
    details: str = ""


@dataclass(frozen=True, slots=True)
class ChargingAlternative:
    """Suggested alternative hub and charging point for one displaced charging request."""

    request_id: str
    alternative_hub_id: str | None
    charging_point_id: str | None
    closeness: int
    status: str


@dataclass(frozen=True, slots=True)
class AlternativeChargingResult:
    """Alternative charging suggestions paired per displaced request at read time."""

    alternatives: tuple[ChargingAlternative, ...]
    as_of: datetime


class AlternativeChargingProvider(Protocol):
    """M4 read port (UC-M4-07, D-020). Suggests free bays at other hubs for displaced requests."""

    def find_alternative_charging(
        self, requests: Sequence[DisplacedChargingRequest], hub_id: str
    ) -> Result[AlternativeChargingResult]: ...
