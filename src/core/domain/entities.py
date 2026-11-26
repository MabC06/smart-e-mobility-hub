"""Entities of the core domain (docs/design/structural/class-diagram-core.md, section 2).

Entities are plain dataclasses. ``version`` is the optimistic-locking counter (D-002); the
repository sets it, callers never bump it themselves. All times are timezone-aware UTC (D-005).
Hub counters (occupied, occupancy ratio) are derived from the spaces, not stored (NFR-07).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar

from core.domain.enums import (
    ChargingPointStatus,
    ClaimStatus,
    HolderKind,
    HubStatus,
    Ownership,
    ResourceType,
    Role,
    SpaceStatus,
    VehicleState,
    VehicleType,
)


def _require_aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware (UTC)")


@dataclass(slots=True)
class Hub:
    ID_FIELD: ClassVar[str] = "hub_id"

    hub_id: str
    name: str
    zone_code: str
    parking_capacity: int
    charging_point_count: int
    status: HubStatus = HubStatus.ACTIVE
    version: int = 1

    def __post_init__(self) -> None:
        if self.parking_capacity <= 0:
            raise ValueError("parking_capacity must be greater than 0")
        if not 0 <= self.charging_point_count <= self.parking_capacity:
            raise ValueError("charging_point_count must be between 0 and parking_capacity (D-007)")


@dataclass(slots=True)
class ParkingSpace:
    ID_FIELD: ClassVar[str] = "parking_space_id"

    parking_space_id: str
    hub_id: str
    label: str
    status: SpaceStatus = SpaceStatus.AVAILABLE
    occupant_vehicle_id: str | None = None
    version: int = 1


@dataclass(slots=True)
class ChargingPoint:
    ID_FIELD: ClassVar[str] = "charging_point_id"

    charging_point_id: str
    hub_id: str
    parking_space_id: str
    power_rate_kw: float
    status: ChargingPointStatus = ChargingPointStatus.AVAILABLE
    version: int = 1

    def __post_init__(self) -> None:
        if self.power_rate_kw <= 0:
            raise ValueError("power_rate_kw must be greater than 0")


@dataclass(slots=True)
class Vehicle:
    ID_FIELD: ClassVar[str] = "vehicle_id"

    vehicle_id: str
    plate_or_code: str
    ownership: Ownership
    vehicle_type: VehicleType
    battery_pct: float
    battery_capacity_kwh: float
    state: VehicleState = VehicleState.AVAILABLE
    fault_flag: bool = False
    hub_id: str | None = None
    parking_space_id: str | None = None
    owner_user_id: str | None = None
    connector_type: str | None = None
    version: int = 1

    def __post_init__(self) -> None:
        if not 0.0 <= self.battery_pct <= 100.0:
            raise ValueError("battery_pct must be between 0 and 100")
        if self.battery_capacity_kwh <= 0:
            raise ValueError("battery_capacity_kwh must be greater than 0")


@dataclass(slots=True)
class ResourceClaim:
    """The right to use a resource during [start_at, end_at) (BR-M1-01)."""

    ID_FIELD: ClassVar[str] = "claim_id"

    claim_id: str
    resource_type: ResourceType
    resource_id: str
    holder_kind: HolderKind
    holder_ref: str
    start_at: datetime
    end_at: datetime
    status: ClaimStatus = ClaimStatus.ACTIVE

    def __post_init__(self) -> None:
        _require_aware("start_at", self.start_at)
        _require_aware("end_at", self.end_at)
        if self.start_at >= self.end_at:
            raise ValueError("start_at must be before end_at")


@dataclass(slots=True)
class StateChangeRecord:
    """One entry of the state-change log (NFR-25)."""

    ID_FIELD: ClassVar[str] = "record_id"

    record_id: str
    at: datetime
    entity_type: str
    entity_id: str
    previous_state: str
    new_state: str
    trigger: str
    actor: str

    def __post_init__(self) -> None:
        _require_aware("at", self.at)


@dataclass(slots=True)
class DomainEvent:
    ID_FIELD: ClassVar[str] = "event_id"

    event_id: str
    type: str
    at: datetime
    payload: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_aware("at", self.at)


@dataclass(slots=True)
class UserAccount:
    ID_FIELD: ClassVar[str] = "user_id"

    user_id: str
    code: str
    role: Role
    is_active: bool = True
    password_hash: str | None = None  # salted hash, never the password (NFR-17)


type Versioned = Hub | ParkingSpace | ChargingPoint | Vehicle
type Entity = (
    Hub
    | ParkingSpace
    | ChargingPoint
    | Vehicle
    | ResourceClaim
    | StateChangeRecord
    | DomainEvent
    | UserAccount
)

VERSIONED_TYPES: tuple[type, ...] = (Hub, ParkingSpace, ChargingPoint, Vehicle)
CORE_TYPES: tuple[type, ...] = (
    Hub,
    ParkingSpace,
    ChargingPoint,
    Vehicle,
    ResourceClaim,
    StateChangeRecord,
    DomainEvent,
    UserAccount,
)


def entity_id(entity: Entity) -> str:
    return str(getattr(entity, type(entity).ID_FIELD))
