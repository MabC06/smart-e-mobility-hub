"""Rental booking happy path against real Core (FR-03/04, D-015/D-018).

Each operation reads M2 records before any Core mutation and holds Core's unit
of work for quota checks and all writes. Concurrent retries therefore reread the
winner's record before checking a now-stale vehicle version. No result cache or
module-private transaction is used. Callers supply an authenticated Actor; this
service rechecks the active account and never accepts an actor's module privilege.
"""

import logging
from collections.abc import Callable
from datetime import timedelta
from math import isfinite

from core.actor import Actor
from core.domain.entities import UserAccount
from core.domain.enums import (
    HolderKind,
    HubStatus,
    Ownership,
    ResourceType,
    Role,
    VehicleEvent,
    VehicleState,
)
from core.facade import CoreFacade
from core.repository.base import RepositoryError, VersionConflictError
from core.result import Err, Ok
from core.services.transition_ctx import TransitionCtx
from reservation import storage
from reservation.models import (
    RentalReservation,
    RentalTrip,
    ReservationStatus,
    ReserveRequest,
    TripStatus,
)
from reservation.results import BookingError, BookingErrorCode, BookingResult, from_core

logger = logging.getLogger(__name__)
HOLD_MINUTES = 10
RENTAL_MIN_BATTERY = 20.0


def _id_valid(value: str) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip() and len(value) <= 128


def _version_valid(value: int) -> bool:
    return type(value) is int and value > 0


def _error(code: BookingErrorCode, message: str) -> BookingError:
    return BookingError(code, message)


class BookingService:
    """Own Reservation/Trip workflow while delegating shared state to Core."""

    def __init__(self, core: CoreFacade) -> None:
        self.core = core

    def _execute[T](self, operation: Callable[[], BookingResult[T]]) -> BookingResult[T]:
        try:
            return operation()
        except VersionConflictError:
            return _error(BookingErrorCode.CONFLICT, "A booking changed; read it again.")
        except RepositoryError:
            # The unit-of-work context has already rolled back before this handler.
            logger.exception("Booking persistence failed; transaction rolled back")
            return _error(BookingErrorCode.INTERNAL_ERROR, "Booking could not be saved.")

    def _actor(self, actor: Actor) -> Actor | BookingError:
        account = self.core.get_entity(UserAccount, actor.user_id)
        if (
            actor.role is not Role.STUDENT
            or account is None
            or not account.is_active
            or account.role is not Role.STUDENT
        ):
            return _error(BookingErrorCode.FORBIDDEN, "An active student account is required.")
        return Actor(account.user_id, Role.STUDENT, "reservation")

    def reserve(self, request: ReserveRequest, actor: Actor) -> BookingResult[RentalReservation]:
        """Confirm a ten-minute vehicle hold; retain its occupied origin space.

        Verifies intent fields on a retry of the same reservation resource ID.
        The planned destination is advisory and does not create a parking hold.
        """
        if (
            not all(
                _id_valid(v)
                for v in (request.reservation_id, request.vehicle_id, request.origin_hub_id)
            )
            or (
                request.destination_hub_id is not None and not _id_valid(request.destination_hub_id)
            )
            or not _version_valid(request.expected_version)
            or type(request.planned_duration_minutes) is not int
            or not 5 <= request.planned_duration_minutes <= 120
            or isinstance(request.min_battery, bool)
            or not isinstance(request.min_battery, (int, float))
            or not isfinite(request.min_battery)
            or not 0 <= request.min_battery <= 100
        ):
            return _error(BookingErrorCode.INVALID_INPUT, "Invalid booking fields.")
        return self._execute(lambda: self._reserve(request, actor))

    def _reserve(self, request: ReserveRequest, actor: Actor) -> BookingResult[RentalReservation]:
        with self.core.unit_of_work() as uow:
            caller = self._actor(actor)
            if isinstance(caller, BookingError):
                return caller
            existing = storage.read(self.core, RentalReservation, request.reservation_id)
            if existing is not None:
                if existing.user_id != caller.user_id:
                    return _error(BookingErrorCode.NOT_FOUND_OR_NOT_OWNED, "Booking not found.")
                if (
                    existing.vehicle_id != request.vehicle_id
                    or existing.origin_hub_id != request.origin_hub_id
                    or existing.destination_hub_id != request.destination_hub_id
                    or existing.selected_min_battery != request.min_battery
                    or existing.planned_duration_minutes != request.planned_duration_minutes
                ):
                    return _error(
                        BookingErrorCode.INVALID_INPUT, "Booking ID has different fields."
                    )
                return Ok(existing)
            if any(
                b.user_id == caller.user_id
                and b.status in (ReservationStatus.CONFIRMED, ReservationStatus.ACTIVE)
                for b in storage.all_reservations(self.core)
            ):
                return _error(BookingErrorCode.LIMIT_REACHED, "One live rental per student.")
            origin = uow.queries.get_hub(request.origin_hub_id)
            if isinstance(origin, Err):
                return from_core(origin)
            if origin.value.status is HubStatus.MAINTENANCE:
                return _error(BookingErrorCode.RESOURCE_UNAVAILABLE, "Origin is in maintenance.")
            if request.destination_hub_id is not None:
                destination = uow.queries.get_hub(request.destination_hub_id)
                if isinstance(destination, Err):
                    return from_core(destination)
            found = uow.queries.get_vehicle(request.vehicle_id)
            if isinstance(found, Err):
                return from_core(found)
            vehicle = found.value
            config = uow.queries.get_config()
            if vehicle.version != request.expected_version:
                return _error(BookingErrorCode.CONFLICT, "Vehicle changed; refresh selection.")
            if (
                vehicle.ownership is not Ownership.FLEET
                or vehicle.state is not VehicleState.AVAILABLE
                or vehicle.hub_id != request.origin_hub_id
                or vehicle.parking_space_id is None
                or vehicle.fault_flag
                or vehicle.battery_pct < max(RENTAL_MIN_BATTERY, request.min_battery)
                or vehicle.battery_pct <= config.low_battery_threshold
            ):
                return _error(BookingErrorCode.RESOURCE_UNAVAILABLE, "Vehicle is not eligible.")
            now = config.as_of
            expiry = now + timedelta(minutes=HOLD_MINUTES)
            claim = uow.commands.place_claim(
                ResourceType.VEHICLE,
                vehicle.vehicle_id,
                HolderKind.RESERVATION,
                request.reservation_id,
                now,
                expiry,
                caller,
            )
            if isinstance(claim, Err):
                return from_core(claim)
            changed = uow.commands.transition_vehicle(
                vehicle.vehicle_id,
                VehicleEvent.RESERVE,
                request.expected_version,
                caller,
                TransitionCtx(
                    claim_id=claim.value.claim_id,
                    min_battery=max(RENTAL_MIN_BATTERY, request.min_battery),
                ),
            )
            if isinstance(changed, Err):
                return from_core(changed)
            booking = RentalReservation(
                request.reservation_id,
                caller.user_id,
                vehicle.vehicle_id,
                request.origin_hub_id,
                request.destination_hub_id,
                request.min_battery,
                request.planned_duration_minutes,
                now,
                expiry,
                claim.value.claim_id,
            )
            storage.add(uow.repository, booking)
            committed = uow.commit()
            return from_core(committed) if isinstance(committed, Err) else Ok(booking)

    def pickup(
        self, reservation_id: str, origin_hub_id: str, expected_version: int, actor: Actor
    ) -> BookingResult[RentalTrip]:
        """Start exactly one Trip before expiry; free origin and release M2's claim."""
        if not all(_id_valid(v) for v in (reservation_id, origin_hub_id)) or not _version_valid(
            expected_version
        ):
            return _error(BookingErrorCode.INVALID_INPUT, "Invalid pickup fields.")
        return self._execute(
            lambda: self._pickup(reservation_id, origin_hub_id, expected_version, actor)
        )

    def _pickup(
        self, reservation_id: str, origin_hub_id: str, expected_version: int, actor: Actor
    ) -> BookingResult[RentalTrip]:
        with self.core.unit_of_work() as uow:
            caller = self._actor(actor)
            if isinstance(caller, BookingError):
                return caller
            booking = storage.read(self.core, RentalReservation, reservation_id)
            if booking is None or booking.user_id != caller.user_id:
                return _error(BookingErrorCode.NOT_FOUND_OR_NOT_OWNED, "Booking not found.")
            if booking.origin_hub_id != origin_hub_id:
                return _error(BookingErrorCode.INVALID_INPUT, "Pickup must use the booked origin.")
            # One deterministic business ID per reservation; SQL also enforces uniqueness.
            trip_id = f"TRIP:{reservation_id}"
            existing = storage.read(self.core, RentalTrip, trip_id)
            if existing is not None:
                return Ok(existing)
            if booking.status is not ReservationStatus.CONFIRMED:
                return _error(BookingErrorCode.INVALID_STATE, "Booking is not confirmed.")
            config = uow.queries.get_config()
            now = config.as_of
            if now >= booking.hold_expires_at:
                # D-017: expiry maintenance is a separate M2 lifecycle operation (Phase 3).
                return _error(BookingErrorCode.EXPIRED, "Pickup deadline has passed.")
            found = uow.queries.get_vehicle(booking.vehicle_id)
            if isinstance(found, Err):
                return from_core(found)
            vehicle = found.value
            if vehicle.version != expected_version:
                return _error(BookingErrorCode.CONFLICT, "Vehicle changed; refresh pickup.")
            if (
                vehicle.ownership is not Ownership.FLEET
                or vehicle.state is not VehicleState.RESERVED
                or vehicle.hub_id != origin_hub_id
                or vehicle.parking_space_id is None
                or vehicle.fault_flag
                or vehicle.battery_pct < max(RENTAL_MIN_BATTERY, booking.selected_min_battery)
                or vehicle.battery_pct <= config.low_battery_threshold
            ):
                return _error(BookingErrorCode.RESOURCE_UNAVAILABLE, "Vehicle is not eligible.")
            changed = uow.commands.transition_vehicle(
                booking.vehicle_id,
                VehicleEvent.PICKUP,
                expected_version,
                caller,
                TransitionCtx(claim_id=booking.claim_id),
            )
            if isinstance(changed, Err):
                return from_core(changed)
            released = uow.commands.release_claim(booking.claim_id, caller)
            if isinstance(released, Err):
                return from_core(released)
            trip = RentalTrip(
                trip_id,
                reservation_id,
                caller.user_id,
                booking.vehicle_id,
                origin_hub_id,
                now,
                now + timedelta(minutes=booking.planned_duration_minutes),
            )
            storage.add(uow.repository, trip)
            booking.status = ReservationStatus.ACTIVE
            storage.update(uow.repository, booking)
            committed = uow.commit()
            return from_core(committed) if isinstance(committed, Err) else Ok(trip)

    def return_trip(
        self, trip_id: str, destination_hub_id: str, expected_version: int, actor: Actor
    ) -> BookingResult[RentalTrip]:
        """End an owned Trip at an available Hub space, or leave the whole Trip open.

        Uses Core's safe destination selection, including future space claims.
        Return-parking holds and alternative-Hub ranking are Phase 3 integrations.
        """
        if not _id_valid(destination_hub_id) or not trip_id or not _version_valid(expected_version):
            return _error(BookingErrorCode.INVALID_INPUT, "Invalid return fields.")
        return self._execute(
            lambda: self._return_trip(trip_id, destination_hub_id, expected_version, actor)
        )

    def _return_trip(
        self, trip_id: str, destination_hub_id: str, expected_version: int, actor: Actor
    ) -> BookingResult[RentalTrip]:
        with self.core.unit_of_work() as uow:
            caller = self._actor(actor)
            if isinstance(caller, BookingError):
                return caller
            trip = storage.read(self.core, RentalTrip, trip_id)
            if trip is None or trip.user_id != caller.user_id:
                return _error(BookingErrorCode.NOT_FOUND_OR_NOT_OWNED, "Trip not found.")
            if trip.status in (TripStatus.COMPLETED, TripStatus.INCIDENT_ABORTED):
                if trip.return_hub_id != destination_hub_id:
                    return _error(BookingErrorCode.INVALID_INPUT, "Trip ended at a different Hub.")
                return Ok(trip)
            booking = storage.read(self.core, RentalReservation, trip.reservation_id)
            if booking is None or booking.status is not ReservationStatus.ACTIVE:
                return _error(BookingErrorCode.INVALID_STATE, "Rental is not active.")
            found = uow.queries.get_vehicle(trip.vehicle_id)
            if isinstance(found, Err):
                return from_core(found)
            vehicle = found.value
            now = uow.queries.get_config().as_of
            event = VehicleEvent.RETURN_FAULTY if vehicle.fault_flag else VehicleEvent.RETURN
            changed = uow.commands.transition_vehicle(
                trip.vehicle_id,
                event,
                expected_version,
                caller,
                TransitionCtx(hub_id=destination_hub_id),
            )
            if isinstance(changed, Err):
                return from_core(changed)
            trip.status = (
                TripStatus.INCIDENT_ABORTED if vehicle.fault_flag else TripStatus.COMPLETED
            )
            trip.returned_at = now
            trip.return_hub_id = changed.value.hub_id
            trip.return_space_id = changed.value.parking_space_id
            booking.status = ReservationStatus.COMPLETED
            storage.update(uow.repository, trip)
            storage.update(uow.repository, booking)
            committed = uow.commit()
            return from_core(committed) if isinstance(committed, Err) else Ok(trip)
