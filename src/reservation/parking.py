"""M2 parking: a return-space hold for a Trip and a private EV's stay (FR-05, FR-07 parking).

UC-M2-06 reserves, UC-M2-07 cancels, UC-M2-08 arrives and departs. Core owns the space, its
claim and the vehicle; M2 owns the booking record. Every change is one Core unit of work, so an
error leaves the booking, the claim and the space as they were (NFR-09).

Rules (fr-02-05-07-reservation.md, section 3):
- RENTAL_RETURN_PARKING_HOLD: an open Trip may hold an empty space of its destination for 10 min,
  on a space with no other commitment; the return consumes it (BR-M2-10).
- PARKING_ADVANCE 24 h, PARKING_DURATION 30..240 min (default 120), PARKING_ARRIVAL [start,
  start + 10 min): no early arrival, at the deadline the booking expires.
- STUDENT_LIMITS: one live parking booking per student (BR-M2-03).
- Cancel releases only the claim; departure frees the space through Core (BR-M2-05, BR-M2-11).
- After the planned end a parked EV stays ACTIVE and occupied (overstay, BR-M2-15).
"""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from core.actor import Actor
from core.domain.entities import UserAccount
from core.domain.enums import (
    HolderKind,
    HubStatus,
    Ownership,
    ResourceType,
    Role,
    SpaceStatus,
    VehicleEvent,
    VehicleState,
)
from core.facade import CoreFacade
from core.repository.base import RepositoryError, VersionConflictError
from core.result import Err, Ok
from core.services.transition_ctx import TransitionCtx
from reservation import storage
from reservation.models import (
    ParkingBooking,
    ParkingPurpose,
    ParkingStatus,
    RentalReservation,
    RentalTrip,
    ReservationStatus,
    TripStatus,
)
from reservation.results import BookingError, BookingErrorCode, BookingResult, from_core

logger = logging.getLogger(__name__)

ARRIVAL_WINDOW = timedelta(minutes=10)
ADVANCE = timedelta(hours=24)
MIN_STAY, MAX_STAY, DEFAULT_STAY = 30, 240, 120  # minutes
LIVE = (ParkingStatus.CONFIRMED, ParkingStatus.ACTIVE)


def _error(code: BookingErrorCode, message: str) -> BookingError:
    return BookingError(code, message)


def _id_valid(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip() and len(value) <= 128


def live_return_hold(core: CoreFacade, trip_id: str, now: datetime) -> ParkingBooking | None:
    """The unexpired return hold of a Trip, if any (read inside the caller's transaction)."""
    for booking in storage.all_parkings(core):
        if (
            booking.trip_id == trip_id
            and booking.purpose is ParkingPurpose.RENTAL_RETURN
            and booking.status is ParkingStatus.CONFIRMED
            and now < booking.hold_expires_at
        ):
            return booking
    return None


class ParkingService:
    """Hold, use and release parking spaces for students through Core."""

    def __init__(self, core: CoreFacade) -> None:
        self.core = core

    # ------------------------------------------------------------------ commands

    def hold_return(
        self, parking_id: str, reservation_id: str, hub_id: str, actor: Actor
    ) -> BookingResult[ParkingBooking]:
        """Hold one empty space at the destination for the student's open Trip (10 min)."""
        if not all(_id_valid(v) for v in (parking_id, reservation_id, hub_id)):
            return _error(BookingErrorCode.INVALID_INPUT, "Invalid hold fields.")
        return self._execute(lambda: self._hold_return(parking_id, reservation_id, hub_id, actor))

    def reserve_private(
        self,
        parking_id: str,
        vehicle_id: str,
        hub_id: str,
        start_at: datetime | None,
        duration_minutes: int,
        actor: Actor,
    ) -> BookingResult[ParkingBooking]:
        """Book a space for the student's own EV from ``start_at`` (now when omitted)."""
        if (
            not all(_id_valid(v) for v in (parking_id, vehicle_id, hub_id))
            or type(duration_minutes) is not int
            or not MIN_STAY <= duration_minutes <= MAX_STAY
            or (start_at is not None and start_at.tzinfo is None)
        ):
            return _error(BookingErrorCode.INVALID_INPUT, "Invalid parking fields.")
        return self._execute(
            lambda: self._reserve_private(
                parking_id, vehicle_id, hub_id, start_at, duration_minutes, actor
            )
        )

    def arrive(
        self, parking_id: str, expected_version: int, actor: Actor
    ) -> BookingResult[ParkingBooking]:
        """The private EV parks in its held space (consumes the claim)."""
        return self._execute(lambda: self._arrive(parking_id, expected_version, actor))

    def depart(
        self, parking_id: str, expected_version: int, actor: Actor
    ) -> BookingResult[ParkingBooking]:
        """The private EV leaves; Core frees its space."""
        return self._execute(lambda: self._depart(parking_id, expected_version, actor))

    def cancel(self, parking_id: str, actor: Actor) -> BookingResult[ParkingBooking]:
        """Cancel an unused booking before its deadline; only the claim is released."""
        return self._execute(lambda: self._release(parking_id, actor))

    def expire_due(self) -> dict[str, BookingResult[ParkingBooking]]:
        """Expire each unused booking whose arrival deadline has passed."""
        now = self.core.queries.get_config().as_of
        ids = [
            booking.parking_id
            for booking in storage.all_parkings(self.core)
            if booking.status is ParkingStatus.CONFIRMED and booking.hold_expires_at <= now
        ]
        return {parking_id: self._expire(parking_id) for parking_id in ids}

    def _expire(self, parking_id: str) -> BookingResult[ParkingBooking]:
        return self._execute(lambda: self._release(parking_id, None))

    def sweep(self) -> None:
        """Expire unused bookings past their deadline; a failure is logged, never raised."""
        try:
            self.expire_due()
        except RepositoryError:
            logger.exception("Parking sweep failed; the next request tries again")

    def student_parkings(self, user_id: str) -> list[ParkingBooking]:
        """The student's parking bookings, newest first."""
        mine = [b for b in storage.all_parkings(self.core) if b.user_id == user_id]
        return sorted(mine, key=lambda b: b.start_at, reverse=True)

    # ------------------------------------------------------------------ helpers

    def _execute[T](self, operation: Callable[[], BookingResult[T]]) -> BookingResult[T]:
        try:
            return operation()
        except VersionConflictError:
            return _error(BookingErrorCode.CONFLICT, "A booking changed; read it again.")
        except RepositoryError:
            logger.exception("Parking persistence failed; transaction rolled back")
            return _error(BookingErrorCode.INTERNAL_ERROR, "Parking could not be saved.")

    def _student(self, actor: Actor) -> Actor | BookingError:
        account = self.core.get_entity(UserAccount, actor.user_id)
        if (
            actor.role is not Role.STUDENT
            or account is None
            or not account.is_active
            or account.role is not Role.STUDENT
        ):
            return _error(BookingErrorCode.FORBIDDEN, "An active student account is required.")
        return Actor(account.user_id, Role.STUDENT, "reservation")

    def _retry(self, parking_id: str, user_id: str) -> ParkingBooking | BookingError | None:
        """A repeated ID returns the stored booking to its owner; another owner sees 404."""
        existing = storage.read(self.core, ParkingBooking, parking_id)
        if existing is None:
            return None
        if existing.user_id != user_id:
            return _error(BookingErrorCode.NOT_FOUND_OR_NOT_OWNED, "Parking not found.")
        return existing

    def _quota_reached(self, user_id: str) -> bool:
        return any(
            b.user_id == user_id and b.status in LIVE for b in storage.all_parkings(self.core)
        )

    def _free_space(self, hub_id: str, start: datetime, end: datetime) -> str | BookingError:
        """Lowest empty space of an open Hub with no claim in [start, end).

        ``core.queries`` is the same query object as the open unit of work's.
        """
        hub = self.core.queries.get_hub(hub_id)
        if isinstance(hub, Err):
            return from_core(hub)
        if hub.value.status is HubStatus.MAINTENANCE:
            return _error(BookingErrorCode.RESOURCE_UNAVAILABLE, "The Hub is in maintenance.")
        for space in self.core.queries.list_spaces(hub_id, SpaceStatus.AVAILABLE):
            if not self.core.queries.get_claims(space.parking_space_id, start, end):
                return space.parking_space_id
        return _error(BookingErrorCode.NO_PARKING, "No free space at this Hub for that time.")

    def _hold(
        self, uow: Any, caller: Actor, booking: ParkingBooking, claim_end: datetime
    ) -> BookingResult[ParkingBooking]:
        """Place the space claim and store the CONFIRMED booking in the same unit of work.

        ``uow`` is the open ``core.unit_of_work()``; its class is internal to core (NFR-22).
        """
        claim = uow.commands.place_claim(
            ResourceType.SPACE,
            booking.parking_space_id,
            HolderKind.RESERVATION,
            booking.parking_id,
            booking.start_at,
            claim_end,
            caller,
        )
        if isinstance(claim, Err):
            return from_core(claim)
        booking.claim_id = claim.value.claim_id
        storage.add(uow.repository, booking)
        committed = uow.commit()
        return from_core(committed) if isinstance(committed, Err) else Ok(booking)

    # ------------------------------------------------------------------ transactions

    def _hold_return(
        self, parking_id: str, reservation_id: str, hub_id: str, actor: Actor
    ) -> BookingResult[ParkingBooking]:
        with self.core.unit_of_work() as uow:
            caller = self._student(actor)
            if isinstance(caller, BookingError):
                return caller
            retry = self._retry(parking_id, caller.user_id)
            if retry is not None:
                if isinstance(retry, ParkingBooking) and (
                    retry.trip_id != f"TRIP:{reservation_id}" or retry.hub_id != hub_id
                ):
                    return _error(BookingErrorCode.INVALID_INPUT, "Parking ID has other fields.")
                return retry if isinstance(retry, BookingError) else Ok(retry)
            booking = storage.read(self.core, RentalReservation, reservation_id)
            trip = storage.read(self.core, RentalTrip, f"TRIP:{reservation_id}")
            if booking is None or booking.user_id != caller.user_id or trip is None:
                return _error(BookingErrorCode.NOT_FOUND_OR_NOT_OWNED, "Trip not found.")
            if booking.status is not ReservationStatus.ACTIVE or trip.status not in (
                TripStatus.IN_PROGRESS,
                TripStatus.OVERDUE,
            ):
                return _error(BookingErrorCode.INVALID_STATE, "Only an open Trip can hold a space.")
            if self._quota_reached(caller.user_id):
                return _error(BookingErrorCode.LIMIT_REACHED, "One live parking per student.")
            now = uow.queries.get_config().as_of
            # No other commitment on the space: after the return the vehicle stays parked.
            space = self._free_space(hub_id, now, now + ADVANCE + timedelta(minutes=MAX_STAY))
            if isinstance(space, BookingError):
                return space
            hold = ParkingBooking(
                parking_id=parking_id,
                user_id=caller.user_id,
                purpose=ParkingPurpose.RENTAL_RETURN,
                vehicle_id=trip.vehicle_id,
                hub_id=hub_id,
                parking_space_id=space,
                start_at=now,
                hold_expires_at=now + ARRIVAL_WINDOW,
                claim_id="",
                trip_id=trip.trip_id,
            )
            return self._hold(uow, caller, hold, now + ARRIVAL_WINDOW)

    def _reserve_private(
        self,
        parking_id: str,
        vehicle_id: str,
        hub_id: str,
        start_at: datetime | None,
        duration_minutes: int,
        actor: Actor,
    ) -> BookingResult[ParkingBooking]:
        with self.core.unit_of_work() as uow:
            caller = self._student(actor)
            if isinstance(caller, BookingError):
                return caller
            retry = self._retry(parking_id, caller.user_id)
            if retry is not None:
                if isinstance(retry, ParkingBooking) and (
                    retry.vehicle_id != vehicle_id or retry.hub_id != hub_id
                ):
                    return _error(BookingErrorCode.INVALID_INPUT, "Parking ID has other fields.")
                return retry if isinstance(retry, BookingError) else Ok(retry)
            found = uow.queries.get_vehicle(vehicle_id)
            if (
                isinstance(found, Err)
                or found.value.ownership is not Ownership.PRIVATE
                or found.value.owner_user_id != caller.user_id
            ):
                return _error(BookingErrorCode.NOT_FOUND_OR_NOT_OWNED, "Vehicle not found.")
            if found.value.hub_id is not None:
                return _error(BookingErrorCode.INVALID_STATE, "The vehicle is already parked.")
            now = uow.queries.get_config().as_of
            start = now if start_at is None else start_at
            if not now <= start <= now + ADVANCE:
                return _error(BookingErrorCode.INVALID_INPUT, "Start must be within 24 hours.")
            if self._quota_reached(caller.user_id):
                return _error(BookingErrorCode.LIMIT_REACHED, "One live parking per student.")
            end = start + timedelta(minutes=duration_minutes)
            space = self._free_space(hub_id, start, end)
            if isinstance(space, BookingError):
                return space
            stay = ParkingBooking(
                parking_id=parking_id,
                user_id=caller.user_id,
                purpose=ParkingPurpose.PRIVATE_STAY,
                vehicle_id=vehicle_id,
                hub_id=hub_id,
                parking_space_id=space,
                start_at=start,
                hold_expires_at=start + ARRIVAL_WINDOW,
                claim_id="",
                planned_end_at=end,
            )
            return self._hold(uow, caller, stay, end)

    def _owned_private(
        self, parking_id: str, actor: Actor
    ) -> tuple[Actor, ParkingBooking] | BookingError:
        caller = self._student(actor)
        if isinstance(caller, BookingError):
            return caller
        booking = storage.read(self.core, ParkingBooking, parking_id)
        if booking is None or booking.user_id != caller.user_id:
            return _error(BookingErrorCode.NOT_FOUND_OR_NOT_OWNED, "Parking not found.")
        if booking.purpose is not ParkingPurpose.PRIVATE_STAY:
            return _error(BookingErrorCode.INVALID_STATE, "A return hold is used by the return.")
        return caller, booking

    def _arrive(
        self, parking_id: str, expected_version: int, actor: Actor
    ) -> BookingResult[ParkingBooking]:
        with self.core.unit_of_work() as uow:
            owned = self._owned_private(parking_id, actor)
            if isinstance(owned, BookingError):
                return owned
            caller, booking = owned
            if booking.status is not ParkingStatus.CONFIRMED:
                if booking.status in (ParkingStatus.ACTIVE, ParkingStatus.COMPLETED):
                    return Ok(booking)  # a repeated arrival returns the recorded outcome
                return _error(BookingErrorCode.INVALID_STATE, "This booking has ended.")
            now = uow.queries.get_config().as_of
            if now < booking.start_at:
                return _error(BookingErrorCode.INVALID_STATE, "Too early: the stay has not begun.")
            if now >= booking.hold_expires_at:
                return _error(BookingErrorCode.EXPIRED, "The arrival deadline has passed.")
            changed = uow.commands.transition_vehicle(
                booking.vehicle_id,
                VehicleEvent.ARRIVE,
                expected_version,
                caller,
                TransitionCtx(parking_space_id=booking.parking_space_id, claim_id=booking.claim_id),
            )
            if isinstance(changed, Err):
                return from_core(changed)
            booking.status = ParkingStatus.ACTIVE
            booking.arrived_at = now
            storage.update(uow.repository, booking)
            committed = uow.commit()
            return from_core(committed) if isinstance(committed, Err) else Ok(booking)

    def _depart(
        self, parking_id: str, expected_version: int, actor: Actor
    ) -> BookingResult[ParkingBooking]:
        with self.core.unit_of_work() as uow:
            owned = self._owned_private(parking_id, actor)
            if isinstance(owned, BookingError):
                return owned
            caller, booking = owned
            if booking.status is ParkingStatus.COMPLETED:
                return Ok(booking)
            if booking.status is not ParkingStatus.ACTIVE:
                return _error(BookingErrorCode.INVALID_STATE, "The vehicle has not arrived.")
            vehicle = uow.queries.get_vehicle(booking.vehicle_id)
            if isinstance(vehicle, Err):
                return from_core(vehicle)
            if vehicle.value.state is VehicleState.CHARGING:
                # Core refuses DEPART while charging; say why and what to do (NFR-21).
                return _error(
                    BookingErrorCode.INVALID_STATE,
                    "The vehicle is still charging. Finish charging on the Charging page, "
                    "then record your departure.",
                )
            changed = uow.commands.transition_vehicle(
                booking.vehicle_id, VehicleEvent.DEPART, expected_version, caller
            )
            if isinstance(changed, Err):
                return from_core(changed)
            booking.status = ParkingStatus.COMPLETED
            booking.departed_at = uow.queries.get_config().as_of
            storage.update(uow.repository, booking)
            committed = uow.commit()
            return from_core(committed) if isinstance(committed, Err) else Ok(booking)

    def _release(self, parking_id: str, actor: Actor | None) -> BookingResult[ParkingBooking]:
        """Cancel (an owner, before the deadline) or expire (``actor`` None, at the deadline)."""
        with self.core.unit_of_work() as uow:
            booking = storage.read(self.core, ParkingBooking, parking_id)
            if actor is not None:
                caller = self._student(actor)
                if isinstance(caller, BookingError):
                    return caller
                if booking is None or booking.user_id != caller.user_id:
                    return _error(BookingErrorCode.NOT_FOUND_OR_NOT_OWNED, "Parking not found.")
            if booking is None:
                return _error(BookingErrorCode.NOT_FOUND_OR_NOT_OWNED, "Parking not found.")
            if booking.status in (ParkingStatus.CANCELLED, ParkingStatus.EXPIRED):
                return Ok(booking)
            if booking.status is not ParkingStatus.CONFIRMED:
                return _error(BookingErrorCode.INVALID_STATE, "Only an unused booking ends here.")
            now = uow.queries.get_config().as_of
            expired = now >= booking.hold_expires_at
            if actor is None and not expired:
                return _error(BookingErrorCode.INVALID_STATE, "Booking is not due for expiry.")
            owner = Actor(booking.user_id, Role.STUDENT, "reservation")
            released = uow.commands.release_claim(booking.claim_id, owner)
            if isinstance(released, Err):
                return from_core(released)
            booking.status = ParkingStatus.EXPIRED if expired else ParkingStatus.CANCELLED
            storage.update(uow.repository, booking)
            committed = uow.commit()
            return from_core(committed) if isinstance(committed, Err) else Ok(booking)
