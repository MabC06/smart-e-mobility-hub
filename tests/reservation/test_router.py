"""TC-M2-024/025: wire student rental actions to real auth, Core, and SQLite."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import main
from core.auth import hash_password
from core.clock import FixedClock
from core.domain.enums import Role, SpaceStatus, VehicleType
from core.repository.base import RepositoryError
from core.result import Ok
from core.seed import HubSpec, NetworkSpec, UserSpec, VehicleSpec
from reservation import storage

PREFIX = "/reservations"
PASSWORD = "m2-test-password"
CLOCK_START = datetime(2026, 11, 24, 8, tzinfo=UTC)


@pytest.fixture
def m2_api():
    clock = FixedClock(CLOCK_START)
    settings = main.Settings.from_env(
        {"SECRET_KEY": "m2-rest-test-token-key-0123456789", "LOG_LEVEL": "WARNING"}
    )
    app = main.build_app(settings, clock=clock, module_names=("reservation",))
    password_hash = hash_password(PASSWORD, 1000)
    network = NetworkSpec(
        hubs=(
            HubSpec(
                "H1",
                "Origin",
                "A",
                1,
                0,
                vehicles=(VehicleSpec("V1", "FLEET-1", VehicleType.E_BIKE, 80),),
            ),
            HubSpec("H2", "Destination", "B", 1, 0),
            HubSpec(
                "H3",
                "Full Hub",
                "C",
                1,
                0,
                vehicles=(VehicleSpec("V2", "FLEET-2", VehicleType.E_BIKE, 80),),
            ),
        ),
        users=(
            UserSpec("U1", "STUDENT-1", Role.STUDENT, password_hash),
            UserSpec("U2", "STUDENT-2", Role.STUDENT, password_hash),
            UserSpec("OP", "OPERATOR", Role.OPERATOR, password_hash),
        ),
    )
    core = app.state.core
    seeded = core.commands.load_network(network, main.SEEDER)
    assert isinstance(seeded, Ok), seeded
    with TestClient(app) as client:
        yield client, core, clock


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def _login(client, code):
    result = _ok(client.post("/auth/login", json={"code": code, "password": PASSWORD}))
    return {"Authorization": f"Bearer {result['access_token']}"}


def _request(core, reservation_id="R1"):
    vehicle = core.queries.get_vehicle("V1")
    assert isinstance(vehicle, Ok)
    return {
        "reservation_id": reservation_id,
        "vehicle_id": "V1",
        "origin_hub_id": "H1",
        "destination_hub_id": "H2",
        "expected_version": vehicle.value.version,
    }


def _mine(client, headers):
    return _ok(client.get(f"{PREFIX}/mine", headers=headers))


@pytest.mark.tc_m2_024
def test_student_rental_journey_and_retries(m2_api):
    """Verifies: FR-03/04, UC-M2-02/04/05, D-015, D-023, NFR-09/16."""
    client, core, clock = m2_api
    headers = _login(client, "STUDENT-1")
    request = _request(core)
    reservation = _ok(client.post(PREFIX, headers=headers, json=request))
    assert reservation["reservation_id"] == "R1" and reservation["status"] == "CONFIRMED"
    assert _ok(client.post(PREFIX, headers=headers, json=request)) == reservation
    mine = _mine(client, headers)
    assert mine["bookings"] == [reservation] and mine["open_trips"] == []
    pickup_body = {"origin_hub_id": "H1", "expected_version": mine["vehicle_versions"]["V1"]}

    clock.advance(timedelta(minutes=2))
    pickup_url = f"{PREFIX}/R1/pickup"
    trip = _ok(client.post(pickup_url, headers=headers, json=pickup_body))
    assert trip["status"] == "IN_PROGRESS" and trip["trip_id"] == "TRIP:R1"
    assert _ok(client.post(pickup_url, headers=headers, json=pickup_body)) == trip
    mine = _mine(client, headers)
    assert mine["bookings"][0]["status"] == "ACTIVE"
    assert mine["open_trips"] == [trip]
    (source,) = core.queries.list_spaces("H1")
    assert source.status is SpaceStatus.AVAILABLE

    return_body = {"destination_hub_id": "H2", "expected_version": mine["vehicle_versions"]["V1"]}
    return_url = f"{PREFIX}/R1/return"
    receipt = _ok(client.post(return_url, headers=headers, json=return_body))
    assert receipt["status"] == "COMPLETED" and receipt["return_hub_id"] == "H2"
    assert _ok(client.post(return_url, headers=headers, json=return_body)) == receipt
    assert _mine(client, headers)["open_trips"] == []
    (destination,) = core.queries.list_spaces("H2")
    assert (destination.status, destination.occupant_vehicle_id) == (SpaceStatus.OCCUPIED, "V1")
    assert core.check_invariants() == []


@pytest.mark.tc_m2_024
def test_owner_can_cancel_without_freeing_parked_space(m2_api):
    """Verifies: FR-03, UC-M2-03, BR-M2-05, NFR-07/09."""
    client, core, _clock = m2_api
    headers = _login(client, "STUDENT-1")
    _ok(client.post(PREFIX, headers=headers, json=_request(core)))
    url = f"{PREFIX}/R1/cancel"
    cancelled = _ok(client.post(url, headers=headers))
    assert cancelled["status"] == "CANCELLED"
    assert _ok(client.post(url, headers=headers)) == cancelled
    (space,) = core.queries.list_spaces("H1")
    assert (space.status, space.occupant_vehicle_id) == (SpaceStatus.OCCUPIED, "V1")
    assert _mine(client, headers)["open_trips"] == []
    assert core.check_invariants() == []


@pytest.mark.tc_m2_025
def test_rental_endpoints_require_student_and_hide_foreign_records(m2_api):
    """Verifies: D-023, NFR-16, BR-M2-09."""
    client, core, _clock = m2_api
    owner = _login(client, "STUDENT-1")
    other = _login(client, "STUDENT-2")
    operator = _login(client, "OPERATOR")
    request = _request(core)
    routes = [
        ("GET", f"{PREFIX}/mine", None),
        ("POST", PREFIX, request),
        ("POST", f"{PREFIX}/R1/cancel", None),
        ("POST", f"{PREFIX}/R1/pickup", {"origin_hub_id": "H1", "expected_version": 1}),
        ("POST", f"{PREFIX}/R1/return", {"destination_hub_id": "H2", "expected_version": 1}),
    ]
    for method, path, body in routes:
        assert client.request(method, path, json=body).status_code == 401
        assert client.request(method, path, headers=operator, json=body).status_code == 403

    _ok(client.post(PREFIX, headers=owner, json=request))
    before = core.snapshots.export_snapshot()
    hidden = _mine(client, other)
    assert hidden["bookings"] == [] and hidden["open_trips"] == []
    assert hidden["vehicle_versions"] == {}
    for method, path, body in routes[2:]:
        foreign = client.request(method, path, headers=other, json=body)
        missing = client.request(method, path.replace("R1", "missing"), headers=other, json=body)
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json() == missing.json()
    assert core.snapshots.export_snapshot() == before
    hidden_reserve = client.post(PREFIX, headers=other, json=request)
    assert hidden_reserve.status_code == 404

    version = _mine(client, owner)["vehicle_versions"]["V1"]
    trip = _ok(
        client.post(
            f"{PREFIX}/R1/pickup",
            headers=owner,
            json={"origin_hub_id": "H1", "expected_version": version},
        )
    )
    version = _mine(client, owner)["vehicle_versions"]["V1"]
    foreign_return = client.post(
        f"{PREFIX}/R1/return",
        headers=other,
        json={"destination_hub_id": "H2", "expected_version": version},
    )
    assert foreign_return.status_code == 404
    assert _mine(client, other)["open_trips"] == []
    assert _mine(client, owner)["open_trips"] == [trip]


@pytest.mark.tc_m2_025
def test_invalid_version_and_full_hub_errors_have_no_partial_writes(m2_api):
    """Verifies: FR-03/04, BR-M2-09/10, NFR-09/18."""
    client, core, _clock = m2_api
    headers = _login(client, "STUDENT-1")
    request = _request(core)
    before = core.snapshots.export_snapshot()
    invalid = client.post(PREFIX, headers=headers, json={**request, "reservation_id": " R1 "})
    assert invalid.status_code == 400
    assert invalid.json()["detail"]["code"] == "INVALID_INPUT"
    assert _mine(client, headers)["bookings"] == []
    assert core.snapshots.export_snapshot() == before

    _ok(client.post(PREFIX, headers=headers, json=request))
    pickup_url = f"{PREFIX}/R1/pickup"
    pickup_body = {"origin_hub_id": "H1", "expected_version": request["expected_version"]}
    before = core.snapshots.export_snapshot()
    stale = client.post(pickup_url, headers=headers, json=pickup_body)
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "CONFLICT"
    mine = _mine(client, headers)
    assert mine["bookings"][0]["status"] == "CONFIRMED" and mine["open_trips"] == []
    assert core.snapshots.export_snapshot() == before

    pickup_body["expected_version"] = mine["vehicle_versions"]["V1"]
    trip = _ok(client.post(pickup_url, headers=headers, json=pickup_body))
    before = core.snapshots.export_snapshot()
    observed_version = _mine(client, headers)["vehicle_versions"]["V1"]
    full = client.post(
        f"{PREFIX}/R1/return",
        headers=headers,
        json={"destination_hub_id": "H3", "expected_version": observed_version},
    )
    assert full.status_code == 409
    assert full.json()["detail"]["code"] == "NO_PARKING"
    assert _mine(client, headers)["open_trips"] == [trip]
    assert core.snapshots.export_snapshot() == before


@pytest.mark.tc_m2_025
def test_storage_failures_return_server_errors_and_leave_booking_retryable(m2_api, monkeypatch):
    """Verifies: review M2-1, NFR-09/18. Read and write faults differ from conflicts."""
    client, core, _clock = m2_api
    headers = _login(client, "STUDENT-1")
    request = _request(core)
    before = core.snapshots.export_snapshot()

    def fail_storage(*_args):
        raise RepositoryError("injected database failure")

    with monkeypatch.context() as patch:
        patch.setattr(storage, "add", fail_storage)
        failed_booking = client.post(PREFIX, headers=headers, json=request)
    assert failed_booking.status_code == 500
    assert failed_booking.json()["detail"]["code"] == "INTERNAL_ERROR"
    assert "injected database failure" not in failed_booking.text
    assert core.snapshots.export_snapshot() == before
    assert _mine(client, headers)["bookings"] == []

    with monkeypatch.context() as patch:
        patch.setattr(storage, "student_records", fail_storage)
        failed_list = client.get(f"{PREFIX}/mine", headers=headers)
    assert failed_list.status_code == 503
    assert failed_list.json()["detail"] == {
        "code": "INTERNAL_ERROR",
        "message": "Could not read bookings.",
    }

    booking = _ok(client.post(PREFIX, headers=headers, json=request))
    assert _mine(client, headers)["bookings"] == [booking]
