"""Description of a whole network, to load into an empty core with ``commands.load_network``.

The IoT simulator (M8) builds a ``NetworkSpec`` from the reference dataset (reference-dataset.md)
and hands it to core, so it never writes to storage itself (CONTRIBUTING 9.13). Core owns the
shape of the data; M8 owns the numbers.

IDs are derived from the Hub ID, so the same spec always gives the same network (NFR-13):
space ``H01-S001``, charging point ``H01-CP01`` (the bay of space ``H01-S001``). Fleet vehicles
are parked in the free spaces first and in the bays last, so charging bays stay free for charging.
"""

from dataclasses import dataclass

from core.domain.enums import Role, VehicleType
from core.errors import ErrorCode
from core.result import Err


def space_id(hub_id: str, number: int) -> str:
    return f"{hub_id}-S{number:03d}"


def charging_point_id(hub_id: str, number: int) -> str:
    return f"{hub_id}-CP{number:02d}"


@dataclass(frozen=True, slots=True)
class UserSpec:
    user_id: str
    code: str
    role: Role
    password_hash: str | None = None  # made with ``core.auth.hash_password``; None = cannot log in


@dataclass(frozen=True, slots=True)
class VehicleSpec:
    """A vehicle with an ``owner_user_id`` is private; without one it is a fleet vehicle."""

    vehicle_id: str
    plate_or_code: str
    vehicle_type: VehicleType
    battery_pct: float
    battery_capacity_kwh: float = 0.5
    owner_user_id: str | None = None
    connector_type: str | None = None


@dataclass(frozen=True, slots=True)
class HubSpec:
    hub_id: str
    name: str
    zone_code: str
    space_count: int
    charging_point_count: int
    power_rate_kw: float = 11.0
    vehicles: tuple[VehicleSpec, ...] = ()


@dataclass(frozen=True, slots=True)
class NetworkSpec:
    hubs: tuple[HubSpec, ...]
    users: tuple[UserSpec, ...] = ()
    private_vehicles: tuple[VehicleSpec, ...] = ()


@dataclass(frozen=True, slots=True)
class NetworkSummary:
    hubs: int
    parking_spaces: int
    charging_points: int
    vehicles: int
    users: int


def _bad(message: str) -> Err:
    return Err(ErrorCode.INVALID_INPUT, message)


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    return sorted({v for v in values if v in seen or seen.add(v)})  # type: ignore[func-returns-value]


def validate_network(spec: NetworkSpec) -> Err | None:
    """The rules that can be checked on the description alone."""
    if not spec.hubs:
        return _bad("a network needs at least one Hub")
    for label, values in (
        ("hub IDs", [h.hub_id for h in spec.hubs]),
        ("hub names", [h.name for h in spec.hubs]),
        ("user IDs", [u.user_id for u in spec.users]),
        ("user codes", [u.code for u in spec.users]),
    ):
        repeated = _duplicates(values)
        if repeated:
            return _bad(f"duplicate {label}: {repeated}")
    all_vehicles = [v for h in spec.hubs for v in h.vehicles] + list(spec.private_vehicles)
    for label, values in (
        ("vehicle IDs", [v.vehicle_id for v in all_vehicles]),
        ("plates or codes", [v.plate_or_code for v in all_vehicles]),
    ):
        repeated = _duplicates(values)
        if repeated:
            return _bad(f"duplicate {label}: {repeated}")
    for hub in spec.hubs:
        if hub.space_count < 1:
            return _bad(f"hub {hub.hub_id!r} needs at least one parking space")
        if not 0 <= hub.charging_point_count <= hub.space_count:
            return _bad(
                f"hub {hub.hub_id!r}: charging points ({hub.charging_point_count}) must be between "
                f"0 and the parking spaces ({hub.space_count}), D-007"
            )
        if len(hub.vehicles) > hub.space_count:
            return _bad(
                f"hub {hub.hub_id!r}: {len(hub.vehicles)} vehicles for {hub.space_count} spaces"
            )
        for vehicle in hub.vehicles:
            if vehicle.owner_user_id is not None:
                return _bad(
                    f"vehicle {vehicle.vehicle_id!r} is parked at a Hub, so it is a fleet vehicle"
                )
    owners = {u.user_id for u in spec.users}
    for vehicle in spec.private_vehicles:
        if vehicle.owner_user_id is None or not vehicle.connector_type:
            return _bad(
                f"private vehicle {vehicle.vehicle_id!r} needs an owner and a connector type"
            )
        if vehicle.owner_user_id not in owners:
            return _bad(
                f"private vehicle {vehicle.vehicle_id!r}: unknown owner {vehicle.owner_user_id!r}"
            )
    return None
