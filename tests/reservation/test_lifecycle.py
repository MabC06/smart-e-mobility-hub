"""TC-M2-023: cancellation/expiry transitions, authorization and atomic release.

Verifies: FR-03, UC-M2-03, BR-M2-04/05, NFR-06/09/16, D-017.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest

from core.actor import Actor
from core.domain.entities import ParkingSpace, ResourceClaim, UserAccount
from core.domain.enums import ClaimStatus, Role, VehicleEvent, VehicleState
from core.errors import ErrorCode
from core.repository.base import IntegrityViolationError
from core.result import Err, Ok
from reservation import storage
from reservation.models import RentalReservation, RentalTrip, ReservationStatus
from reservation.results import BookingError, BookingErrorCode

pytestmark = pytest.mark.tc_m2_023


def reserve(rental):
    result = rental.service.reserve(rental.request(), rental.actor)
    assert isinstance(result, Ok)
    return result.value


@pytest.mark.parametrize(
    "offset,status",
    [
        (-1, ReservationStatus.CANCELLED),
        (0, ReservationStatus.EXPIRED),
        (1, ReservationStatus.EXPIRED),
    ],
)
def test_cancel_boundary_and_retry(rental, offset, status):
    booking = reserve(rental)
    rental.clock.set(booking.hold_expires_at + timedelta(milliseconds=offset))
    lifecycle = rental.app.state.reservation_lifecycle
    result = lifecycle.cancel("R1", rental.actor)
    assert isinstance(result, Ok) and result.value.status is status
    assert rental.vehicle().state is VehicleState.AVAILABLE
    assert rental.repo.get(ParkingSpace, "S1").occupant_vehicle_id == "V1"
    assert rental.repo.get(ResourceClaim, booking.claim_id).status is ClaimStatus.RELEASED
    assert storage.read(rental.core, RentalTrip, "TRIP:R1") is None
    version, events = rental.repo.version(), list(rental.events)
    assert lifecycle.cancel("R1", rental.actor) == result
    assert lifecycle.expire("R1") == result
    assert rental.repo.version() == version and rental.events == events
    assert rental.core.check_invariants() == []
    # Terminal bookings release the user quota as well as the vehicle.
    assert isinstance(rental.service.reserve(rental.request(reservation_id="R2"), rental.actor), Ok)


def test_sweep_uses_core_time_and_can_expire_disabled_users(rental):
    booking = reserve(rental)
    lifecycle = rental.app.state.reservation_lifecycle
    assert lifecycle.expire_due() == {}
    early = lifecycle.expire("R1")
    assert isinstance(early, BookingError)
    account = rental.repo.get(UserAccount, "U1")
    account.is_active = False
    rental.repo.update(account)
    rental.clock.set(booking.hold_expires_at)
    result = lifecycle.expire_due()
    assert isinstance(result["R1"], Ok)
    assert result["R1"].value.status is ReservationStatus.EXPIRED
    assert lifecycle.expire_due() == {}


@pytest.mark.parametrize(
    "actor,code",
    [
        (Actor("U2", Role.STUDENT, "ui"), BookingErrorCode.NOT_FOUND_OR_NOT_OWNED),
        (Actor("OFF", Role.STUDENT, "ui"), BookingErrorCode.FORBIDDEN),
        (Actor("OP", Role.OPERATOR, "ui"), BookingErrorCode.FORBIDDEN),
    ],
)
def test_cancel_authorization(rental, actor, code):
    reserve(rental)
    before = rental.core.snapshots.export_snapshot()
    result = rental.app.state.reservation_lifecycle.cancel("R1", actor)
    assert isinstance(result, BookingError) and result.code is code
    assert rental.core.snapshots.export_snapshot() == before
    assert storage.read(rental.core, RentalReservation, "R1").status is ReservationStatus.CONFIRMED


def test_expiry_never_ends_active_trip(rental):
    booking = reserve(rental)
    assert isinstance(rental.service.pickup("R1", "H1", rental.vehicle().version, rental.actor), Ok)
    rental.clock.set(booking.hold_expires_at + timedelta(days=1))
    lifecycle = rental.app.state.reservation_lifecycle
    assert lifecycle.expire_due() == {}
    for result in (lifecycle.cancel("R1", rental.actor), lifecycle.expire("R1")):
        assert isinstance(result, BookingError) and result.code is BookingErrorCode.INVALID_STATE
    assert rental.vehicle().state is VehicleState.IN_USE


@pytest.mark.parametrize("failure", ["release", "transition", "write", "commit"])
def test_release_is_atomic(rental, monkeypatch, failure):
    booking = reserve(rental)
    before = rental.core.snapshots.export_snapshot()
    events = list(rental.events)
    if failure in ("release", "transition"):
        name = "release_claim" if failure == "release" else "transition_vehicle"
        monkeypatch.setattr(rental.core.commands, name, lambda *a: Err(ErrorCode.INTERNAL_ERROR))
    elif failure == "commit":

        def fail():
            raise IntegrityViolationError("injected commit failure")

        monkeypatch.setattr(rental.repo, "commit", fail)
    else:
        original = rental.repo.update

        def fail(entity, expected_version=None):
            if isinstance(entity, RentalReservation):
                raise IntegrityViolationError("injected M2 failure")
            return original(entity, expected_version)

        monkeypatch.setattr(rental.repo, "update", fail)
    result = rental.app.state.reservation_lifecycle.cancel("R1", rental.actor)
    assert isinstance(result, BookingError)
    assert rental.core.snapshots.export_snapshot() == before
    assert storage.read(rental.core, RentalReservation, "R1") == booking
    assert rental.events == events


def test_faulty_parked_vehicle_stays_in_maintenance(rental):
    reserve(rental)
    assert isinstance(
        rental.core.commands.transition_vehicle(
            "V1",
            VehicleEvent.REPORT_FAULT,
            rental.vehicle().version,
            Actor("OP", Role.OPERATOR, "monitoring"),
        ),
        Ok,
    )
    assert isinstance(rental.app.state.reservation_lifecycle.cancel("R1", rental.actor), Ok)
    assert rental.vehicle().state is VehicleState.MAINTENANCE
    assert rental.repo.get(ParkingSpace, "S1").occupant_vehicle_id == "V1"


def test_pickup_and_cancel_have_one_winner(rental):
    reserve(rental)
    version = rental.vehicle().version
    barrier = Barrier(2)

    def pickup():
        barrier.wait(timeout=10)
        return rental.service.pickup("R1", "H1", version, rental.actor)

    def cancel():
        barrier.wait(timeout=10)
        return rental.app.state.reservation_lifecycle.cancel("R1", rental.actor)

    with ThreadPoolExecutor(2) as pool:
        first, second = pool.submit(pickup), pool.submit(cancel)
        results = [first.result(), second.result()]
    assert sum(isinstance(r, Ok) for r in results) == 1
    booking = storage.read(rental.core, RentalReservation, "R1")
    assert booking.status in (ReservationStatus.ACTIVE, ReservationStatus.CANCELLED)
    assert rental.core.check_invariants() == []
