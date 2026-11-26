"""Read-only rental demand for Core consumers (D-020, D-021)."""

from datetime import timedelta

from core.domain.entities import ResourceClaim
from core.domain.enums import ClaimStatus, HolderKind, ResourceType
from core.errors import ErrorCode
from core.facade import CoreFacade
from core.providers import (
    BookingDemand,
    BookingDemandKind,
    OpenTripDemand,
    OpenTrips,
    UpcomingBookings,
)
from core.result import Err, Ok, Result
from reservation import storage
from reservation.models import OVERDUE_GRACE, RentalReservation, ReservationStatus, TripStatus


class ReservationDemandProvider:
    def __init__(self, core: CoreFacade) -> None:
        self._core = core

    def upcoming_bookings(self, hub_id: str, horizon: timedelta) -> Result[UpcomingBookings]:
        """Return live fleet pickup holds overlapping the requested half-open window."""
        if not isinstance(horizon, timedelta) or horizon <= timedelta(0):
            return Err(ErrorCode.INVALID_INPUT, "horizon must be a positive timedelta")
        found = self._core.queries.get_hub(hub_id)
        if isinstance(found, Err):
            return found
        now = self._core.queries.get_config().as_of
        try:
            horizon_end = now + horizon
        except OverflowError:
            return Err(ErrorCode.INVALID_INPUT, "horizon exceeds the supported timestamp range")

        rows: list[BookingDemand] = []
        for booking in storage.all_reservations(self._core):
            if (
                booking.origin_hub_id != hub_id
                or booking.status is not ReservationStatus.CONFIRMED
                or booking.hold_expires_at <= now
            ):
                continue
            claim = self._core.get_entity(ResourceClaim, booking.claim_id)
            if (
                claim is None
                or claim.status is not ClaimStatus.ACTIVE
                or claim.holder_kind is not HolderKind.RESERVATION
                or claim.holder_ref != booking.reservation_id
                or claim.resource_type is not ResourceType.VEHICLE
                or claim.resource_id != booking.vehicle_id
                or claim.end_at <= now
                or claim.start_at >= horizon_end
            ):
                continue
            rows.append(
                BookingDemand(
                    booking.reservation_id,
                    BookingDemandKind.RENTAL_PICKUP,
                    hub_id,
                    booking.vehicle_id,
                    claim.resource_id,
                    claim.claim_id,
                    claim.start_at,
                    claim.end_at,
                    booking.hold_expires_at,
                )
            )
        return Ok(UpcomingBookings(now, horizon_end, tuple(rows)))

    def open_trips(self, hub_id: str) -> Result[OpenTrips]:
        """Report open trips by origin or their explicitly planned destination."""
        found = self._core.queries.get_hub(hub_id)
        if isinstance(found, Err):
            return found
        now = self._core.queries.get_config().as_of
        rows: list[OpenTripDemand] = []
        for trip in storage.all_trips(self._core):
            if trip.status not in (TripStatus.IN_PROGRESS, TripStatus.OVERDUE):
                continue
            booking = storage.read(self._core, RentalReservation, trip.reservation_id)
            if booking is None:
                return Err(ErrorCode.RESOURCE_UNAVAILABLE, "open Trip has no rental booking")
            if hub_id not in (trip.origin_hub_id, booking.destination_hub_id):
                continue
            rows.append(
                OpenTripDemand(
                    trip.trip_id,
                    trip.reservation_id,
                    trip.vehicle_id,
                    trip.origin_hub_id,
                    booking.destination_hub_id,
                    trip.picked_up_at,
                    trip.expected_return_at,
                    trip.status is TripStatus.OVERDUE
                    or now - trip.expected_return_at > OVERDUE_GRACE,
                )
            )
        return Ok(OpenTrips(now, tuple(rows)))
