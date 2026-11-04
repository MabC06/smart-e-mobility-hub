"""Database schema of core (SQLAlchemy Core tables) and the mapping to the entities.

The database repeats the rules it can check by itself, so a bug cannot store a broken state:
foreign keys, uniqueness (one plate per vehicle, one vehicle per space, one charging point per
bay, D-007), value ranges and the pairing rules of a vehicle's location and owner. Rules that
need several rows (capacity, overlapping claims) stay with the InvariantChecker.

Times are stored as UTC and come back timezone-aware (D-005).
"""

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from core.domain.entities import (
    ChargingPoint,
    DomainEvent,
    Hub,
    ParkingSpace,
    ResourceClaim,
    StateChangeRecord,
    UserAccount,
    Vehicle,
)
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


class UtcDateTime(TypeDecorator[datetime]):
    """Stores a timezone-aware time as naive UTC and returns it as aware UTC."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("times must be timezone-aware (UTC)")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return None if value is None else value.replace(tzinfo=UTC)


metadata = MetaData()


def _in_values(table: str, column: str, enum: type[Enum]) -> CheckConstraint:
    values = ", ".join(f"'{member.value}'" for member in enum)
    return CheckConstraint(f"{column} IN ({values})", name=f"ck_{table}_{column}")


hubs = Table(
    "hubs",
    metadata,
    Column("hub_id", String, primary_key=True),
    Column("name", String, nullable=False, unique=True),
    Column("zone_code", String, nullable=False),
    Column("parking_capacity", Integer, nullable=False),
    Column("charging_point_count", Integer, nullable=False),
    Column("status", String, nullable=False),
    Column("version", Integer, nullable=False),
    CheckConstraint("parking_capacity > 0", name="ck_hubs_capacity"),
    CheckConstraint(
        "charging_point_count >= 0 AND charging_point_count <= parking_capacity",
        name="ck_hubs_charging_points",
    ),
    _in_values("hubs", "status", HubStatus),
)

user_accounts = Table(
    "user_accounts",
    metadata,
    Column("user_id", String, primary_key=True),
    Column("code", String, nullable=False, unique=True),
    Column("role", String, nullable=False),
    Column("is_active", Boolean, nullable=False),
    Column("password_hash", String, nullable=True),
    _in_values("user_accounts", "role", Role),
)

parking_spaces = Table(
    "parking_spaces",
    metadata,
    Column("parking_space_id", String, primary_key=True),
    Column("hub_id", String, ForeignKey("hubs.hub_id"), nullable=False),
    Column("label", String, nullable=False),
    Column("status", String, nullable=False),
    Column("occupant_vehicle_id", String, nullable=True),
    Column("version", Integer, nullable=False),
    UniqueConstraint("hub_id", "label", name="uq_parking_spaces_label"),
    _in_values("parking_spaces", "status", SpaceStatus),
)

charging_points = Table(
    "charging_points",
    metadata,
    Column("charging_point_id", String, primary_key=True),
    Column("hub_id", String, ForeignKey("hubs.hub_id"), nullable=False),
    Column(
        "parking_space_id",
        String,
        ForeignKey("parking_spaces.parking_space_id"),
        nullable=False,
        unique=True,
    ),
    Column("power_rate_kw", Float, nullable=False),
    Column("status", String, nullable=False),
    Column("version", Integer, nullable=False),
    CheckConstraint("power_rate_kw > 0", name="ck_charging_points_power"),
    _in_values("charging_points", "status", ChargingPointStatus),
)

vehicles = Table(
    "vehicles",
    metadata,
    Column("vehicle_id", String, primary_key=True),
    Column("plate_or_code", String, nullable=False, unique=True),
    Column("ownership", String, nullable=False),
    Column("vehicle_type", String, nullable=False),
    Column("battery_pct", Float, nullable=False),
    Column("battery_capacity_kwh", Float, nullable=False),
    Column("state", String, nullable=False),
    Column("fault_flag", Boolean, nullable=False),
    Column("hub_id", String, ForeignKey("hubs.hub_id"), nullable=True),
    Column(
        "parking_space_id",
        String,
        ForeignKey("parking_spaces.parking_space_id"),
        nullable=True,
        unique=True,
    ),
    Column("owner_user_id", String, ForeignKey("user_accounts.user_id"), nullable=True),
    Column("connector_type", String, nullable=True),
    Column("version", Integer, nullable=False),
    CheckConstraint("battery_pct >= 0 AND battery_pct <= 100", name="ck_vehicles_battery"),
    CheckConstraint("battery_capacity_kwh > 0", name="ck_vehicles_capacity"),
    CheckConstraint(
        "(hub_id IS NULL AND parking_space_id IS NULL)"
        " OR (hub_id IS NOT NULL AND parking_space_id IS NOT NULL)",
        name="ck_vehicles_location",
    ),
    CheckConstraint(
        "(ownership = 'PRIVATE' AND owner_user_id IS NOT NULL)"
        " OR (ownership = 'FLEET' AND owner_user_id IS NULL)",
        name="ck_vehicles_owner",
    ),
    _in_values("vehicles", "ownership", Ownership),
    _in_values("vehicles", "vehicle_type", VehicleType),
    _in_values("vehicles", "state", VehicleState),
)

resource_claims = Table(
    "resource_claims",
    metadata,
    Column("claim_id", String, primary_key=True),
    Column("resource_type", String, nullable=False),
    Column("resource_id", String, nullable=False),
    Column("holder_kind", String, nullable=False),
    Column("holder_ref", String, nullable=False),
    Column("start_at", UtcDateTime, nullable=False),
    Column("end_at", UtcDateTime, nullable=False),
    Column("status", String, nullable=False),
    CheckConstraint("start_at < end_at", name="ck_resource_claims_interval"),
    _in_values("resource_claims", "resource_type", ResourceType),
    _in_values("resource_claims", "holder_kind", HolderKind),
    _in_values("resource_claims", "status", ClaimStatus),
    Index("ix_resource_claims_resource", "resource_type", "resource_id"),
)

state_change_records = Table(
    "state_change_records",
    metadata,
    Column("record_id", String, primary_key=True),
    Column("at", UtcDateTime, nullable=False),
    Column("entity_type", String, nullable=False),
    Column("entity_id", String, nullable=False),
    Column("previous_state", String, nullable=False),
    Column("new_state", String, nullable=False),
    Column("trigger", String, nullable=False),
    Column("actor", String, nullable=False),
    Index("ix_state_change_records_entity", "entity_id"),
)

domain_events = Table(
    "domain_events",
    metadata,
    Column("event_id", String, primary_key=True),
    Column("type", String, nullable=False),
    Column("at", UtcDateTime, nullable=False),
    Column("payload", JSON, nullable=False),
)

# One row, "version": the commit counter. change_log: the commit counter at which each entity was
# last written, which is what ``unit_of_work(snapshot_version=...)`` compares against.
meta = Table(
    "meta",
    metadata,
    Column("key", String, primary_key=True),
    Column("value", Integer, nullable=False),
)

change_log = Table(
    "change_log",
    metadata,
    Column("entity_type", String, primary_key=True),
    Column("entity_id", String, primary_key=True),
    Column("version", Integer, nullable=False),
)


@dataclass(frozen=True, slots=True)
class TableSpec:
    entity: type
    table: Table
    id_column: str
    enums: Mapping[str, type[Enum]]
    versioned: bool


SPECS: dict[type, TableSpec] = {
    spec.entity: spec
    for spec in (
        TableSpec(Hub, hubs, "hub_id", {"status": HubStatus}, True),
        TableSpec(ParkingSpace, parking_spaces, "parking_space_id", {"status": SpaceStatus}, True),
        TableSpec(
            ChargingPoint,
            charging_points,
            "charging_point_id",
            {"status": ChargingPointStatus},
            True,
        ),
        TableSpec(
            Vehicle,
            vehicles,
            "vehicle_id",
            {"ownership": Ownership, "vehicle_type": VehicleType, "state": VehicleState},
            True,
        ),
        TableSpec(
            ResourceClaim,
            resource_claims,
            "claim_id",
            {"resource_type": ResourceType, "holder_kind": HolderKind, "status": ClaimStatus},
            False,
        ),
        TableSpec(StateChangeRecord, state_change_records, "record_id", {}, False),
        TableSpec(DomainEvent, domain_events, "event_id", {}, False),
        TableSpec(UserAccount, user_accounts, "user_id", {"role": Role}, False),
    )
}


def check_spec(spec: TableSpec) -> None:
    """Refuse a module's entity spec that cannot work. Raises ValueError that says what is wrong.

    A spec is valid when the entity is a dataclass whose ``ID_FIELD`` is the table's id column, the
    table has exactly one column per field, and ``versioned`` agrees with the entity's ``VERSIONED``
    flag (a versioned entity needs a ``version`` field). The class name must not be a core name,
    because the change log identifies entities by class name.
    """
    entity = spec.entity
    name = entity.__name__
    if not is_dataclass(entity):
        raise ValueError(f"{name} must be a dataclass")
    if name in {core.entity.__name__ for core in SPECS.values()}:
        raise ValueError(f"{name} is the name of a core entity; choose another class name")
    id_field = getattr(entity, "ID_FIELD", None)
    if id_field != spec.id_column or spec.id_column not in spec.table.c:
        raise ValueError(f"{name}: ID_FIELD must be the id column {spec.id_column!r} of the table")
    field_names = {f.name for f in fields(entity)}
    column_names = {c.name for c in spec.table.c}
    if field_names != column_names:
        raise ValueError(
            f"{name}: fields and columns differ "
            f"(only fields: {sorted(field_names - column_names)}, "
            f"only columns: {sorted(column_names - field_names)})"
        )
    if spec.versioned != (getattr(entity, "VERSIONED", False) is True):
        raise ValueError(f"{name}: versioned must match the class attribute VERSIONED")
    if spec.versioned and "version" not in field_names:
        raise ValueError(f"{name}: a versioned entity needs a 'version' field")
    for column in spec.enums:
        if column not in column_names:
            raise ValueError(f"{name}: enum column {column!r} is not in the table")


def add_spec(registry: dict[type, TableSpec], spec: TableSpec) -> bool:
    """Put a module's spec into a repository's registry. False when the same spec is already there.

    A different spec for the same class, or another class with the same name or table name, is a
    ValueError: two modules must not share a name by accident.
    """
    existing = registry.get(spec.entity)
    if existing is not None:
        if existing == spec:
            return False
        raise ValueError(f"{spec.entity.__name__} is already registered with another table")
    check_spec(spec)
    for other in registry.values():
        if other.entity.__name__ == spec.entity.__name__:
            raise ValueError(f"an entity named {spec.entity.__name__} is already registered")
        if other.table.name == spec.table.name:
            raise ValueError(
                f"table {spec.table.name!r} is already used by {other.entity.__name__}"
            )
    registry[spec.entity] = spec
    return True
