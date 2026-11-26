"""The REST interface (NFR-16 roles, NFR-18 input, NFR-21 errors), on both repositories."""

import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from core.actor import Actor
from core.api import create_app
from core.auth import AuthConfig, hash_password
from core.clock import FixedClock
from core.domain.entities import UserAccount
from core.domain.enums import Role, VehicleEvent, VehicleType
from core.events import EventType
from core.facade import CoreFacade
from core.repository.memory import InMemoryRepository
from core.repository.sql import SqlRepository
from core.result import Ok
from core.seed import HubSpec, NetworkSpec, UserSpec, VehicleSpec

KEY = "test-secret-key-0123456789"  # test data, not a real secret
COST = 1000  # a cheap hash cost so the tests are fast
SIM = Actor("SIM", Role.OPERATOR, "iot_sim")


class Api:
    def __init__(self, core, repo, clock, client, auth, events):
        self.core, self.repo, self.clock, self.client, self.auth, self.events = (
            core,
            repo,
            clock,
            client,
            auth,
            events,
        )

    def token(self, code, password):
        response = self.client.post("/auth/login", json={"code": code, "password": password})
        assert response.status_code == 200, response.text
        return response.json()["access_token"]

    def headers(self, who):
        if who == "anon":
            return {}
        if who == "service":
            return {"Authorization": f"Bearer {self.auth.issue_service_token('iot_sim', 'SIM')}"}
        code, password = {
            "student": ("2452001", "pw-student"),
            "operator": ("OP-1", "pw-operator"),
        }[who]
        return {"Authorization": f"Bearer {self.token(code, password)}"}

    def get(self, path, who="operator", **params):
        return self.client.get(path, headers=self.headers(who), params=params)


@pytest.fixture(params=["memory", "sql"])
def api(request, t0):
    repo = InMemoryRepository() if request.param == "memory" else SqlRepository.open("sqlite://")
    clock = FixedClock(t0)
    core = CoreFacade(repo, clock)
    events = []
    for event_type in EventType:
        core.events.subscribe(event_type, events.append)
    users = (
        UserSpec("U1", "2452001", Role.STUDENT, hash_password("pw-student", COST)),
        UserSpec("U2", "2452002", Role.STUDENT, hash_password("pw-student-2", COST)),
        UserSpec("OP1", "OP-1", Role.OPERATOR, hash_password("pw-operator", COST)),
    )
    fleet = tuple(
        VehicleSpec(f"V{n}", f"RENT-{n}", VehicleType.E_BIKE, battery)
        for n, battery in ((1, 90.0), (2, 40.0), (3, 12.0))
    )
    private = (
        VehicleSpec(
            "P1", "EV-1", VehicleType.E_SCOOTER, 70.0, 1.0, owner_user_id="U2", connector_type="T2"
        ),
    )
    spec = NetworkSpec(
        hubs=(
            HubSpec("H01", "Metro", "METRO", 6, 2, vehicles=fleet),
            HubSpec("H02", "Dorm A", "DORM", 3, 0),
        ),
        users=users,
        private_vehicles=private,
    )
    assert isinstance(core.commands.load_network(spec, SIM), Ok)
    # the private EV of student U2 is parked at H01
    assert isinstance(core.commands.occupy_space("P1", "H01-S002", 1, SIM), Ok)
    auth = core.authentication(AuthConfig(secret_key=KEY, token_minutes=30, hash_iterations=COST))
    client = TestClient(create_app(core, auth), raise_server_exceptions=False)
    events.clear()
    yield Api(core, repo, clock, client, auth, events)
    if isinstance(repo, SqlRepository):
        repo.close()


# ----------------------------------------------------------------------------------- login


def test_login_returns_a_bearer_token(api):
    response = api.client.post("/auth/login", json={"code": "2452001", "password": "pw-student"})

    body = response.json()
    assert response.status_code == 200
    assert body["token_type"] == "bearer"
    assert (body["user_id"], body["role"]) == ("U1", "STUDENT")
    assert body["expires_at"].startswith("2026-11-02T08:30:00")
    assert "pbkdf2" not in response.text and "pw-student" not in response.text


@pytest.mark.parametrize(
    "credentials",
    [
        {"code": "2452001", "password": "wrong"},
        {"code": "NOBODY", "password": "pw-student"},
    ],
)
def test_wrong_credentials_give_401_with_the_same_message(api, credentials):
    response = api.client.post("/auth/login", json=credentials)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"] == {
        "code": "UNAUTHENTICATED",
        "message": "wrong account or password",
        "details": {},
    }


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"code": "2452001"},
        {"password": "x"},
        {"code": "", "password": "x"},
        {"code": 7, "password": []},
    ],
)
def test_a_malformed_login_is_a_400_with_a_message(api, body):
    response = api.client.post("/auth/login", json=body)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"
    assert response.json()["error"]["message"]


def test_a_login_that_is_not_json_is_a_400(api):
    response = api.client.post(
        "/auth/login", content="not json", headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 400


def test_me_names_the_caller(api):
    response = api.get("/me", "student")

    assert response.json() == {"user_id": "U1", "role": "STUDENT", "module": "ui"}


# ------------------------------------------------------------------- roles on every endpoint

ALL = ("anon", "student", "operator", "service")
SENSOR_BODY = {
    "event_id": "E1",
    "source": "sim-1",
    "type": "HEARTBEAT",
    "entity_id": "H01",
    "at": "2026-11-02T08:00:00+00:00",
}
# method, route template, a real path, body, status per caller
MATRIX = [
    ("GET", "/me", "/me", None, (401, 200, 200, 200)),
    ("GET", "/hubs", "/hubs", None, (401, 200, 200, 200)),
    ("GET", "/hubs/{hub_id}", "/hubs/H01", None, (401, 200, 200, 200)),
    ("GET", "/hubs/{hub_id}/vehicles", "/hubs/H01/vehicles", None, (401, 200, 200, 200)),
    ("GET", "/hubs/{hub_id}/spaces", "/hubs/H01/spaces", None, (401, 403, 200, 200)),
    (
        "GET",
        "/hubs/{hub_id}/charging-points",
        "/hubs/H01/charging-points",
        None,
        (401, 403, 200, 200),
    ),
    (
        "GET",
        "/vehicles/{vehicle_id}/state-log",
        "/vehicles/V1/state-log",
        None,
        (401, 403, 200, 200),
    ),
    ("POST", "/sensor-events", "/sensor-events", SENSOR_BODY, (401, 403, 403, 200)),
]
PUBLIC = {"/auth/login", "/openapi.json", "/docs", "/docs/oauth2-redirect"}


@pytest.mark.parametrize(("method", "template", "path", "body", "expected"), MATRIX)
def test_each_endpoint_gives_the_right_status_to_each_kind_of_caller(
    api, method, template, path, body, expected
):
    for who, status in zip(ALL, expected, strict=True):
        response = api.client.request(method, path, headers=api.headers(who), json=body)
        assert response.status_code == status, f"{method} {path} as {who}: {response.text}"
        if status in (401, 403):
            assert response.json()["error"]["code"] in {"UNAUTHENTICATED", "FORBIDDEN"}


def test_no_endpoint_is_missing_from_the_authorization_matrix(api):
    """NFR-16: 100 % of the endpoints have an authorization test."""
    covered = {(method, template) for method, template, *_ in MATRIX}
    schema = api.client.get("/openapi.json").json()
    actual = {
        (method.upper(), path)
        for path, operations in schema["paths"].items()
        if path not in PUBLIC
        for method in operations
    }

    assert actual == covered


@pytest.mark.parametrize(
    "header",
    ["", "Bearer", "Bearer ", "Basic abc", "bearer", "Token abc", "Bearer a.b.c"],
)
def test_a_missing_or_malformed_authorization_header_is_a_401(api, header):
    response = api.client.get("/hubs", headers={"Authorization": header})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_an_expired_token_is_a_401(api):
    headers = api.headers("student")
    assert api.client.get("/hubs", headers=headers).status_code == 200

    api.clock.advance(timedelta(minutes=30))

    assert api.client.get("/hubs", headers=headers).status_code == 401


def test_a_deactivated_user_is_locked_out_at_once(api):
    headers = api.headers("student")
    user = api.repo.get(UserAccount, "U1")
    user.is_active = False
    api.repo.update(user)

    assert api.client.get("/hubs", headers=headers).status_code == 401


# ---------------------------------------------------------------------------------- content


def test_hubs_list_has_the_numbers_of_the_dashboard(api):
    hubs = api.get("/hubs", "student").json()

    assert [h["hub_id"] for h in hubs] == ["H01", "H02"]
    metro = hubs[0]
    assert (metro["parking_capacity"], metro["occupied"], metro["free_spaces"]) == (6, 4, 2)
    assert (metro["charging_points"], metro["charging_in_use"]) == (2, 0)
    assert metro["available_vehicles"] == 3
    assert metro["status"] == "ACTIVE" and metro["version"] == 1
    assert metro["as_of"].startswith("2026-11-02T08:00:00")


def test_one_hub_and_an_unknown_hub(api):
    ok = api.get("/hubs/H02", "student")
    missing = api.get("/hubs/NOPE", "student")

    assert ok.status_code == 200 and ok.json()["name"] == "Dorm A"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"


def test_a_student_sees_only_the_rental_fleet_but_an_operator_sees_everything(api):
    student = api.get("/hubs/H01/vehicles", "student").json()
    operator = api.get("/hubs/H01/vehicles", "operator").json()

    assert [v["vehicle_id"] for v in student] == ["V1", "V2", "V3"]
    assert [v["vehicle_id"] for v in operator] == ["P1", "V1", "V2", "V3"]
    assert all(v["ownership"] == "FLEET" for v in student)
    assert "owner_user_id" not in student[0] and "connector_type" not in student[0]


def test_vehicle_filters(api):
    by_battery = api.get("/hubs/H01/vehicles", "student", min_battery=40).json()
    by_type = api.get("/hubs/H01/vehicles", "operator", type="E_SCOOTER").json()
    by_state = api.get("/hubs/H01/vehicles", "student", state="MAINTENANCE").json()
    combined = api.get("/hubs/H01/vehicles", "student", min_battery=50, type="E_BIKE").json()

    assert [v["vehicle_id"] for v in by_battery] == ["V1", "V2"]
    assert [v["vehicle_id"] for v in by_type] == ["P1"]
    assert by_state == []
    assert [v["vehicle_id"] for v in combined] == ["V1"]


@pytest.mark.parametrize(
    "params",
    [
        {"min_battery": 150},
        {"min_battery": -1},
        {"min_battery": "lots"},
        {"state": "FLYING"},
        {"type": "CAR"},
    ],
)
def test_bad_filter_values_are_400s_never_500s(api, params):
    response = api.get("/hubs/H01/vehicles", "student", **params)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"
    assert response.json()["error"]["message"]


def test_vehicles_of_an_unknown_hub_are_a_404(api):
    assert api.get("/hubs/NOPE/vehicles", "student").status_code == 404


def test_spaces_and_charging_points_for_operators(api):
    spaces = api.get("/hubs/H01/spaces", "operator").json()
    free = api.get("/hubs/H01/spaces", "operator", status="AVAILABLE").json()
    points = api.get("/hubs/H01/charging-points", "operator").json()

    assert [s["parking_space_id"] for s in spaces] == [f"H01-S00{n}" for n in range(1, 7)]
    assert [s["parking_space_id"] for s in free] == ["H01-S001", "H01-S006"]
    assert [p["charging_point_id"] for p in points] == ["H01-CP01", "H01-CP02"]
    assert points[0]["parking_space_id"] == "H01-S001"
    assert api.get("/hubs/H01/spaces", "operator", status="BROKEN").status_code == 400
    assert api.get("/hubs/NOPE/spaces", "operator").status_code == 404
    assert api.get("/hubs/NOPE/charging-points", "operator").status_code == 404


def test_the_state_log_is_newest_first_and_can_be_limited(api):
    reserve = api.core.commands.place_claim
    from core.domain.enums import HolderKind, ResourceType
    from core.services.commands import TransitionCtx

    claim = reserve(
        ResourceType.VEHICLE,
        "V1",
        HolderKind.RESERVATION,
        "R1",
        api.clock.now(),
        api.clock.now() + timedelta(minutes=10),
        Actor("U1", Role.STUDENT, "reservation"),
    )
    assert isinstance(claim, Ok)
    reserved = api.core.commands.transition_vehicle(
        "V1",
        VehicleEvent.RESERVE,
        1,
        Actor("U1", Role.STUDENT, "reservation"),
        TransitionCtx(claim_id=claim.value.claim_id),
    )
    assert isinstance(reserved, Ok)
    api.clock.advance(timedelta(minutes=1))
    api.core.commands.transition_vehicle(
        "V1", VehicleEvent.RELEASE_RESERVATION, 2, Actor("U1", Role.STUDENT, "reservation")
    )

    log = api.get("/vehicles/V1/state-log", "operator").json()
    limited = api.get("/vehicles/V1/state-log", "operator", limit=1).json()

    assert [r["trigger"] for r in log] == ["release_reservation", "reserve"]
    assert [r["trigger"] for r in limited] == ["release_reservation"]
    assert log[0]["actor"] == "reservation/U1"
    assert api.get("/vehicles/V1/state-log", "operator", limit=0).status_code == 400
    assert api.get("/vehicles/NOPE/state-log", "operator").status_code == 404


# ------------------------------------------------------------------------- sensor intake


def post_event(api, body, who="service"):
    return api.client.post("/sensor-events", headers=api.headers(who), json=body)


def test_a_valid_sensor_event_is_applied(api):
    body = dict(SENSOR_BODY, type="BATTERY_LEVEL", entity_id="V1", value=11.5, event_id="E7")

    response = post_event(api, body)

    assert response.status_code == 200
    assert response.json() == {
        "event_id": "E7",
        "type": "BATTERY_LEVEL",
        "changed": True,
        "detail": "",
    }
    assert api.core.queries.get_vehicle("V1").value.battery_pct == 11.5
    assert api.events[0].type == EventType.VEHICLE_BATTERY_CHANGED.value


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        (dict(SENSOR_BODY, type="EXPLODE"), 400, "INVALID_INPUT"),
        (dict(SENSOR_BODY, event_id=""), 400, "INVALID_INPUT"),
        (dict(SENSOR_BODY, at="yesterday"), 400, "INVALID_INPUT"),
        (dict(SENSOR_BODY, at="2026-11-02T08:00:00"), 400, "INVALID_INPUT"),  # no time zone
        (dict(SENSOR_BODY, at=12345), 400, "INVALID_INPUT"),
        (dict(SENSOR_BODY, type="BATTERY_LEVEL", entity_id="V1", value=999), 400, "INVALID_INPUT"),
        (dict(SENSOR_BODY, type="BATTERY_LEVEL", entity_id="V404", value=50), 404, "NOT_FOUND"),
        ({}, 400, "INVALID_INPUT"),
    ],
)
def test_a_bad_sensor_event_is_rejected_announced_and_changes_nothing(api, body, status, code):
    before = api.repo.export_state()

    response = post_event(api, body)

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert api.repo.export_state() == before
    assert [e.type for e in api.events] == [EventType.SENSOR_EVENT_REJECTED.value]


def test_only_the_simulator_credential_reaches_the_intake(api):
    """An operator or student is stopped at the door: core never sees the event."""
    for who in ("student", "operator"):
        response = post_event(api, SENSOR_BODY, who=who)
        assert response.status_code == 403
    assert api.events == []


@pytest.mark.parametrize("content", ["[]", '"text"', "12", "null", "{broken"])
def test_a_body_that_is_not_an_object_is_a_400(api, content):
    response = api.client.post(
        "/sensor-events",
        headers={**api.headers("service"), "Content-Type": "application/json"},
        content=content,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"


# --------------------------------------------------------------------------------- failures


def test_an_unexpected_failure_is_a_500_without_internals(api, monkeypatch):
    def boom():
        raise RuntimeError("secret internal detail: /srv/db/password")

    monkeypatch.setattr(api.core.queries, "list_hubs", boom)

    response = api.get("/hubs", "student")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secret" not in response.text and "Traceback" not in response.text


def test_the_documentation_can_be_switched_off(api):
    quiet = TestClient(create_app(api.core, api.auth, expose_docs=False))

    assert quiet.get("/openapi.json").status_code == 404
    assert quiet.get("/docs").status_code == 404
    assert api.client.get("/openapi.json").status_code == 200


def test_the_published_schema_describes_the_endpoints_and_the_error_body(api):
    schema = api.client.get("/openapi.json").json()

    assert {"/hubs", "/hubs/{hub_id}/vehicles", "/auth/login", "/sensor-events"} <= set(
        schema["paths"]
    )
    assert "ErrorOut" in json.dumps(schema)
    assert "password_hash" not in json.dumps(schema)
