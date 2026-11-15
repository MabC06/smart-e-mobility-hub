"""M2-owned rental cancellation and expiry (D-017, UC-M2-03).

The expiry sweep is an explicit application-maintenance entry point. It does not
trust a client clock and never expires active Trips. Each booking is settled in
one Core unit of work; an error leaves that booking and its resources unchanged.
"""

import logging

from core.actor import Actor
from core.domain.entities import ResourceClaim, UserAccount
from core.domain.enums import (
    ClaimStatus,
    HolderKind,
    ResourceType,
    Role,
    VehicleEvent,
    VehicleState,
)
from core.facade import CoreFacade
from core.repository.base import RepositoryError
from core.result import Err, Ok
from reservation import storage
from reservation.models import RentalReservation, ReservationStatus
from reservation.results import BookingError, BookingErrorCode, BookingResult, from_core

logger = logging.getLogger(__name__)


class RentalLifecycle:
    """Release only M2's unused vehicle claims; never free physical occupancy."""

    def __init__(self, core: CoreFacade) -> None:
        self.core = core

    def cancel(self, reservation_id: str, actor: Actor) -> BookingResult[RentalReservation]:
        """Cancel the student's Confirmed rental, or settle expiry at the deadline.

        Matching Cancelled/Expired retries return the stored terminal record.
        At/after the deadline the result is EXPIRED, not an owner cancellation.
        """
        return self._settle(reservation_id, actor)

    def expire(self, reservation_id: str) -> BookingResult[RentalReservation]:
        """Internal maintenance entry point; not a user-authorized cancellation.

        Reads Core's clock under its lock and only changes Confirmed expired rows.
        An active or not-yet-due booking is rejected without any mutation.
        """
        return self._settle(reservation_id, None)

    def expire_due(self) -> dict[str, BookingResult[RentalReservation]]:
        """Settle due Confirmed bookings independently and report each outcome.

        A scheduler/application calls this explicitly. Selection is advisory;
        each expiry rechecks state/time under its own transaction lock. A failed
        booking remains retryable and does not roll back successful neighbours.
        """
        now = self.core.queries.get_config().as_of
        ids = [
            booking.reservation_id
            for booking in storage.all_reservations(self.core)
            if booking.status is ReservationStatus.CONFIRMED and booking.hold_expires_at <= now
        ]
        return {reservation_id: self.expire(reservation_id) for reservation_id in ids}

    def _settle(self, reservation_id: str, actor: Actor | None) -> BookingResult[RentalReservation]:
        if not isinstance(reservation_id, str) or not reservation_id.strip():
            return BookingError(BookingErrorCode.INVALID_INPUT, "Reservation ID is required.")
        try:
            return self._transaction(reservation_id, actor)
        except RepositoryError:
            logger.exception("Rental release failed; transaction rolled back")
            return BookingError(
                BookingErrorCode.INTERNAL_ERROR, "Rental release could not be saved."
            )

    def _transaction(
        self, reservation_id: str, actor: Actor | None
    ) -> BookingResult[RentalReservation]:
        with self.core.unit_of_work() as uow:
            if actor is not None:
                account = self.core.get_entity(UserAccount, actor.user_id)
                if (
                    actor.role is not Role.STUDENT
                    or account is None
                    or account.role is not Role.STUDENT
                    or not account.is_active
                ):
                    return BookingError(BookingErrorCode.FORBIDDEN, "Active student required.")
            booking = storage.read(self.core, RentalReservation, reservation_id)
            if booking is None or (actor is not None and booking.user_id != actor.user_id):
                return BookingError(BookingErrorCode.NOT_FOUND_OR_NOT_OWNED, "Booking not found.")
            if booking.status in (ReservationStatus.CANCELLED, ReservationStatus.EXPIRED):
                return Ok(booking)
            if booking.status is not ReservationStatus.CONFIRMED:
                return BookingError(
                    BookingErrorCode.INVALID_STATE, "Only unused bookings end here."
                )
            now = uow.queries.get_config().as_of
            expired = now >= booking.hold_expires_at
            if actor is None and not expired:
                return BookingError(
                    BookingErrorCode.INVALID_STATE, "Booking is not due for expiry."
                )
            claim = self.core.get_entity(ResourceClaim, booking.claim_id)
            if (
                claim is None
                or claim.holder_kind is not HolderKind.RESERVATION
                or claim.holder_ref != booking.reservation_id
                or claim.resource_type is not ResourceType.VEHICLE
                or claim.resource_id != booking.vehicle_id
            ):
                return BookingError(BookingErrorCode.CONFLICT, "Booking claim does not match.")
            found = uow.queries.get_vehicle(booking.vehicle_id)
            if isinstance(found, Err):
                return from_core(found)
            vehicle = found.value
            if vehicle.state is VehicleState.RESERVED and claim.status is not ClaimStatus.ACTIVE:
                return BookingError(BookingErrorCode.CONFLICT, "Vehicle claim is no longer active.")
            # A pre-pickup accepted incident may already have put it in Maintenance.
            # Never touch an InUse vehicle or manufacture a physical departure.
            if vehicle.state not in (VehicleState.RESERVED, VehicleState.MAINTENANCE):
                return BookingError(
                    BookingErrorCode.INVALID_STATE, "Vehicle is not held or faulty."
                )
            caller = Actor(booking.user_id, Role.STUDENT, "reservation")
            released = uow.commands.release_claim(booking.claim_id, caller)
            if isinstance(released, Err):
                return from_core(released)
            if vehicle.state is VehicleState.RESERVED:
                changed = uow.commands.transition_vehicle(
                    vehicle.vehicle_id, VehicleEvent.RELEASE_RESERVATION, vehicle.version, caller
                )
                if isinstance(changed, Err):
                    return from_core(changed)
            booking.status = ReservationStatus.EXPIRED if expired else ReservationStatus.CANCELLED
            storage.update(uow.repository, booking)
            committed = uow.commit()
            return from_core(committed) if isinstance(committed, Err) else Ok(booking)
