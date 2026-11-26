"""TC-M2-027..029: vehicle search, lazy expiry and overdue marking through the M2 routes."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import main
from core.auth import hash_password
from core.clock import FixedClock
from core.domain.enums import Role, VehicleState, VehicleType
from core.result import Ok
from core.seed import HubSpec, NetworkSpec, UserSpec, VehicleSpec
from reservation.models import OVERDUE_GRACE

PREFIX = "/reservations"
PASSWORD = "m2-test-password"
CLOCK_START = datetime(2026, 11, 25, 8, tzinfo=UTC)


@pytest.fixture
def api():
    clock = FixedClock(CLOCK_START)
    settings = main.Settings.from_env(
        {"SECRET_KEY": "m2-search-test-token-key-0123456789", "LOG_LEVEL": "WARNING"}
    )
    app = main.build_app(settings, clock=clock, module_names=("reservation",))
    password_hash = hash_password(PASSWORD, 1000)
    fleet = (
        VehicleSpec("V1", "FLEET-1", VehicleType.E_BIKE, 80),
        VehicleSpec("V2", "FLEET-2", VehicleType.E_SCOOTER, 90),
        VehicleSpec("V3", "FLEET-3", VehicleType.E_BIKE, 15),  # under the 20% rental minimum
        VehicleSpec("V4", "FLEET-4", VehicleType.E_BIKE, 60),
        VehicleSpec("V5", "FLEET-5", VehicleType.E_BIKE, 80),
    )
    network = NetworkSpec(
        hubs=(
            HubSpec("H1", "Origin", "A", 6, 0, vehicles=fleet),
            HubSpec("H2", "Destination", "B", 2, 0),
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


def _reserve(client, core, headers, vehicle_id, reservation_id):
    version = core.queries.get_vehicle(vehicle_id).value.version
    body = {
        "reservation_id": reservation_id,
        "vehicle_id": vehicle_id,
        "origin_hub_id": "H1",
        "expected_version": version,
    }
    return client.post(PREFIX, headers=headers, json=body)


def _found(client, headers, **params):
    result = _ok(
        client.get(f"{PREFIX}/vehicles", headers=headers, params={"hub_id": "H1", **params})
    )
    return [vehicle["vehicle_id"] for vehicle in result["vehicles"]]


@pytest.mark.tc_m2_027
def test_search_lists_rentable_fleet_vehicles_best_battery_first(api):
    """Verifies: FR-02, BR-M2-02, UC-M2-01.

    Expected: fleet vehicles only, at least 20%, sorted by battery then ID; filters by type and
    minimum battery; a vehicle another student reserved is left out.
    """
    client, core, _clock = api
    headers = _login(client, "STUDENT-1")

    assert _found(client, headers) == ["V2", "V1", "V5", "V4"]
    assert _found(client, headers, type="E_SCOOTER") == ["V2"]
    assert _found(client, headers, min_battery=70) == ["V2", "V1", "V5"]

    _ok(_reserve(client, core, _login(client, "STUDENT-2"), "V5", "R-OTHER"))

    assert _found(client, headers) == ["V2", "V1", "V4"]


@pytest.mark.tc_m2_027
def test_search_checks_its_input_and_changes_nothing(api):
    """Verifies: FR-02, NFR-16, NFR-18.

    Expected: 401 without a token, 403 for an operator, 400 for a minimum over 100 or an unknown
    type, 404 for an unknown Hub; the shared state is the same afterwards.
    """
    client, core, _clock = api
    headers = _login(client, "STUDENT-1")
    before = core.snapshots.export_snapshot()
    url = f"{PREFIX}/vehicles"

    assert client.get(url, params={"hub_id": "H1"}).status_code == 401
    operator = _login(client, "OPERATOR")
    assert client.get(url, headers=operator, params={"hub_id": "H1"}).status_code == 403
    for params in ({"min_battery": 101}, {"type": "CAR"}):
        response = client.get(url, headers=headers, params={"hub_id": "H1", **params})
        assert response.status_code == 400
    unknown = client.get(url, headers=headers, params={"hub_id": "H9"})
    assert unknown.status_code == 404
    assert unknown.json()["detail"]["code"] == "NOT_FOUND_OR_NOT_OWNED"
    assert core.snapshots.export_snapshot() == before


@pytest.mark.tc_m2_028
def test_a_due_booking_expires_on_the_next_request(api):
    """Verifies: FR-03, BR-M2-04, UC-M2-03, D-017.

    Expected: before the deadline a second booking is refused (LIMIT_REACHED); at the deadline
    the next request expires the first booking, frees its vehicle, and a new booking succeeds.
    """
    client, core, clock = api
    headers = _login(client, "STUDENT-1")
    booking = _ok(_reserve(client, core, headers, "V1", "R1"))
    second = _reserve(client, core, headers, "V2", "R2")
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "LIMIT_REACHED"

    clock.set(datetime.fromisoformat(booking["hold_expires_at"]))
    mine = _ok(client.get(f"{PREFIX}/mine", headers=headers))

    assert mine["bookings"][0]["status"] == "EXPIRED"
    assert core.queries.get_vehicle("V1").value.state is VehicleState.AVAILABLE
    assert "V1" in _found(client, headers)
    assert _ok(_reserve(client, core, headers, "V2", "R2"))["status"] == "CONFIRMED"
    assert core.check_invariants() == []


@pytest.mark.tc_m2_029
def test_a_late_trip_becomes_overdue_and_can_still_be_returned(api):
    """Verifies: FR-04, BR-M2-15, UC-M2-05.

    Expected: at due + 60 min the Trip is still IN_PROGRESS; one second later it is OVERDUE
    while the booking stays ACTIVE; the return then completes it.
    """
    client, core, clock = api
    headers = _login(client, "STUDENT-1")
    _ok(_reserve(client, core, headers, "V1", "R1"))
    version = core.queries.get_vehicle("V1").value.version
    pickup = {"origin_hub_id": "H1", "expected_version": version}
    trip = _ok(client.post(f"{PREFIX}/R1/pickup", headers=headers, json=pickup))
    due = datetime.fromisoformat(trip["expected_return_at"])

    clock.set(due + OVERDUE_GRACE)
    headers = _login(client, "STUDENT-1")  # the first token has expired by now
    assert _ok(client.get(f"{PREFIX}/mine", headers=headers))["open_trips"][0]["status"] == (
        "IN_PROGRESS"
    )
    clock.set(due + OVERDUE_GRACE + timedelta(seconds=1))
    mine = _ok(client.get(f"{PREFIX}/mine", headers=headers))

    assert mine["open_trips"][0]["status"] == "OVERDUE"
    assert mine["bookings"][0]["status"] == "ACTIVE"
    back = {"destination_hub_id": "H2", "expected_version": mine["vehicle_versions"]["V1"]}
    receipt = _ok(client.post(f"{PREFIX}/R1/return", headers=headers, json=back))
    assert receipt["status"] == "COMPLETED" and receipt["return_hub_id"] == "H2"
    assert core.check_invariants() == []
