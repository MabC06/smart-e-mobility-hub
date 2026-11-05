"""Alternative Hub and Charging Point Providers (UC-M4-05, UC-M4-07, BR-M4-10, D-020).

Implements ProviderPort.ALTERNATIVE_HUB and ProviderPort.ALTERNATIVE_CHARGING.
Read-only queries against Core, returning ranked candidates with as_of timestamp.
"""

from dataclasses import dataclass
from typing import Any

from core.domain.enums import ChargingPointStatus, HubStatus, SpaceStatus, VehicleState, VehicleType
from core.facade import CoreFacade
from core.result import Ok, Result
from core.views import VehicleFilter

from .config import AllocationConfig, default_config


@dataclass(frozen=True, slots=True)
class HubAlternative:
    hub_id: str
    hub_name: str
    closeness: int
    available_vehicles_count: int
    free_spaces_count: int
    best_battery_level: float


@dataclass(frozen=True, slots=True)
class ChargingAlternative:
    request_id: str
    alternative_hub_id: str | None
    charging_point_id: str | None
    closeness: int
    status: str  # "FOUND" or "NO_CHARGER"


class AlternativeHubService:
    """Implements ProviderPort.ALTERNATIVE_HUB (UC-M4-05, BR-M4-10)."""

    def __init__(self, core: CoreFacade, config: AllocationConfig | None = None) -> None:
        self._core = core
        self._config = config or default_config()

    def suggest_alternative_hubs(
        self,
        requested_hub_id: str,
        vehicle_type: VehicleType | None = None,
        require_vehicle: bool = True,
        require_parking: bool = False,
        limit: int = 3,
    ) -> Result[dict[str, Any]]:
        """Find and rank alternative hubs according to BR-M4-10.

        Ranking order:
        1. Closeness (lower distance first)
        2. Resource count (more available vehicles/spaces first)
        3. Battery level (higher first)
        4. Hub ID (lexicographical)
        """
        now = self._core._clock.now()
        hubs = self._core.queries.list_hubs()

        candidates: list[HubAlternative] = []
        for hub in hubs:
            if hub.hub_id == requested_hub_id:
                continue
            if hub.status in {HubStatus.MAINTENANCE, HubStatus.CRITICAL}:
                continue

            # Query spaces
            spaces = self._core.queries.list_spaces(hub.hub_id)
            free_spaces = [s for s in spaces if s.status == SpaceStatus.AVAILABLE]

            # Query vehicles
            v_filter = VehicleFilter(
                hub_id=hub.hub_id,
                state=VehicleState.AVAILABLE,
                vehicle_type=vehicle_type,
                min_battery=self._config.min_dispatch_battery if require_vehicle else None,
            )
            available_vehicles = self._core.queries.find_vehicles(v_filter)

            if require_vehicle and not available_vehicles:
                continue
            if require_parking and not free_spaces:
                continue

            closeness = self._config.get_closeness(requested_hub_id, hub.hub_id)
            best_battery = max((v.battery_pct for v in available_vehicles), default=0.0)

            candidates.append(
                HubAlternative(
                    hub_id=hub.hub_id,
                    hub_name=hub.name,
                    closeness=closeness,
                    available_vehicles_count=len(available_vehicles),
                    free_spaces_count=len(free_spaces),
                    best_battery_level=best_battery,
                )
            )

        if not candidates:
            reason = (
                "NO_VEHICLE"
                if require_vehicle
                else ("NO_PARKING" if require_parking else "ALL_HUBS_FULL")
            )
            return Ok({"candidates": [], "as_of": now.isoformat(), "reason_code": reason})

        # Sort according to BR-M4-10
        candidates.sort(
            key=lambda c: (
                c.closeness,
                -(c.available_vehicles_count if require_vehicle else c.free_spaces_count),
                -c.best_battery_level,
                c.hub_id,
            )
        )

        return Ok(
            {
                "candidates": [
                    {
                        "hub_id": c.hub_id,
                        "hub_name": c.hub_name,
                        "closeness": c.closeness,
                        "available_vehicles": c.available_vehicles_count,
                        "free_spaces": c.free_spaces_count,
                        "best_battery_level": c.best_battery_level,
                    }
                    for c in candidates[:limit]
                ],
                "as_of": now.isoformat(),
                "reason_code": "OK",
            }
        )


class AlternativeChargingService:
    """Implements ProviderPort.ALTERNATIVE_CHARGING (UC-M4-07, BR-M4-10, BR-M3-02)."""

    def __init__(self, core: CoreFacade, config: AllocationConfig | None = None) -> None:
        self._core = core
        self._config = config or default_config()

    def find_alternative_charging(
        self, displaced_requests: list[dict[str, Any]], failed_hub_id: str
    ) -> Result[list[dict[str, Any]]]:
        """Find alternative charging points across other hubs for displaced requests."""
        hubs = self._core.queries.list_hubs()

        # Find hubs with available charging points
        hub_chargers: list[tuple[str, int, list[str]]] = []
        for hub in hubs:
            if hub.hub_id == failed_hub_id:
                continue
            if hub.status in {HubStatus.MAINTENANCE, HubStatus.CRITICAL}:
                continue

            chargers = self._core.queries.list_charging_points(hub.hub_id)
            available_chargers = [
                cp.charging_point_id
                for cp in chargers
                if cp.status == ChargingPointStatus.AVAILABLE
            ]
            if available_chargers:
                dist = self._config.get_closeness(failed_hub_id, hub.hub_id)
                hub_chargers.append((hub.hub_id, dist, available_chargers))

        # Sort hubs: closest first, then most free chargers, then hub_id
        hub_chargers.sort(key=lambda item: (item[1], -len(item[2]), item[0]))

        results: list[dict[str, Any]] = []
        assigned_chargers: set[str] = set()

        for req in displaced_requests:
            req_id = req.get("request_id", "unknown")
            assigned = False

            for hub_id, dist, cp_ids in hub_chargers:
                free_cps = [cp_id for cp_id in cp_ids if cp_id not in assigned_chargers]
                if free_cps:
                    chosen_cp = free_cps[0]
                    assigned_chargers.add(chosen_cp)
                    results.append(
                        {
                            "request_id": req_id,
                            "alternative_hub_id": hub_id,
                            "charging_point_id": chosen_cp,
                            "closeness": dist,
                            "status": "FOUND",
                        }
                    )
                    assigned = True
                    break

            if not assigned:
                results.append(
                    {
                        "request_id": req_id,
                        "alternative_hub_id": None,
                        "charging_point_id": None,
                        "closeness": 99,
                        "status": "NO_CHARGER",
                    }
                )

        return Ok(results)
