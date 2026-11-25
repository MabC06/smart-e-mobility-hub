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


class ParkingPurpose(StrEnum):
    RENTAL_RETURN = "RENTAL_RETURN"  # ten-minute hold for an open Trip (FR-05)
    PRIVATE_STAY = "PRIVATE_STAY"  # a student's own EV parks for a planned stay (FR-07 parking)


class ParkingStatus(StrEnum):
    CONFIRMED = "CONFIRMED"  # the space is held; nothing parked yet
    ACTIVE = "ACTIVE"  # a private EV arrived and occupies the space
    COMPLETED = "COMPLETED"  # the hold was used by a return, or the private EV left
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"  # nobody arrived before hold_expires_at


@dataclass(slots=True)
class ParkingBooking:
    """One held space of one Hub (UC-M2-06 to UC-M2-08). Core owns the claim and the space."""

    ID_FIELD: ClassVar[str] = "parking_id"
    VERSIONED: ClassVar[bool] = True

    parking_id: str
    user_id: str
    purpose: ParkingPurpose
    vehicle_id: str
    hub_id: str
    parking_space_id: str
    start_at: datetime
    hold_expires_at: datetime  # arrival deadline: start + 10 min
    claim_id: str
    planned_end_at: datetime | None = None  # private stay only
    trip_id: str | None = None  # rental return only
    status: ParkingStatus = ParkingStatus.CONFIRMED
    arrived_at: datetime | None = None
    departed_at: datetime | None = None
    version: int = 1
