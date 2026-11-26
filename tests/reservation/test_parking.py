"""TC-M2-030..032: return-space hold and private parking through the M2 routes."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import main
from core.auth import hash_password
from core.clock import FixedClock
from core.domain.entities import ResourceClaim
from core.domain.enums import ClaimStatus, Role, SpaceStatus, VehicleState, VehicleType
from core.result import Ok
from core.seed import HubSpec, NetworkSpec, UserSpec, VehicleSpec

PREFIX = "/reservations"
PASSWORD = "m2-test-password"
CLOCK_START = datetime(2026, 11, 25, 8, tzinfo=UTC)


@pytest.fixture
def api():
    clock = FixedClock(CLOCK_START)
    settings = main.Settings.from_env(
        {"SECRET_KEY": "m2-parking-test-token-key-0123456789", "LOG_LEVEL": "WARNING"}
    )
    app = main.build_app(settings, clock=clock, module_names=("reservation",))
    password_hash = hash_password(PASSWORD, 1000)
    network = NetworkSpec(
        hubs=(
            HubSpec(
                "H1",
                "Origin",
                "A",
                3,
                0,
                vehicles=(VehicleSpec("V1", "FLEET-1", VehicleType.E_BIKE, 80),),
            ),
            HubSpec("H2", "Destination", "B", 2, 0),
            HubSpec("H3", "Other", "C", 2, 0),
        ),
        users=(
            UserSpec("U1", "STUDENT-1", Role.STUDENT, password_hash),
            UserSpec("U2", "STUDENT-2", Role.STUDENT, password_hash),
        ),
        private_vehicles=(
            VehicleSpec("P1", "PRIVATE-1", VehicleType.E_BIKE, 60, 0.5, "U1", "TYPE2"),
            VehicleSpec("P2", "PRIVATE-2", VehicleType.E_BIKE, 60, 0.5, "U2", "TYPE2"),
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


def _code(response, status):
    assert response.status_code == status, response.text
    return response.json()["detail"]["code"]


def _login(client, code="STUDENT-1"):
    result = _ok(client.post("/auth/login", json={"code": code, "password": PASSWORD}))
    return {"Authorization": f"Bearer {result['access_token']}"}


def _version(core, vehicle_id):
    return core.queries.get_vehicle(vehicle_id).value.version


def _start_trip(client, core, headers):
    body = {
        "reservation_id": "R1",
        "vehicle_id": "V1",
        "origin_hub_id": "H1",
        "expected_version": _version(core, "V1"),
    }
    _ok(client.post(PREFIX, headers=headers, json=body))
    pickup = {"origin_hub_id": "H1", "expected_version": _version(core, "V1")}
    _ok(client.post(f"{PREFIX}/R1/pickup", headers=headers, json=pickup))


def _hold(client, headers, hub_id, parking_id="PK1"):
    body = {"parking_id": parking_id, "destination_hub_id": hub_id}
    return client.post(f"{PREFIX}/R1/return-hold", headers=headers, json=body)


def _return(client, core, headers, hub_id):
    body = {"destination_hub_id": hub_id, "expected_version": _version(core, "V1")}
    return client.post(f"{PREFIX}/R1/return", headers=headers, json=body)


def _claim(core, claim_id):
    return core.get_entity(ResourceClaim, claim_id)


@pytest.mark.tc_m2_030
def test_return_uses_the_held_space_and_consumes_the_hold(api):
    """Verifies: FR-05, UC-M2-05, UC-M2-06, BR-M2-10, BR-M2-11.

    Expected: the hold names an empty space of H2 for 10 min; the same ID returns the same hold;
    the return parks V1 in that space, the hold is COMPLETED and its claim released.
    """
    client, core, _clock = api
    headers = _login(client)
    _start_trip(client, core, headers)

    hold = _ok(_hold(client, headers, "H2"))
    assert hold["status"] == "CONFIRMED" and hold["purpose"] == "RENTAL_RETURN"
    assert hold["hub_id"] == "H2" and hold["trip_id"] == "TRIP:R1"
    assert _ok(_hold(client, headers, "H2")) == hold

    receipt = _ok(_return(client, core, headers, "H2"))

    assert receipt["return_space_id"] == hold["parking_space_id"]
    parking = _ok(client.get(f"{PREFIX}/mine", headers=headers))["parking"]
    assert [p["status"] for p in parking] == ["COMPLETED"]
    assert _claim(core, hold["claim_id"]).status is ClaimStatus.RELEASED
    assert core.check_invariants() == []


@pytest.mark.tc_m2_030
def test_a_hold_blocks_others_and_one_at_another_hub_is_left_to_expire(api):
    """Verifies: FR-05, BR-M2-03, BR-M2-04, BR-M2-10.

    Expected: a second hold is refused (LIMIT_REACHED); a return to H3 does not use the H2 hold;
    at the deadline the next request expires it and releases its claim; no hold without a Trip.
    """
    client, core, clock = api
    headers = _login(client)
    assert _code(_hold(client, headers, "H2"), 404) == "NOT_FOUND_OR_NOT_OWNED"
    _start_trip(client, core, headers)
    hold = _ok(_hold(client, headers, "H2"))
    assert _code(_hold(client, headers, "H3", "PK2"), 409) == "LIMIT_REACHED"

    receipt = _ok(_return(client, core, headers, "H3"))
    assert receipt["return_hub_id"] == "H3"
    assert _claim(core, hold["claim_id"]).status is ClaimStatus.ACTIVE

    clock.set(datetime.fromisoformat(hold["hold_expires_at"]))
    parking = _ok(client.get(f"{PREFIX}/mine", headers=headers))["parking"]

    assert parking[0]["status"] == "EXPIRED"
    assert _claim(core, hold["claim_id"]).status is ClaimStatus.RELEASED
    assert core.check_invariants() == []


def _park(client, headers, **fields):
    body = {"parking_id": "PK1", "vehicle_id": "P1", "hub_id": "H2", **fields}
    return client.post(f"{PREFIX}/parking", headers=headers, json=body)


@pytest.mark.tc_m2_031
def test_private_ev_reserves_arrives_and_departs(api):
    """Verifies: FR-05, FR-07, UC-M2-06, UC-M2-08, BR-M2-11.

    Expected: a booking 30 min ahead holds a space of H2; arrival before the start is refused;
    in the window P1 parks in that space; departure frees it and completes the booking.
    """
    client, core, clock = api
    headers = _login(client)
    start = CLOCK_START + timedelta(minutes=30)

    booking = _ok(_park(client, headers, start_at=start.isoformat(), duration_minutes=60))
    assert booking["status"] == "CONFIRMED" and booking["purpose"] == "PRIVATE_STAY"
    url = f"{PREFIX}/parking/PK1"
    early = client.post(f"{url}/arrive", headers=headers, json={"expected_version": 1})
    assert _code(early, 409) == "INVALID_STATE"

    clock.set(start + timedelta(minutes=5))
    headers = _login(client)
    version = {"expected_version": _version(core, "P1")}
    arrived = _ok(client.post(f"{url}/arrive", headers=headers, json=version))

    assert arrived["status"] == "ACTIVE"
    vehicle = core.queries.get_vehicle("P1").value
    assert vehicle.parking_space_id == booking["parking_space_id"]
    assert vehicle.state is VehicleState.AVAILABLE
    version = {"expected_version": vehicle.version}
    left = _ok(client.post(f"{url}/depart", headers=headers, json=version))

    assert left["status"] == "COMPLETED" and left["departed_at"] is not None
    space = next(
        s
        for s in core.queries.list_spaces("H2")
        if s.parking_space_id == booking["parking_space_id"]
    )
    assert space.status is SpaceStatus.AVAILABLE
    assert core.check_invariants() == []


@pytest.mark.tc_m2_032
def test_private_parking_checks_owner_times_and_releases_on_cancel_or_expiry(api):
    """Verifies: FR-05, FR-07, UC-M2-07, BR-M2-03, BR-M2-04, BR-M2-05, NFR-18.

    Expected: another student's EV is 404; a stay outside 30..240 min or a start after 24 h is
    400; a second booking is LIMIT_REACHED; cancel releases the claim; an unused booking expires
    at start + 10 min on the next request.
    """
    client, core, clock = api
    headers = _login(client)
    assert _code(_park(client, headers, vehicle_id="P2"), 404) == "NOT_FOUND_OR_NOT_OWNED"
    assert _code(_park(client, headers, duration_minutes=20), 400) == "INVALID_INPUT"
    late = (CLOCK_START + timedelta(hours=25)).isoformat()
    assert _code(_park(client, headers, start_at=late), 400) == "INVALID_INPUT"

    first = _ok(_park(client, headers))
    assert _code(_park(client, headers, parking_id="PK2"), 409) == "LIMIT_REACHED"
    cancelled = _ok(client.post(f"{PREFIX}/parking/PK1/cancel", headers=headers))
    assert cancelled["status"] == "CANCELLED"
    assert _claim(core, first["claim_id"]).status is ClaimStatus.RELEASED

    second = _ok(_park(client, headers, parking_id="PK2"))
    clock.set(datetime.fromisoformat(second["hold_expires_at"]))
    headers = _login(client)
    parking = _ok(client.get(f"{PREFIX}/mine", headers=headers))["parking"]

    assert {p["parking_id"]: p["status"] for p in parking} == {"PK1": "CANCELLED", "PK2": "EXPIRED"}
    assert _claim(core, second["claim_id"]).status is ClaimStatus.RELEASED
    assert core.check_invariants() == []


@pytest.mark.tc_m2_033
def test_departure_while_charging_says_to_finish_charging_first():
    """Verifies: FR-07, UC-M2-08, NFR-21.

    Expected: a private EV that arrived in a charging bay and is charging cannot depart; the
    refusal says to finish charging first. After the owner finishes charging it departs.
    """
    clock = FixedClock(CLOCK_START)
    settings = main.Settings.from_env(
        {"SECRET_KEY": "m2-parking-test-token-key-0123456789", "LOG_LEVEL": "WARNING"}
    )
    app = main.build_app(settings, clock=clock, module_names=("reservation", "charging"))
    network = NetworkSpec(
        hubs=(HubSpec("H1", "Bays", "A", 2, 2),),
        users=(UserSpec("U1", "STUDENT-1", Role.STUDENT, hash_password(PASSWORD, 1000)),),
        private_vehicles=(
            VehicleSpec("P1", "PRIVATE-1", VehicleType.E_BIKE, 40, 0.5, "U1", "TYPE2"),
        ),
    )
    core = app.state.core
    assert isinstance(core.commands.load_network(network, main.SEEDER), Ok)
    with TestClient(app) as client:
        headers = _login(client)
        booking = _ok(_park(client, headers, hub_id="H1", duration_minutes=120))
        url = f"{PREFIX}/parking/PK1"
        _ok(
            client.post(
                f"{url}/arrive", headers=headers, json={"expected_version": _version(core, "P1")}
            )
        )
        body = {"request_id": "CR1", "vehicle_id": "P1", "hub_id": "H1"}
        charging = _ok(client.post("/charging/requests/immediate", headers=headers, json=body))
        assert charging["status"] == "CHARGING"
        assert booking["parking_space_id"] == "H1-S001"

        refused = client.post(
            f"{url}/depart", headers=headers, json={"expected_version": _version(core, "P1")}
        )
        assert _code(refused, 409) == "INVALID_STATE"
        assert "still charging" in refused.json()["detail"]["message"]
        assert core.queries.get_vehicle("P1").value.state is VehicleState.CHARGING

        _ok(client.post("/charging/sessions/CR1/finish", headers=headers, json={}))
        left = _ok(
            client.post(
                f"{url}/depart", headers=headers, json={"expected_version": _version(core, "P1")}
            )
        )
        assert left["status"] == "COMPLETED"
