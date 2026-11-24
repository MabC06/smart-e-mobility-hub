"""Verifies: D-020, D-021, BR-M2-04, BR-M2-15; rental demand is read-only."""

from datetime import timedelta

import pytest

from core.actor import Actor
from core.domain.entities import ResourceClaim
from core.domain.enums import ClaimStatus, Role
from core.errors import ErrorCode
from core.providers import BookingDemandKind, ProviderPort
from core.result import Err, Ok
from reservation import storage
from reservation.models import RentalReservation, RentalTrip, ReservationStatus, TripStatus
from reservation.providers import OVERDUE_GRACE, ReservationDemandProvider

pytestmark = pytest.mark.tc_m2_026


def test_live_rental_demand_is_sorted_and_does_not_settle_expiry(rental):
    result = rental.service.reserve(rental.request(reservation_id="R2"), rental.actor)
    assert isinstance(result, Ok)
    booking = result.value
    request = rental.request(
        reservation_id="R1", vehicle_id="V2", expected_version=rental.vehicle("V2").version
    )
    second = rental.service.reserve(request, Actor("U2", Role.STUDENT, "ui"))
    assert isinstance(second, Ok)
    provider = ReservationDemandProvider(rental.core)
    horizon = timedelta(hours=1)
    snapshot = rental.core.snapshots.export_snapshot()

    demand = rental.core.providers.call(
        ProviderPort.RESERVATION_DEMAND, lambda port: port.upcoming_bookings("H1", horizon)
    )
    assert isinstance(demand, Ok)
    assert [row.reservation_id for row in demand.value.bookings] == ["R1", "R2"]
    row = demand.value.bookings[1]
    assert row.kind is BookingDemandKind.RENTAL_PICKUP
    assert row.resource_id == "V1" and row.claim_id == booking.claim_id
    assert row.start_at == booking.confirmed_at and row.end_at == booking.hold_expires_at
    assert demand.value.as_of == booking.confirmed_at
    assert demand.value.horizon_end == booking.confirmed_at + horizon
    assert provider.upcoming_bookings("H2", horizon).value.bookings == ()
    assert rental.core.snapshots.export_snapshot() == snapshot

    rental.clock.set(booking.hold_expires_at)
    assert provider.upcoming_bookings("H1", horizon).value.bookings == ()
    assert storage.read(rental.core, RentalReservation, "R2").status is ReservationStatus.CONFIRMED
    assert rental.repo.get(ResourceClaim, booking.claim_id).status is ClaimStatus.ACTIVE


def test_demand_rejects_bad_horizon_and_unknown_hub(rental):
    provider = ReservationDemandProvider(rental.core)
    for horizon in (timedelta(0), -timedelta(seconds=1), timedelta.max):
        result = provider.upcoming_bookings("H1", horizon)
        assert isinstance(result, Err) and result.code is ErrorCode.INVALID_INPUT
    booking = provider.upcoming_bookings("UNKNOWN", timedelta(hours=1))
    trip = provider.open_trips("UNKNOWN")
    assert isinstance(booking, Err) and booking.code is ErrorCode.NOT_FOUND
    assert isinstance(trip, Err) and trip.code is ErrorCode.NOT_FOUND


@pytest.mark.parametrize("destination", ["H2", None])
def test_open_trip_demand_is_advisory_and_tracks_overdue_boundary(rental, destination):
    booking = rental.service.reserve(rental.request(destination_hub_id=destination), rental.actor)
    assert isinstance(booking, Ok)
    picked_up = rental.service.pickup("R1", "H1", rental.vehicle().version, rental.actor)
    assert isinstance(picked_up, Ok)
    trip = picked_up.value
    provider = ReservationDemandProvider(rental.core)
    assert provider.upcoming_bookings("H1", timedelta(hours=1)).value.bookings == ()
    deadline = trip.expected_return_at + OVERDUE_GRACE
    rental.clock.set(deadline)
    (row,) = provider.open_trips("H1").value.trips
    assert row.trip_id == trip.trip_id and row.reservation_id == trip.reservation_id
    assert row.destination_hub_id == destination
    assert row.expected_return_at == trip.expected_return_at and not row.is_overdue
    assert provider.open_trips("H2").value.trips == ((row,) if destination is not None else ())

    rental.clock.advance(timedelta(microseconds=1))
    observed = provider.open_trips("H1").value
    assert observed.trips[0].is_overdue and observed.as_of == rental.clock.now()
    assert storage.read(rental.core, RentalTrip, trip.trip_id).status is TripStatus.IN_PROGRESS
    returned = rental.service.return_trip(
        trip.trip_id, "H2", rental.vehicle().version, rental.actor
    )
    assert isinstance(returned, Ok)
    assert provider.open_trips("H1").value.trips == ()
    assert provider.open_trips("H2").value.trips == ()
