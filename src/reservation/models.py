"""M2-owned rental records; Core owns vehicles, spaces and claims (D-018)."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import ClassVar

from core.views import VehicleView

OVERDUE_GRACE = timedelta(minutes=60)  # BR-M2-15: an open Trip is OVERDUE after due + 60 min


class ReservationStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class TripStatus(StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    OVERDUE = "OVERDUE"
    INCIDENT_ABORTED = "INCIDENT_ABORTED"


@dataclass(frozen=True, slots=True)
class ReserveRequest:
    """A reservation resource ID identifies retries; it is not a command/result key.

    Reuse this ID and the same booking fields after a lost response. A new booking
    needs a new ID. ``expected_version`` is the observed Core Vehicle version.
    """

    reservation_id: str
    vehicle_id: str
    origin_hub_id: str
    expected_version: int
    destination_hub_id: str | None = None
    min_battery: float = 20.0
    planned_duration_minutes: int = 30


@dataclass(frozen=True, slots=True)
class VehicleSearch:
    """FR-02 result: rentable fleet vehicles at one Hub, best battery first, as of Core time."""

    hub_id: str
    as_of: datetime
    vehicles: list[VehicleView]


@dataclass(slots=True)
class RentalReservation:
    ID_FIELD: ClassVar[str] = "reservation_id"
    VERSIONED: ClassVar[bool] = True

    reservation_id: str
    user_id: str
    vehicle_id: str
    origin_hub_id: str
    destination_hub_id: str | None
    selected_min_battery: float
    planned_duration_minutes: int
    confirmed_at: datetime
    hold_expires_at: datetime
    claim_id: str
    status: ReservationStatus = ReservationStatus.CONFIRMED
    version: int = 1


@dataclass(slots=True)
class RentalTrip:
    ID_FIELD: ClassVar[str] = "trip_id"
    VERSIONED: ClassVar[bool] = True

    trip_id: str
    reservation_id: str
    user_id: str
    vehicle_id: str
    origin_hub_id: str
    picked_up_at: datetime
    expected_return_at: datetime
    status: TripStatus = TripStatus.IN_PROGRESS
    returned_at: datetime | None = None
    return_hub_id: str | None = None
    return_space_id: str | None = None
    version: int = 1
