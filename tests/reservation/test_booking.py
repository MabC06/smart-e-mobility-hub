"""TC-M2-001..020: equivalence, boundary, transaction and retry tests.

Verifies: FR-03, FR-04, UC-M2-02/04/05, BR-M2-02/03/04/09/10/14,
NFR-06/07/08/09/13/16/18/22. See docs/testing/reservation-phase2.md.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Barrier

import pytest

from core.actor import Actor
from core.domain.entities import DomainEvent, ParkingSpace, ResourceClaim, UserAccount
from core.domain.enums import ClaimStatus, HolderKind, Ownership, ResourceType, Role, VehicleState
from core.errors import ErrorCode
from core.repository.base import IntegrityViolationError
from core.result import Err, Ok
from reservation import install, storage
from reservation.models import RentalReservation, RentalTrip, ReservationStatus, TripStatus
from reservation.results import BookingError, BookingErrorCode


def ok(result):
    assert isinstance(result, Ok), result
    return result.value


def error(result, code):
    assert isinstance(result, BookingError), result
    assert result.code is code


def start(rental):
    booking = ok(rental.service.reserve(rental.request(), rental.actor))
    trip = ok(rental.service.pickup("R1", "H1", rental.vehicle().version, rental.actor))
    return booking, trip


def fingerprint(rental):
    """Snapshot excludes M2 records: assert both parts and event publication separately."""
    return (
        rental.core.snapshots.export_snapshot(),
        storage.all_reservations(rental.core),
        storage.read(rental.core, RentalTrip, "TRIP:R1"),
        tuple(rental.repo.query(DomainEvent)),
        tuple(rental.events),
    )


@pytest.mark.tc_m2_001
@pytest.mark.parametrize("duration", [5, 30, 120])
def test_complete_rental(rental, duration):
    """Verifies: FR-03/04, UC-M2-02/04/05, BR-M2-04/09/10, NFR-09."""
    request = rental.request(planned_duration_minutes=duration)
    booking = ok(rental.service.reserve(request, rental.actor))
    assert booking.status is ReservationStatus.CONFIRMED
    assert booking.hold_expires_at == rental.clock.now() + timedelta(minutes=10)
    assert rental.vehicle().state is VehicleState.RESERVED
    assert rental.repo.get(ParkingSpace, "S1").occupant_vehicle_id == "V1"
    assert rental.repo.get(ParkingSpace, "S3").occupant_vehicle_id is None
    assert storage.read(rental.core, RentalTrip, "TRIP:R1") is None
    rental.clock.advance(timedelta(minutes=2))
    trip = ok(rental.service.pickup("R1", "H1", rental.vehicle().version, rental.actor))
    assert trip.expected_return_at == rental.clock.now() + timedelta(minutes=duration)
    assert trip.picked_up_at == rental.clock.now()
    assert rental.vehicle().state is VehicleState.IN_USE
    assert rental.vehicle().hub_id is None and rental.vehicle().parking_space_id is None
    assert rental.repo.get(ParkingSpace, "S1").occupant_vehicle_id is None
    assert rental.repo.get(ResourceClaim, booking.claim_id).status is ClaimStatus.RELEASED
    rental.clock.advance(timedelta(minutes=duration))
    receipt = ok(
        rental.service.return_trip(trip.trip_id, "H2", rental.vehicle().version, rental.actor)
    )
    assert receipt.status is TripStatus.COMPLETED
    assert receipt.returned_at == rental.clock.now()
    assert (receipt.return_hub_id, receipt.return_space_id) == ("H2", "S3")
    assert rental.vehicle().state is VehicleState.RETURNED
    assert rental.repo.get(ParkingSpace, "S3").occupant_vehicle_id == "V1"
    assert storage.read(rental.core, RentalReservation, "R1").status is ReservationStatus.COMPLETED
    assert rental.core.check_invariants() == []


@pytest.mark.tc_m2_002
@pytest.mark.parametrize(
    "field,value",
    [
        ("planned_duration_minutes", 4),
        ("planned_duration_minutes", 121),
        ("planned_duration_minutes", 30.5),
        ("planned_duration_minutes", True),
        ("min_battery", -1),
        ("min_battery", 101),
        ("min_battery", float("nan")),
        ("min_battery", float("inf")),
        ("min_battery", True),
        ("expected_version", 0),
        ("expected_version", -1),
        ("expected_version", True),
        ("reservation_id", ""),
        ("vehicle_id", " "),
        ("origin_hub_id", " H1"),
        ("destination_hub_id", ""),
        ("reservation_id", "r" * 129),
    ],
)
def test_invalid_input_never_mutates(rental, field, value):
    """Verifies: NFR-18, FR-03; invalid equivalence partitions."""
    before = fingerprint(rental)
    error(
        rental.service.reserve(rental.request(**{field: value}), rental.actor),
        BookingErrorCode.INVALID_INPUT,
    )
    assert fingerprint(rental) == before


@pytest.mark.tc_m2_003
@pytest.mark.parametrize(
    "battery,requested,allowed",
    [
        (14.99, 0, False),
        (15, 0, False),
        (15.01, 0, False),
        (19.99, 0, False),
        (20, 0, True),
        (20, 20, True),
        (79.99, 80, False),
        (80, 80, True),
        (100, 100, True),
    ],
)
def test_battery_partitions(rental, battery, requested, allowed):
    """Verifies: BR-M2-02, FR-03; rental floor differs from shared 15% lockout."""
    vehicle = rental.vehicle()
    vehicle.battery_pct = battery
    rental.repo.update(vehicle, vehicle.version)
    before = fingerprint(rental)
    result = rental.service.reserve(rental.request(min_battery=requested), rental.actor)
    if allowed:
        ok(result)
    else:
        error(result, BookingErrorCode.RESOURCE_UNAVAILABLE)
        assert fingerprint(rental) == before


@pytest.mark.tc_m2_004
@pytest.mark.parametrize("kind", ["private", "fault", "wrong_origin", "returned"])
def test_ineligible_vehicle(rental, kind):
    """Verifies: BR-M2-02, FR-03, NFR-08."""
    vehicle = rental.vehicle()
    if kind == "private":
        vehicle.ownership = Ownership.PRIVATE
        vehicle.owner_user_id = "U1"
    elif kind == "fault":
        vehicle.fault_flag = True
        vehicle.state = VehicleState.MAINTENANCE
    elif kind == "returned":
        vehicle.state = VehicleState.RETURNED
    rental.repo.update(vehicle, vehicle.version)
    request = rental.request(origin_hub_id="H2" if kind == "wrong_origin" else "H1")
    before = fingerprint(rental)
    error(rental.service.reserve(request, rental.actor), BookingErrorCode.RESOURCE_UNAVAILABLE)
    assert fingerprint(rental) == before


@pytest.mark.tc_m2_005
@pytest.mark.parametrize(
    "actor",
    [
        Actor("unknown", Role.STUDENT, "ui"),
        Actor("OFF", Role.STUDENT, "ui"),
        Actor("OP", Role.OPERATOR, "ui"),
        Actor("U1", Role.OPERATOR, "iot_sim"),
        Actor("OP", Role.STUDENT, "ui"),
    ],
)
def test_only_active_students(rental, actor):
    """Verifies: NFR-16; actor module/role cannot elevate the stored account."""
    before = fingerprint(rental)
    error(rental.service.reserve(rental.request(), actor), BookingErrorCode.FORBIDDEN)
    error(rental.service.pickup("R1", "H1", 1, actor), BookingErrorCode.FORBIDDEN)
    error(rental.service.return_trip("TRIP:R1", "H2", 1, actor), BookingErrorCode.FORBIDDEN)
    assert fingerprint(rental) == before


@pytest.mark.tc_m2_006
@pytest.mark.parametrize("operation", ["reserve", "pickup", "return"])
def test_stale_version_rolls_back(rental, operation):
    """Verifies: NFR-09, FR-03/04; no partial claim, departure or return."""
    if operation != "reserve":
        ok(rental.service.reserve(rental.request(), rental.actor))
    if operation == "return":
        ok(rental.service.pickup("R1", "H1", rental.vehicle().version, rental.actor))
    before = fingerprint(rental)
    stale = rental.vehicle().version + 99
    if operation == "reserve":
        result = rental.service.reserve(rental.request(expected_version=stale), rental.actor)
    elif operation == "pickup":
        result = rental.service.pickup("R1", "H1", stale, rental.actor)
    else:
        result = rental.service.return_trip("TRIP:R1", "H2", stale, rental.actor)
    error(result, BookingErrorCode.CONFLICT)
    assert fingerprint(rental) == before


@pytest.mark.tc_m2_007
@pytest.mark.parametrize("offset,allowed", [(-1, True), (0, False), (1, False)])
def test_pickup_deadline(rental, offset, allowed):
    """Verifies: BR-M2-04, UC-M2-04; deadline +/- 1 ms, no automatic sweep."""
    booking = ok(rental.service.reserve(rental.request(), rental.actor))
    rental.clock.set(booking.hold_expires_at + timedelta(milliseconds=offset))
    before = fingerprint(rental)
    result = rental.service.pickup("R1", "H1", rental.vehicle().version, rental.actor)
    if allowed:
        ok(result)
    else:
        error(result, BookingErrorCode.EXPIRED)
        assert fingerprint(rental) == before


@pytest.mark.tc_m2_008
def test_matching_retries_read_records_even_after_completion(rental, monkeypatch):
    """Verifies: D-015, BR-M2-09/10, FR-03/04; no Core command on retries."""
    request = rental.request()
    booking, trip = start(rental)
    receipt = ok(
        rental.service.return_trip(trip.trip_id, "H2", rental.vehicle().version, rental.actor)
    )
    before = fingerprint(rental)

    def forbidden(*args, **kwargs):
        raise AssertionError("retry must read M2 instead of changing Core")

    monkeypatch.setattr(rental.core.commands, "transition_vehicle", forbidden)
    monkeypatch.setattr(rental.core.commands, "place_claim", forbidden)
    monkeypatch.setattr(rental.core.commands, "release_claim", forbidden)
    assert (
        ok(rental.service.reserve(request, rental.actor)).reservation_id == booking.reservation_id
    )
    assert ok(rental.service.pickup("R1", "H1", 2, rental.actor)) == receipt
    assert ok(rental.service.return_trip(trip.trip_id, "H2", 3, rental.actor)) == receipt
    assert fingerprint(rental) == before


@pytest.mark.tc_m2_009
def test_foreign_records_and_mismatched_retries(rental):
    """Verifies: NFR-16/18, BR-M2-09/10; cannot steal or relocate a booking."""
    request = rental.request()
    _, trip = start(rental)
    before = fingerprint(rental)
    foreign = Actor("U2", Role.STUDENT, "ui")
    for result in [
        rental.service.reserve(request, foreign),
        rental.service.pickup("R1", "H1", 2, foreign),
        rental.service.return_trip(trip.trip_id, "H2", 3, foreign),
        rental.service.pickup("missing", "H1", 1, rental.actor),
        rental.service.return_trip("missing", "H2", 1, rental.actor),
    ]:
        error(result, BookingErrorCode.NOT_FOUND_OR_NOT_OWNED)
    error(
        rental.service.reserve(replace(request, planned_duration_minutes=60), rental.actor),
        BookingErrorCode.INVALID_INPUT,
    )
    error(rental.service.pickup("R1", "H2", 2, rental.actor), BookingErrorCode.INVALID_INPUT)
    assert fingerprint(rental) == before
    ok(rental.service.return_trip(trip.trip_id, "H2", rental.vehicle().version, rental.actor))
    before = fingerprint(rental)
    error(
        rental.service.return_trip(trip.trip_id, "H1", 3, rental.actor),
        BookingErrorCode.INVALID_INPUT,
    )
    assert fingerprint(rental) == before


@pytest.mark.tc_m2_010
@pytest.mark.parametrize("reason", ["occupied", "future_claim"])
def test_full_destination_leaves_trip_open(rental, reason):
    """Verifies: NFR-07/09, BR-M2-10; future claims also block indefinite occupancy."""
    _, trip = start(rental)
    if reason == "future_claim":
        ok(
            rental.core.commands.place_claim(
                ResourceType.SPACE,
                "S3",
                HolderKind.RESERVATION,
                "OTHER",
                rental.clock.now() + timedelta(hours=1),
                rental.clock.now() + timedelta(hours=2),
                Actor("U2", Role.STUDENT, "reservation"),
            )
        )
    else:
        # A second real trip wins the destination first.
        other = Actor("U2", Role.STUDENT, "ui")
        ok(
            rental.service.reserve(
                rental.request(
                    reservation_id="R2",
                    vehicle_id="V2",
                    expected_version=rental.vehicle("V2").version,
                ),
                other,
            )
        )
        t2 = ok(rental.service.pickup("R2", "H1", rental.vehicle("V2").version, other))
        ok(rental.service.return_trip(t2.trip_id, "H2", rental.vehicle("V2").version, other))
    before = fingerprint(rental)
    error(
        rental.service.return_trip(trip.trip_id, "H2", rental.vehicle().version, rental.actor),
        BookingErrorCode.NO_PARKING,
    )
    assert fingerprint(rental) == before
    assert rental.vehicle().state is VehicleState.IN_USE
    assert rental.core.check_invariants() == []


@pytest.mark.tc_m2_011
@pytest.mark.parametrize("operation", ["reserve", "pickup", "return"])
@pytest.mark.parametrize("failure", ["module_write", "commit"])
def test_storage_failure_rolls_back_core_and_module(rental, monkeypatch, operation, failure):
    """Verifies: NFR-09/25; failure after resource writes undoes state, records, audit/events."""
    if operation != "reserve":
        ok(rental.service.reserve(rental.request(), rental.actor))
    if operation == "return":
        ok(rental.service.pickup("R1", "H1", rental.vehicle().version, rental.actor))
    before = fingerprint(rental)

    if failure == "commit":

        def fail_commit():
            raise IntegrityViolationError("injected commit failure")

        monkeypatch.setattr(rental.repo, "commit", fail_commit)
    else:
        method = "update" if operation == "return" else "add"
        original = getattr(rental.repo, method)

        def fail_module(entity, *args, **kwargs):
            if isinstance(entity, (RentalReservation, RentalTrip)):
                raise IntegrityViolationError("injected M2 write failure")
            return original(entity, *args, **kwargs)

        monkeypatch.setattr(rental.repo, method, fail_module)
    if operation == "reserve":
        result = rental.service.reserve(rental.request(), rental.actor)
    elif operation == "pickup":
        result = rental.service.pickup("R1", "H1", rental.vehicle().version, rental.actor)
    else:
        result = rental.service.return_trip("TRIP:R1", "H2", rental.vehicle().version, rental.actor)
    error(result, BookingErrorCode.INTERNAL_ERROR)
    assert fingerprint(rental) == before
    assert rental.core.check_invariants() == []


@pytest.mark.tc_m2_012
def test_claim_release_failure_rolls_back_pickup(rental, monkeypatch):
    """Verifies: D-017, NFR-09; M2 must check release_claim's result."""
    ok(rental.service.reserve(rental.request(), rental.actor))
    before = fingerprint(rental)
    monkeypatch.setattr(
        rental.core.commands, "release_claim", lambda *args: Err(ErrorCode.RESOURCE_UNAVAILABLE)
    )
    error(
        rental.service.pickup("R1", "H1", rental.vehicle().version, rental.actor),
        BookingErrorCode.RESOURCE_UNAVAILABLE,
    )
    assert fingerprint(rental) == before


def together(actions):
    barrier = Barrier(len(actions))

    def run(action):
        barrier.wait(timeout=10)
        return action()

    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        return list(pool.map(run, actions))


@pytest.mark.tc_m2_013
def test_concurrent_identical_requests_return_one_record(rental):
    """Verifies: D-015, NFR-06/09; stale versions on racing retries still recover winner."""
    request = rental.request()
    results = together([lambda: rental.service.reserve(request, rental.actor)] * 12)
    assert len({ok(r).reservation_id for r in results}) == 1
    assert len(storage.all_reservations(rental.core)) == 1
    version = rental.vehicle().version
    results = together([lambda: rental.service.pickup("R1", "H1", version, rental.actor)] * 12)
    assert len({ok(r).trip_id for r in results}) == 1
    version = rental.vehicle().version
    results = together(
        [lambda: rental.service.return_trip("TRIP:R1", "H2", version, rental.actor)] * 12
    )
    assert all(ok(r) == ok(results[0]) for r in results)
    assert len(rental.core.queries.get_state_log("V1")) == 3
    assert rental.core.check_invariants() == []


@pytest.mark.tc_m2_014
def test_quota_serializes_across_different_vehicles(rental):
    """Verifies: BR-M2-03, NFR-06; vehicle version alone cannot protect a user quota."""
    r1 = rental.request()
    r2 = rental.request(reservation_id="R2", vehicle_id="V2")
    results = together(
        [
            lambda: rental.service.reserve(r1, rental.actor),
            lambda: rental.service.reserve(r2, rental.actor),
        ]
    )
    assert sum(isinstance(r, Ok) for r in results) == 1
    assert [r.code for r in results if isinstance(r, BookingError)] == [
        BookingErrorCode.LIMIT_REACHED
    ]
    assert len(storage.all_reservations(rental.core)) == 1


@pytest.mark.tc_m2_015
def test_two_students_cannot_reserve_one_vehicle(rental):
    """Verifies: NFR-06, BR-M2-02; fresh contention is not an identical retry."""
    r1 = rental.request()
    r2 = rental.request(reservation_id="R2")
    results = together(
        [
            lambda: rental.service.reserve(r1, rental.actor),
            lambda: rental.service.reserve(r2, Actor("U2", Role.STUDENT, "ui")),
        ]
    )
    assert sum(isinstance(r, Ok) for r in results) == 1
    assert [r.code for r in results if isinstance(r, BookingError)] == [BookingErrorCode.CONFLICT]
    assert len(rental.repo.query(ResourceClaim)) == 1


@pytest.mark.tc_m2_016
def test_pickup_rechecks_battery_and_account(rental):
    """Verifies: BR-M2-02, NFR-16; validity at reserve does not authorize later pickup."""
    ok(rental.service.reserve(rental.request(), rental.actor))
    vehicle = rental.vehicle()
    vehicle.battery_pct = 19
    rental.repo.update(vehicle, vehicle.version)
    before = fingerprint(rental)
    error(
        rental.service.pickup("R1", "H1", vehicle.version, rental.actor),
        BookingErrorCode.RESOURCE_UNAVAILABLE,
    )
    assert fingerprint(rental) == before
    account = rental.repo.get(UserAccount, "U1")
    account.is_active = False
    rental.repo.update(account)
    error(
        rental.service.pickup("R1", "H1", vehicle.version, rental.actor), BookingErrorCode.FORBIDDEN
    )


@pytest.mark.tc_m2_017
def test_faulty_trip_uses_core_faulty_return(rental):
    """Verifies: D-016, BR-M2-14; an in-use fault stays accountable until actual return."""
    _, trip = start(rental)
    from core.domain.enums import VehicleEvent

    ok(
        rental.core.commands.transition_vehicle(
            "V1",
            VehicleEvent.REPORT_FAULT,
            rental.vehicle().version,
            Actor("OP", Role.OPERATOR, "monitoring"),
        )
    )
    result = ok(
        rental.service.return_trip(trip.trip_id, "H2", rental.vehicle().version, rental.actor)
    )
    assert result.status is TripStatus.INCIDENT_ABORTED
    assert rental.vehicle().state is VehicleState.MAINTENANCE
    assert rental.repo.get(ParkingSpace, "S3").occupant_vehicle_id == "V1"
    assert rental.core.check_invariants() == []


@pytest.mark.tc_m2_018
def test_install_registers_entities_but_not_unimplemented_providers(rental):
    """Verifies: D-013/018/020, NFR-22; startup does not claim Phase 3 capabilities."""
    from core.providers import ProviderPort

    install(rental.core, rental.app)
    assert rental.app.state.reservation.core is rental.core
    assert not rental.core.providers.is_registered(ProviderPort.RESERVATION_DEMAND)
    assert not rental.core.providers.is_registered(ProviderPort.HOLD_CONSUMER)
    ok(rental.app.state.reservation.reserve(rental.request(), rental.actor))


@pytest.mark.tc_m2_019
def test_unknown_resources_and_competing_claim(rental):
    """Verifies: FR-03, NFR-06/18; failed admission leaves no booking."""
    for request in [
        rental.request(vehicle_id="missing"),
        rental.request(destination_hub_id="missing"),
    ]:
        error(
            rental.service.reserve(request, rental.actor), BookingErrorCode.NOT_FOUND_OR_NOT_OWNED
        )
    ok(
        rental.core.commands.place_claim(
            ResourceType.VEHICLE,
            "V1",
            HolderKind.DISPATCH_TASK,
            "D1",
            rental.clock.now(),
            rental.clock.now() + timedelta(minutes=20),
            Actor("OP", Role.OPERATOR, "allocation"),
        )
    )
    before = fingerprint(rental)
    error(rental.service.reserve(rental.request(), rental.actor), BookingErrorCode.CONFLICT)
    assert fingerprint(rental) == before


@pytest.mark.tc_m2_020
def test_return_can_choose_different_hub_from_advisory_destination(rental):
    """Verifies: BR-M2-10, FR-04; planned destination is not an automatic hold."""
    _, trip = start(rental)
    receipt = ok(
        rental.service.return_trip(trip.trip_id, "H1", rental.vehicle().version, rental.actor)
    )
    assert receipt.return_hub_id == "H1" and receipt.return_space_id == "S1"
    assert rental.core.check_invariants() == []


@pytest.mark.tc_m2_022
@pytest.mark.parametrize(
    "hub_id,code",
    [
        ("missing", BookingErrorCode.NOT_FOUND_OR_NOT_OWNED),
        ("H1", BookingErrorCode.RESOURCE_UNAVAILABLE),
    ],
)
def test_origin_must_exist_and_accept_rentals(rental, hub_id, code):
    """Verifies: FR-03, BR-M2-02; unknown/maintenance origin cannot admit a rental."""
    from core.domain.enums import HubStatus

    ok(
        rental.core.commands.set_hub_status(
            "H1", HubStatus.MAINTENANCE, 1, Actor("OP", Role.OPERATOR, "ui")
        )
    )
    before = fingerprint(rental)
    error(rental.service.reserve(rental.request(origin_hub_id=hub_id), rental.actor), code)
    assert fingerprint(rental) == before
