"""Register M2 tables in Core's store; never open a second transaction.

Core v1.1 accepts registered dataclasses at runtime, but its Entity type alias
still lists only built-in entities. Casts here bridge that annotation limitation
in one place; check_spec validates the real models when they are registered.
"""

from typing import cast

from sqlalchemy import CheckConstraint, Column, Float, ForeignKey, Integer, String, Table

from core.domain.entities import Entity
from core.facade import CoreFacade
from core.repository.base import Repository
from core.repository.schema import TableSpec, UtcDateTime, metadata
from reservation.models import RentalReservation, RentalTrip, ReservationStatus, TripStatus

reservations = Table(
    "rental_reservations",
    metadata,
    Column("reservation_id", String, primary_key=True),
    Column("user_id", String, ForeignKey("user_accounts.user_id"), nullable=False),
    Column("vehicle_id", String, ForeignKey("vehicles.vehicle_id"), nullable=False),
    Column("origin_hub_id", String, ForeignKey("hubs.hub_id"), nullable=False),
    Column("destination_hub_id", String, ForeignKey("hubs.hub_id")),
    Column("selected_min_battery", Float, nullable=False),
    Column("planned_duration_minutes", Integer, nullable=False),
    Column("confirmed_at", UtcDateTime, nullable=False),
    Column("hold_expires_at", UtcDateTime, nullable=False),
    Column("claim_id", String, ForeignKey("resource_claims.claim_id"), nullable=False, unique=True),
    Column("status", String, nullable=False),
    Column("version", Integer, nullable=False),
    CheckConstraint("selected_min_battery BETWEEN 0 AND 100"),
    CheckConstraint("planned_duration_minutes BETWEEN 5 AND 120"),
    CheckConstraint("confirmed_at < hold_expires_at"),
    CheckConstraint("status IN ('CONFIRMED','ACTIVE','COMPLETED','CANCELLED','EXPIRED')"),
)
trips = Table(
    "rental_trips",
    metadata,
    Column("trip_id", String, primary_key=True),
    Column(
        "reservation_id",
        String,
        ForeignKey("rental_reservations.reservation_id"),
        nullable=False,
        unique=True,
    ),
    Column("user_id", String, ForeignKey("user_accounts.user_id"), nullable=False),
    Column("vehicle_id", String, ForeignKey("vehicles.vehicle_id"), nullable=False),
    Column("origin_hub_id", String, ForeignKey("hubs.hub_id"), nullable=False),
    Column("picked_up_at", UtcDateTime, nullable=False),
    Column("expected_return_at", UtcDateTime, nullable=False),
    Column("status", String, nullable=False),
    Column("returned_at", UtcDateTime),
    Column("return_hub_id", String, ForeignKey("hubs.hub_id")),
    Column("return_space_id", String, ForeignKey("parking_spaces.parking_space_id")),
    Column("version", Integer, nullable=False),
    CheckConstraint("picked_up_at < expected_return_at"),
    CheckConstraint("status IN ('IN_PROGRESS','COMPLETED','OVERDUE','INCIDENT_ABORTED')"),
    CheckConstraint(
        "(returned_at IS NULL AND return_hub_id IS NULL AND return_space_id IS NULL) OR "
        "(returned_at IS NOT NULL AND return_hub_id IS NOT NULL AND return_space_id IS NOT NULL)"
    ),
)
RESERVATION_SPEC = TableSpec(
    RentalReservation, reservations, "reservation_id", {"status": ReservationStatus}, True
)
TRIP_SPEC = TableSpec(RentalTrip, trips, "trip_id", {"status": TripStatus}, True)


def register_tables(core: CoreFacade) -> None:
    """Register both tables once; repeating the same specs is safe."""
    core.register_entity(RESERVATION_SPEC)
    core.register_entity(TRIP_SPEC)


def read[E: (RentalReservation, RentalTrip)](
    core: CoreFacade, entity_type: type[E], entity_id: str
) -> E | None:
    """Read a detached M2 record under Core's lock."""
    return cast(E | None, core.get_entity(cast(type[Entity], entity_type), entity_id))


def all_reservations(core: CoreFacade) -> list[RentalReservation]:
    """Read bookings in ID order for the serialized per-user quota check."""
    return cast(list[RentalReservation], core.query_entities(cast(type[Entity], RentalReservation)))


def add(repo: Repository, entity: RentalReservation | RentalTrip) -> None:
    """Insert an M2 record using the caller's open unit of work."""
    repo.add(cast(Entity, entity))


def update(repo: Repository, entity: RentalReservation | RentalTrip) -> None:
    """Write an M2 record using its observed version in the caller's unit of work."""
    repo.update(cast(Entity, entity), entity.version)
