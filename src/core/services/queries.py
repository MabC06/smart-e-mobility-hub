"""Read interface ``HubQueries`` (docs/design/architecture/core-api-spec.md, section 4).

Reads return the committed state, sorted by ID (NFR-13). In this single-process version a read
takes the same short lock as a command, so it never sees a half-finished unit of work.
"""

from collections import Counter
from datetime import datetime

from core.domain.claims import ClaimPolicy
from core.domain.entities import (
    ChargingPoint,
    Hub,
    ParkingSpace,
    ResourceClaim,
    StateChangeRecord,
    Vehicle,
)
from core.domain.enums import (
    ChargingPointStatus,
    ClaimStatus,
    Ownership,
    ResourceType,
    SpaceStatus,
    VehicleState,
)
from core.errors import ErrorCode
from core.result import Err, Ok, Result
from core.services.runtime import Runtime
from core.views import (
    ChargingPointView,
    ClaimView,
    CoreConfigView,
    HubView,
    SpaceView,
    VehicleFilter,
    VehicleView,
)


class HubQueries:
    def __init__(self, runtime: Runtime) -> None:
        self._rt = runtime

    def _hub_views(self, hubs: list[Hub]) -> list[HubView]:
        """Hub numbers for several Hubs with one read of each table, not one per Hub."""
        repo = self._rt.repo
        wanted = {hub.hub_id for hub in hubs}
        occupied: Counter[str] = Counter()
        free: Counter[str] = Counter()
        for space in repo.query(ParkingSpace, lambda s: s.hub_id in wanted):
            if space.status is SpaceStatus.OCCUPIED:
                occupied[space.hub_id] += 1
            elif space.status is SpaceStatus.AVAILABLE:
                free[space.hub_id] += 1
        points: Counter[str] = Counter()
        charging: Counter[str] = Counter()
        for point in repo.query(ChargingPoint, lambda p: p.hub_id in wanted):
            points[point.hub_id] += 1
            if point.status is ChargingPointStatus.CHARGING:
                charging[point.hub_id] += 1
        available: Counter[str] = Counter(
            v.hub_id
            for v in repo.query(
                Vehicle,
                lambda v: (
                    v.hub_id in wanted
                    and v.ownership is Ownership.FLEET  # a private EV is not for rent
                    and v.state is VehicleState.AVAILABLE
                ),
            )
            if v.hub_id is not None
        )
        as_of = self._rt.now()
        return [
            HubView(
                hub_id=hub.hub_id,
                name=hub.name,
                zone_code=hub.zone_code,
                parking_capacity=hub.parking_capacity,
                occupied=occupied[hub.hub_id],
                free_spaces=free[hub.hub_id],
                charging_points=points[hub.hub_id],
                charging_in_use=charging[hub.hub_id],
                available_vehicles=available[hub.hub_id],
                status=hub.status,
                version=hub.version,
                as_of=as_of,
            )
            for hub in hubs
        ]

    def list_hubs(self) -> list[HubView]:
        with self._rt.lock:
            return self._hub_views(self._rt.repo.query(Hub))

    def get_hub(self, hub_id: str) -> Result[HubView]:
        with self._rt.lock:
            hub = self._rt.repo.get(Hub, hub_id)
            if hub is None:
                return Err(ErrorCode.NOT_FOUND, f"unknown hub {hub_id!r}")
            return Ok(self._hub_views([hub])[0])

    def find_vehicles(self, vehicle_filter: VehicleFilter | None = None) -> list[VehicleView]:
        flt = vehicle_filter or VehicleFilter()

        def matches(v: Vehicle) -> bool:
            return (
                (flt.hub_id is None or v.hub_id == flt.hub_id)
                and (flt.state is None or v.state is flt.state)
                and (flt.vehicle_type is None or v.vehicle_type is flt.vehicle_type)
                and (flt.min_battery is None or v.battery_pct >= flt.min_battery)
                and (flt.ownership is None or v.ownership is flt.ownership)
            )

        with self._rt.lock:
            return [VehicleView.of(v) for v in self._rt.repo.query(Vehicle, matches)]

    def get_vehicle(self, vehicle_id: str) -> Result[VehicleView]:
        with self._rt.lock:
            vehicle = self._rt.repo.get(Vehicle, vehicle_id)
            if vehicle is None:
                return Err(ErrorCode.NOT_FOUND, f"unknown vehicle {vehicle_id!r}")
            return Ok(VehicleView.of(vehicle))

    def list_spaces(self, hub_id: str, status: SpaceStatus | None = None) -> list[SpaceView]:
        with self._rt.lock:
            spaces = self._rt.repo.query(
                ParkingSpace,
                lambda s: s.hub_id == hub_id and (status is None or s.status is status),
            )
            return [SpaceView.of(s) for s in spaces]

    def find_free_space(
        self,
        hub_id: str,
        start_at: datetime,
        end_at: datetime,
        charging_bay: bool | None = None,
    ) -> Result[SpaceView]:
        """The lowest-numbered space of the Hub that is free and has no ACTIVE claim in the window.

        The answer is repeatable (same ID for the same state). ``charging_bay`` limits the search to
        bays (True) or to ordinary spaces (False); None accepts both. Nothing is reserved: the
        caller places the claim, and ``place_claim`` still decides on a conflict.
        """
        invalid = ClaimPolicy.validate_interval(start_at, end_at)
        if invalid is not None:
            return invalid
        with self._rt.lock:
            repo = self._rt.repo
            if repo.get(Hub, hub_id) is None:
                return Err(ErrorCode.NOT_FOUND, f"unknown hub {hub_id!r}")
            bays = {
                p.parking_space_id for p in repo.query(ChargingPoint, lambda p: p.hub_id == hub_id)
            }
            held = {
                c.resource_id
                for c in repo.query(
                    ResourceClaim,
                    lambda c: (
                        c.status is ClaimStatus.ACTIVE
                        and c.resource_type is ResourceType.SPACE
                        and ClaimPolicy.overlaps(c.start_at, c.end_at, start_at, end_at)
                    ),
                )
            }
            for space in repo.query(
                ParkingSpace, lambda s: s.hub_id == hub_id and s.status is SpaceStatus.AVAILABLE
            ):
                if space.parking_space_id in held:
                    continue
                if charging_bay is not None and (space.parking_space_id in bays) != charging_bay:
                    continue
                return Ok(SpaceView.of(space))
        return Err(ErrorCode.HUB_FULL, f"hub {hub_id!r} has no free space in that window")

    def list_charging_points(
        self, hub_id: str, status: ChargingPointStatus | None = None
    ) -> list[ChargingPointView]:
        with self._rt.lock:
            points = self._rt.repo.query(
                ChargingPoint,
                lambda p: p.hub_id == hub_id and (status is None or p.status is status),
            )
            return [ChargingPointView.of(p) for p in points]

    def get_claims(self, resource_id: str, start_at: datetime, end_at: datetime) -> list[ClaimView]:
        """ACTIVE claims on the resource that overlap the window."""
        with self._rt.lock:
            claims = self._rt.repo.query(
                ResourceClaim,
                lambda c: (
                    c.resource_id == resource_id
                    and c.status is ClaimStatus.ACTIVE
                    and ClaimPolicy.overlaps(c.start_at, c.end_at, start_at, end_at)
                ),
            )
            return [ClaimView.of(c) for c in claims]

    def get_state_log(self, entity_id: str, limit: int | None = None) -> list[StateChangeRecord]:
        """The log of one entity, newest first (NFR-25)."""
        with self._rt.lock:
            records = self._rt.repo.query(StateChangeRecord, lambda r: r.entity_id == entity_id)
        records.sort(key=lambda r: (r.at, r.record_id), reverse=True)
        return records if limit is None else records[:limit]

    def get_config(self) -> CoreConfigView:
        config = self._rt.config
        return CoreConfigView(
            low_battery_threshold=config.low_battery_threshold,
            near_capacity_threshold=config.near_capacity_threshold,
            as_of=self._rt.now(),
        )
