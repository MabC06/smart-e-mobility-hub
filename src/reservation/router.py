"""Student booking API. Identity and role always come from Core (D-023).

Every route checks the student, then runs the lifecycle sweep, so due bookings
expire and late Trips become OVERDUE before the request reads or changes anything
(D-017, BR-M2-15).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from core.api.security import Principal, acting_as, require_student
from core.domain.enums import VehicleType
from core.facade import CoreFacade
from core.repository.base import RepositoryError
from core.result import Err
from reservation import storage
from reservation.lifecycle import RentalLifecycle
from reservation.models import (
    ParkingBooking,
    RentalReservation,
    RentalTrip,
    ReserveRequest,
    VehicleSearch,
)
from reservation.parking import DEFAULT_STAY, LIVE, ParkingService
from reservation.results import BookingError, BookingErrorCode, BookingResult
from reservation.service import BookingService

Student = Annotated[Principal, Depends(require_student)]


class ReserveIn(BaseModel):
    reservation_id: str
    vehicle_id: str
    origin_hub_id: str
    expected_version: int = Field(strict=True)
    destination_hub_id: str | None = None
    min_battery: float = Field(default=20.0, strict=True)
    planned_duration_minutes: int = Field(default=30, strict=True)


class PickupIn(BaseModel):
    origin_hub_id: str
    expected_version: int = Field(strict=True)


class ReturnIn(BaseModel):
    destination_hub_id: str
    expected_version: int = Field(strict=True)


class ReturnHoldIn(BaseModel):
    parking_id: str
    destination_hub_id: str


class ParkingIn(BaseModel):
    parking_id: str
    vehicle_id: str
    hub_id: str
    start_at: datetime | None = None  # now when omitted; must carry a time zone
    duration_minutes: int = Field(default=DEFAULT_STAY, strict=True)


class VersionIn(BaseModel):
    expected_version: int = Field(strict=True)


@dataclass(frozen=True, slots=True)
class StudentRentals:
    bookings: list[RentalReservation]
    open_trips: list[RentalTrip]
    vehicle_versions: dict[str, int]
    parking: list[ParkingBooking]


_HTTP_STATUS = {
    BookingErrorCode.INVALID_INPUT: 400,
    BookingErrorCode.FORBIDDEN: 403,
    BookingErrorCode.NOT_FOUND_OR_NOT_OWNED: 404,
    BookingErrorCode.LIMIT_REACHED: 409,
    BookingErrorCode.CONFLICT: 409,
    BookingErrorCode.INVALID_STATE: 409,
    BookingErrorCode.EXPIRED: 409,
    BookingErrorCode.RESOURCE_UNAVAILABLE: 409,
    BookingErrorCode.NO_PARKING: 409,
    BookingErrorCode.INTERNAL_ERROR: 500,
}


def _value[T](result: BookingResult[T]) -> T:
    if isinstance(result, BookingError):
        raise HTTPException(
            _HTTP_STATUS[result.code], {"code": result.code.value, "message": result.message}
        )
    return result.value


def create_router(
    core: CoreFacade,
    service: BookingService,
    lifecycle: RentalLifecycle,
    parking: ParkingService,
) -> APIRouter:
    """Mount the M2 operations with Core's authenticated student dependency."""
    router = APIRouter(prefix="/reservations", tags=["reservation"])

    def swept_student(who: Student) -> Principal:
        """The checked student, after due bookings expired and late Trips were marked."""
        lifecycle.sweep()
        parking.sweep()
        return who

    Caller = Annotated[Principal, Depends(swept_student)]

    @router.get("/vehicles")
    def search(
        who: Caller,
        hub_id: str,
        vehicle_type: Annotated[VehicleType | None, Query(alias="type")] = None,
        min_battery: Annotated[float, Query(ge=0, le=100)] = 20.0,
    ) -> VehicleSearch:
        return _value(
            service.search(hub_id, vehicle_type, min_battery, acting_as(who, "reservation"))
        )

    @router.post("/parking")
    def reserve_parking(body: ParkingIn, who: Caller) -> ParkingBooking:
        return _value(
            parking.reserve_private(
                body.parking_id,
                body.vehicle_id,
                body.hub_id,
                body.start_at,
                body.duration_minutes,
                acting_as(who, "reservation"),
            )
        )

    @router.post("/parking/{parking_id}/arrive")
    def arrive(parking_id: str, body: VersionIn, who: Caller) -> ParkingBooking:
        actor = acting_as(who, "reservation")
        return _value(parking.arrive(parking_id, body.expected_version, actor))

    @router.post("/parking/{parking_id}/depart")
    def depart(parking_id: str, body: VersionIn, who: Caller) -> ParkingBooking:
        actor = acting_as(who, "reservation")
        return _value(parking.depart(parking_id, body.expected_version, actor))

    @router.post("/parking/{parking_id}/cancel")
    def cancel_parking(parking_id: str, who: Caller) -> ParkingBooking:
        return _value(parking.cancel(parking_id, acting_as(who, "reservation")))

    @router.post("/{reservation_id}/return-hold")
    def hold_return(reservation_id: str, body: ReturnHoldIn, who: Caller) -> ParkingBooking:
        actor = acting_as(who, "reservation")
        return _value(
            parking.hold_return(body.parking_id, reservation_id, body.destination_hub_id, actor)
        )

    @router.post("")
    def reserve(body: ReserveIn, who: Caller) -> RentalReservation:
        return _value(
            service.reserve(ReserveRequest(**body.model_dump()), acting_as(who, "reservation"))
        )

    @router.get("/mine")
    def mine(who: Caller, response: Response) -> StudentRentals:
        actor = acting_as(who, "reservation")
        response.headers["Cache-Control"] = "no-store"
        try:
            # An uncommitted read boundary gives the UI one view of bookings,
            # open trips and the vehicle versions for its next commands.
            with core.unit_of_work() as uow:
                bookings, open_trips = storage.student_records(core, actor.user_id)
                parkings = parking.student_parkings(actor.user_id)
                vehicle_versions: dict[str, int] = {}
                ids = {record.vehicle_id for record in bookings}
                ids.update(trip.vehicle_id for trip in open_trips)
                ids.update(stay.vehicle_id for stay in parkings if stay.status in LIVE)
                for vehicle_id in sorted(ids):
                    vehicle = uow.queries.get_vehicle(vehicle_id)
                    if not isinstance(vehicle, Err):
                        vehicle_versions[vehicle_id] = vehicle.value.version
                return StudentRentals(bookings, open_trips, vehicle_versions, parkings)
        except RepositoryError:
            raise HTTPException(
                503,
                {
                    "code": BookingErrorCode.INTERNAL_ERROR.value,
                    "message": "Could not read bookings.",
                },
            ) from None

    @router.post("/{reservation_id}/pickup")
    def pickup(reservation_id: str, body: PickupIn, who: Caller) -> RentalTrip:
        return _value(
            service.pickup(
                reservation_id,
                body.origin_hub_id,
                body.expected_version,
                acting_as(who, "reservation"),
            )
        )

    @router.post("/{reservation_id}/cancel")
    def cancel(reservation_id: str, who: Caller) -> RentalReservation:
        return _value(lifecycle.cancel(reservation_id, acting_as(who, "reservation")))

    @router.post("/{reservation_id}/return")
    def return_vehicle(reservation_id: str, body: ReturnIn, who: Caller) -> RentalTrip:
        return _value(
            service.return_trip(
                f"TRIP:{reservation_id}",
                body.destination_hub_id,
                body.expected_version,
                acting_as(who, "reservation"),
            )
        )

    return router
