"""Read-only views returned to other modules. They never expose the stored objects.

Every view carries ``version`` (for ``expected_version`` in the next command) where the entity
is versioned; list results carry ``as_of`` through the query that built them.
"""

from dataclasses import dataclass
from datetime import datetime

from core.domain.entities import ChargingPoint, Hub, ParkingSpace, ResourceClaim, Vehicle
from core.domain.enums import (
    ChargingPointStatus,
    ClaimStatus,
    HolderKind,
    HubStatus,
    Ownership,
    ResourceType,
    SpaceStatus,
    VehicleState,
    VehicleType,
)


@dataclass(frozen=True, slots=True)
class HubView:
    hub_id: str
    name: str
    zone_code: str
    parking_capacity: int
    occupied: int
    free_spaces: int
    charging_points: int
    charging_in_use: int
    available_vehicles: int
    status: HubStatus
    version: int
    as_of: datetime


@dataclass(frozen=True, slots=True)
class VehicleView:
    vehicle_id: str
    plate_or_code: str
    ownership: Ownership
    vehicle_type: VehicleType
    battery_pct: float
    state: VehicleState
    fault_flag: bool
    hub_id: str | None
    parking_space_id: str | None
    owner_user_id: str | None
    connector_type: str | None
    version: int

    @classmethod
    def of(cls, vehicle: Vehicle) -> "VehicleView":
        return cls(
            vehicle_id=vehicle.vehicle_id,
            plate_or_code=vehicle.plate_or_code,
            ownership=vehicle.ownership,
            vehicle_type=vehicle.vehicle_type,
            battery_pct=vehicle.battery_pct,
            state=vehicle.state,
            fault_flag=vehicle.fault_flag,
            hub_id=vehicle.hub_id,
            parking_space_id=vehicle.parking_space_id,
            owner_user_id=vehicle.owner_user_id,
            connector_type=vehicle.connector_type,
            version=vehicle.version,
        )


@dataclass(frozen=True, slots=True)
class SpaceView:
    parking_space_id: str
    hub_id: str
    label: str
    status: SpaceStatus
    occupant_vehicle_id: str | None
    version: int

    @classmethod
    def of(cls, space: ParkingSpace) -> "SpaceView":
        return cls(
            parking_space_id=space.parking_space_id,
            hub_id=space.hub_id,
            label=space.label,
            status=space.status,
            occupant_vehicle_id=space.occupant_vehicle_id,
            version=space.version,
        )


@dataclass(frozen=True, slots=True)
class ChargingPointView:
    charging_point_id: str
    hub_id: str
    parking_space_id: str
    power_rate_kw: float
    status: ChargingPointStatus
    version: int

    @classmethod
    def of(cls, point: ChargingPoint) -> "ChargingPointView":
        return cls(
            charging_point_id=point.charging_point_id,
            hub_id=point.hub_id,
            parking_space_id=point.parking_space_id,
            power_rate_kw=point.power_rate_kw,
            status=point.status,
            version=point.version,
        )


@dataclass(frozen=True, slots=True)
class ClaimView:
    claim_id: str
    resource_type: ResourceType
    resource_id: str
    holder_kind: HolderKind
    holder_ref: str
    start_at: datetime
    end_at: datetime
    status: ClaimStatus

    @classmethod
    def of(cls, claim: ResourceClaim) -> "ClaimView":
        return cls(
            claim_id=claim.claim_id,
            resource_type=claim.resource_type,
            resource_id=claim.resource_id,
            holder_kind=claim.holder_kind,
            holder_ref=claim.holder_ref,
            start_at=claim.start_at,
            end_at=claim.end_at,
            status=claim.status,
        )


@dataclass(frozen=True, slots=True)
class HubStatusView:
    """Result of ``set_hub_status``; same numbers as ``HubView`` are available from the query."""

    hub_id: str
    status: HubStatus
    version: int

    @classmethod
    def of(cls, hub: Hub) -> "HubStatusView":
        return cls(hub.hub_id, hub.status, hub.version)


@dataclass(frozen=True, slots=True)
class VehicleFilter:
    hub_id: str | None = None
    state: VehicleState | None = None
    vehicle_type: VehicleType | None = None
    min_battery: float | None = None
    ownership: Ownership | None = None


@dataclass(frozen=True, slots=True)
class CoreConfigView:
    low_battery_threshold: float
    near_capacity_threshold: float
    as_of: datetime
