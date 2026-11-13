"""Alternative Hub and Charging Point Providers (UC-M4-05, UC-M4-07, BR-M4-10, D-020).

Implements ProviderPort.ALTERNATIVE_HUB and ProviderPort.ALTERNATIVE_CHARGING.
Read-only queries against Core, returning ranked dataclasses with as_of timestamp.
"""

from collections.abc import Sequence
from datetime import datetime, timedelta

from core.domain.entities import ResourceClaim
from core.domain.enums import (
    ChargingPointStatus,
    ClaimStatus,
    HolderKind,
    HubStatus,
    Ownership,
    ResourceType,
    SpaceStatus,
    VehicleState,
)
from core.errors import ErrorCode
from core.facade import CoreFacade
from core.providers import (
    AlternativeChargingResult,
    AlternativeHubRequest,
    AlternativeHubResult,
    ChargingAlternative,
    DisplacedChargingRequest,
    HubAlternative,
)
from core.result import Err, Ok, Result
from core.views import HubView, VehicleFilter

from .config import AllocationConfig, default_config


def _empty_hub_reason(request: AlternativeHubRequest, any_vehicle: bool, any_parking: bool) -> str:
    if request.require_vehicle and not any_vehicle:
        return "NO_VEHICLE"
    if request.require_parking and not any_parking:
        return "NO_PARKING"
    return "ALL_HUBS_FULL"


class AlternativeHubService:
    """Implements ProviderPort.ALTERNATIVE_HUB (UC-M4-05, BR-M4-10)."""

    def __init__(self, core: CoreFacade, config: AllocationConfig | None = None) -> None:
        self._core = core
        self._config = config or default_config()

    def _active_hold_ids(self, now: datetime, lookahead_end: datetime) -> tuple[set[str], set[str]]:
        claims = self._core.query_entities(
            ResourceClaim,
            lambda c: c.status == ClaimStatus.ACTIVE and c.end_at > now,
        )
        vehicle_ids = {
            c.resource_id
            for c in claims
            if c.resource_type == ResourceType.VEHICLE
            and (c.holder_kind is HolderKind.DISPATCH_TASK or c.start_at < lookahead_end)
        }
        space_ids = {
            c.resource_id
            for c in claims
            if c.resource_type == ResourceType.SPACE and c.start_at < lookahead_end
        }
        return vehicle_ids, space_ids

    def _evaluate_hub(
        self,
        hub: HubView,
        request: AlternativeHubRequest,
        claimed_vids: set[str],
        claimed_sids: set[str],
    ) -> tuple[HubAlternative | None, bool, bool]:
        spaces = self._core.queries.list_spaces(hub.hub_id)
        free_spaces = [
            s
            for s in spaces
            if s.status == SpaceStatus.AVAILABLE and s.parking_space_id not in claimed_sids
        ]
        v_filter = VehicleFilter(
            hub_id=hub.hub_id,
            state=VehicleState.AVAILABLE,
            ownership=Ownership.FLEET,
            vehicle_type=request.vehicle_type,
            min_battery=self._config.min_dispatch_battery if request.require_vehicle else None,
        )
        available_vehicles = [
            v
            for v in self._core.queries.find_vehicles(v_filter)
            if v.vehicle_id not in claimed_vids
        ]
        has_vehicle = bool(available_vehicles)
        has_parking = bool(free_spaces)
        if (request.require_vehicle and not has_vehicle) or (
            request.require_parking and not has_parking
        ):
            return None, has_vehicle, has_parking

        closeness = self._config.get_closeness(request.requested_hub_id, hub.hub_id)
        best_battery = max((v.battery_pct for v in available_vehicles), default=0.0)
        candidate = HubAlternative(
            hub_id=hub.hub_id,
            hub_name=hub.name,
            closeness=closeness,
            available_vehicles=len(available_vehicles),
            free_spaces=len(free_spaces),
            best_battery_level=best_battery,
        )
        return candidate, has_vehicle, has_parking

    def suggest_alternative_hubs(
        self, request: AlternativeHubRequest
    ) -> Result[AlternativeHubResult]:
        """Find and rank alternative hubs according to BR-M4-10.

        Ranking order:
        1. Closeness (lower distance first)
        2. Resource count (more available vehicles/spaces first)
        3. Battery level (higher first)
        4. Hub ID (lexicographical)
        """
        if not request.requested_hub_id.strip():
            return Err(ErrorCode.INVALID_INPUT, "requested_hub_id is required")
        if request.limit < 1:
            return Err(ErrorCode.INVALID_INPUT, "limit must be at least 1")

        now = self._core.queries.get_config().as_of
        lookahead_end = now + timedelta(minutes=self._config.reservation_lookahead_minutes)
        claimed_vids, claimed_sids = self._active_hold_ids(now, lookahead_end)

        candidates: list[HubAlternative] = []
        any_vehicle = False
        any_parking = False
        for hub in self._core.queries.list_hubs():
            if hub.hub_id == request.requested_hub_id:
                continue
            if hub.status in {HubStatus.MAINTENANCE, HubStatus.CRITICAL}:
                continue
            candidate, has_v, has_p = self._evaluate_hub(hub, request, claimed_vids, claimed_sids)
            any_vehicle = any_vehicle or has_v
            any_parking = any_parking or has_p
            if candidate is not None:
                candidates.append(candidate)

        if not candidates:
            return Ok(
                AlternativeHubResult(
                    candidates=(),
                    as_of=now,
                    reason_code=_empty_hub_reason(request, any_vehicle, any_parking),
                )
            )

        candidates.sort(
            key=lambda c: (
                c.closeness,
                -(c.available_vehicles if request.require_vehicle else c.free_spaces),
                -c.best_battery_level,
                c.hub_id,
            )
        )
        return Ok(
            AlternativeHubResult(
                candidates=tuple(candidates[: request.limit]),
                as_of=now,
                reason_code="OK",
            )
        )


class AlternativeChargingService:
    """Implements ProviderPort.ALTERNATIVE_CHARGING (UC-M4-07, BR-M4-10, BR-M3-02)."""

    def __init__(self, core: CoreFacade, config: AllocationConfig | None = None) -> None:
        self._core = core
        self._config = config or default_config()

    def _active_charging_holds(
        self, now: datetime, lookahead_end: datetime
    ) -> tuple[set[str], set[str]]:
        claims = self._core.query_entities(
            ResourceClaim,
            lambda c: (
                c.status == ClaimStatus.ACTIVE and c.end_at > now and c.start_at < lookahead_end
            ),
        )
        claimed_cps = {
            c.resource_id for c in claims if c.resource_type == ResourceType.CHARGING_POINT
        }
        claimed_spaces = {c.resource_id for c in claims if c.resource_type == ResourceType.SPACE}
        return claimed_cps, claimed_spaces

    def _available_bays_by_hub(
        self, failed_hub_id: str, claimed_cps: set[str], claimed_spaces: set[str]
    ) -> list[tuple[str, int, list[str]]]:
        hub_chargers: list[tuple[str, int, list[str]]] = []
        for hub in self._core.queries.list_hubs():
            if hub.hub_id == failed_hub_id:
                continue
            if hub.status in {HubStatus.MAINTENANCE, HubStatus.CRITICAL}:
                continue

            space_status = {
                s.parking_space_id: s.status for s in self._core.queries.list_spaces(hub.hub_id)
            }
            available_chargers = [
                cp.charging_point_id
                for cp in self._core.queries.list_charging_points(hub.hub_id)
                if cp.status == ChargingPointStatus.AVAILABLE
                and cp.charging_point_id not in claimed_cps
                and space_status.get(cp.parking_space_id) == SpaceStatus.AVAILABLE
                and cp.parking_space_id not in claimed_spaces
            ]
            if available_chargers:
                dist = self._config.get_closeness(failed_hub_id, hub.hub_id)
                hub_chargers.append((hub.hub_id, dist, available_chargers))

        hub_chargers.sort(key=lambda item: (item[1], -len(item[2]), item[0]))
        return hub_chargers

    def find_alternative_charging(
        self, requests: Sequence[DisplacedChargingRequest], hub_id: str
    ) -> Result[AlternativeChargingResult]:
        """Find alternative charging points across other hubs for displaced requests."""
        if not hub_id.strip():
            return Err(ErrorCode.INVALID_INPUT, "hub_id is required")
        for req in requests:
            if not req.request_id.strip():
                return Err(ErrorCode.INVALID_INPUT, "request_id is required")

        now = self._core.queries.get_config().as_of
        lookahead_end = now + timedelta(minutes=self._config.reservation_lookahead_minutes)
        claimed_cps, claimed_spaces = self._active_charging_holds(now, lookahead_end)
        hub_chargers = self._available_bays_by_hub(hub_id, claimed_cps, claimed_spaces)

        alternatives: list[ChargingAlternative] = []
        assigned_chargers: set[str] = set()
        for req in requests:
            alt = self._match_charger(req.request_id, hub_chargers, assigned_chargers)
            alternatives.append(alt)

        return Ok(AlternativeChargingResult(alternatives=tuple(alternatives), as_of=now))

    @staticmethod
    def _match_charger(
        request_id: str,
        hub_chargers: list[tuple[str, int, list[str]]],
        assigned_chargers: set[str],
    ) -> ChargingAlternative:
        for alt_hub_id, dist, cp_ids in hub_chargers:
            free_cps = [cp_id for cp_id in cp_ids if cp_id not in assigned_chargers]
            if free_cps:
                chosen_cp = free_cps[0]
                assigned_chargers.add(chosen_cp)
                return ChargingAlternative(
                    request_id=request_id,
                    alternative_hub_id=alt_hub_id,
                    charging_point_id=chosen_cp,
                    closeness=dist,
                    status="FOUND",
                )
        return ChargingAlternative(
            request_id=request_id,
            alternative_hub_id=None,
            charging_point_id=None,
            closeness=99,
            status="NO_CHARGER",
        )
