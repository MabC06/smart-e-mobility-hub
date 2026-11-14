from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from charging import install, schema
from charging.models import ChargingError, ChargingErrorCode, ChargingSessionStatus
from charging.router import create_charging_router
from charging.service import ChargingQueueService
from core.actor import Actor
from core.api import create_app as create_core_app
from core.api.security import Principal, current_principal, require_operator
from core.auth import AuthConfig, hash_password
from core.clock import FixedClock
from core.config import CoreConfig
from core.domain.entities import ChargingPoint, Hub, ParkingSpace, UserAccount, Vehicle
from core.domain.enums import (
    ChargingPointStatus,
    Ownership,
    Role,
    SpaceStatus,
    VehicleState,
    VehicleType,
)
from core.errors import ErrorCode
from core.facade import CoreFacade
from core.providers import ProviderPort
from core.repository.memory import InMemoryRepository
from core.result import Err, Ok

T0 = datetime(2026, 11, 8, 8, 0, tzinfo=UTC)
PW_HASH = hash_password("pw", iterations=1)
STUDENT = Actor("STU1", Role.STUDENT, "ui")
STUDENT_2 = Actor("STU2", Role.STUDENT, "ui")
OPERATOR = Actor("OP1", Role.OPERATOR, "ui")


def _build_core(
    config: CoreConfig | None = None,
) -> tuple[CoreFacade, FixedClock]:
    repo = InMemoryRepository()
    repo.add(Hub("H1", "Hub 1", "Z1", 5, 1))
    repo.add(UserAccount("STU1", "2452030", Role.STUDENT, password_hash=PW_HASH))
    repo.add(UserAccount("STU2", "2452031", Role.STUDENT, password_hash=PW_HASH))
    repo.add(UserAccount("OP1", "OP-01", Role.OPERATOR, password_hash=PW_HASH))
    repo.add(ParkingSpace("H1-S001", "H1", "S1", SpaceStatus.OCCUPIED, "V-DOCKED"))
    repo.add(ParkingSpace("H1-S002", "H1", "S2", SpaceStatus.AVAILABLE, None))
    repo.add(ChargingPoint("H1-CP01", "H1", "H1-S001", 10.0, ChargingPointStatus.AVAILABLE))
    repo.add(ChargingPoint("H1-CP02", "H1", "H1-S002", 10.0, ChargingPointStatus.AVAILABLE))

    vehicles = [
        ("V-DOCKED", "P-00", 50.0, "H1-S001"),
        ("V-149", "P-149", 14.9, None),
        ("V-150", "P-150", 15.0, None),
        ("V-151", "P-151", 15.1, None),
        ("V-400", "P-400", 40.0, None),
    ]
    for vid, plate, soc, space_id in vehicles:
        repo.add(
            Vehicle(
                vid,
                plate,
                Ownership.FLEET,
                VehicleType.E_BIKE,
                soc,
                2.0,
                state=VehicleState.AVAILABLE,
                hub_id="H1",
                parking_space_id=space_id,
            )
        )

    clock = FixedClock(T0)
    return CoreFacade(repo, clock, config), clock


def _setup(
    config: CoreConfig | None = None,
) -> tuple[CoreFacade, FixedClock, ChargingQueueService]:
    core, clock = _build_core(config)
    return core, clock, install(core)


def _api() -> tuple[CoreFacade, FixedClock, ChargingQueueService, TestClient]:
    """Core's real app (auth, error handlers) with the charging module installed on it."""
    core, clock = _build_core()
    auth = core.authentication(
        AuthConfig(secret_key="test-secret-key-0123456789", hash_iterations=1)
    )
    app = create_core_app(core, auth)
    service = install(core, app)
    return core, clock, service, TestClient(app)


def _bearer(client: TestClient, code: str) -> dict[str, str]:
    res = client.post("/auth/login", json={"code": code, "password": "pw"})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.mark.parametrize(
    ("vehicle_id", "expected_emergency"),
    [
        ("V-149", True),
        ("V-150", True),
        ("V-151", False),
        ("V-400", False),
    ],
)
def test_battery_threshold_bva(vehicle_id: str, expected_emergency: bool) -> None:
    """BVA around 15.0% threshold: 14.9% and 15.0% are emergency; 15.1% is not."""
    _, _, service = _setup()
    res = service.submit_charging_request(f"REQ-{vehicle_id}", vehicle_id, "H1", STUDENT)
    assert isinstance(res, Ok)
    assert res.value.status is ChargingSessionStatus.QUEUED
    assert res.value.is_emergency is expected_emergency


def test_priority_queue_ordering() -> None:
    """Priority queue v1 puts <= 15.0% first, then orders by lowest SoC and FIFO."""
    _, clock, service = _setup()
    submissions = [
        ("R-151", "V-151"),
        ("R-400", "V-400"),
        ("R-150", "V-150"),
        ("R-149", "V-149"),
    ]
    for rid, vid in submissions:
        assert isinstance(service.submit_charging_request(rid, vid, "H1", STUDENT), Ok)
        clock.advance(timedelta(minutes=1))

    ranked = service.compute_priority_queue("H1")
    assert [r.vehicle_id for r in ranked] == ["V-149", "V-150", "V-151", "V-400"]


def test_threshold_reads_from_core_config() -> None:
    """Custom CoreConfig low_battery_threshold overrides the 15.0% default (D-005)."""
    _, _, service = _setup(CoreConfig(low_battery_threshold=20.0))
    res = service.submit_charging_request("R-151", "V-151", "H1", STUDENT)
    assert isinstance(res, Ok)
    assert res.value.is_emergency is True


def test_charging_lifecycle_and_d020_provider() -> None:
    """Immediate request starts/finishes charging; D-020 provider returns scheduled sessions."""
    core, _, service = _setup()
    started = service.submit_charging_request("REQ-NOW", "V-DOCKED", "H1", STUDENT, target_soc=90.0)
    assert isinstance(started, Ok)
    assert started.value.status is ChargingSessionStatus.CHARGING

    finished = service.finish_charging("REQ-NOW", STUDENT, final_soc=90.0)
    assert isinstance(finished, Ok)
    assert finished.value.status is ChargingSessionStatus.COMPLETED

    scheduled = service.submit_charging_request(
        "REQ-FUT",
        "V-149",
        "H1",
        STUDENT,
        target_soc=80.0,
        start_at=T0 + timedelta(minutes=30),
        duration_minutes=30,
    )
    assert isinstance(scheduled, Ok)

    demand = core.providers.call(
        ProviderPort.CHARGING_DEMAND,
        lambda p: p.scheduled_sessions("H1", timedelta(hours=2)),
    )
    assert isinstance(demand, Ok)
    assert [row.session_id for row in demand.value] == ["REQ-FUT"]


def test_modify_and_cancel_schedule() -> None:
    """Scheduled request can be modified to a new time slot or cancelled."""
    core, clock, service = _setup()

    start_t = T0 + timedelta(hours=1)
    scheduled = service.submit_charging_request(
        "REQ-MOD",
        "V-149",
        "H1",
        STUDENT,
        target_soc=80.0,
        start_at=start_t,
        duration_minutes=30,
    )
    assert isinstance(scheduled, Ok)
    assert scheduled.value.status is ChargingSessionStatus.SCHEDULED

    new_start_t = T0 + timedelta(hours=2)
    modified = service.modify_charging_schedule("REQ-MOD", new_start_t, 45, STUDENT)
    assert isinstance(modified, Ok)
    assert modified.value.start_time == new_start_t

    cancelled = service.cancel_charging_schedule("REQ-MOD", STUDENT)
    assert isinstance(cancelled, Ok)
    assert cancelled.value.status is ChargingSessionStatus.CANCELLED


def test_interrupt_charging_session() -> None:
    """Active charging session can be prematurely interrupted and cancelled."""
    core, _, service = _setup()

    started = service.submit_charging_request("REQ-INT", "V-DOCKED", "H1", STUDENT, target_soc=90.0)
    assert isinstance(started, Ok)
    assert started.value.status is ChargingSessionStatus.CHARGING
    interrupted = service.interrupt_charging("REQ-INT", STUDENT, current_soc=60.0)
    assert isinstance(interrupted, Ok)
    assert interrupted.value.status is ChargingSessionStatus.INTERRUPTED
    assert interrupted.value.current_soc == 60.0


def test_charging_router_security_401_403() -> None:
    core, clock, service = _setup()

    app = FastAPI()
    app.include_router(create_charging_router(service, core))
    client = TestClient(app)

    app.dependency_overrides[current_principal] = lambda: (_ for _ in ()).throw(
        HTTPException(status_code=401, detail="Not authenticated")
    )
    assert client.get("/charging/sessions").status_code == 401

    student_principal = Principal(user_id="STU1", role=Role.STUDENT, module="charging")
    app.dependency_overrides[current_principal] = lambda: student_principal
    app.dependency_overrides[require_operator] = lambda: (_ for _ in ()).throw(
        HTTPException(status_code=403, detail="Operator role required")
    )
    assert client.post("/charging/schedule/optimize?hub_id=H1").status_code == 403
    assert client.get("/charging/queue?hub_id=H1").status_code == 403
    assert client.get("/charging/demand?hub_id=H1").status_code == 403


def test_charging_router_endpoints_success() -> None:
    core, clock, service = _setup()

    app = FastAPI()
    app.include_router(create_charging_router(service, core))

    student_principal = Principal(user_id="STU1", role=Role.STUDENT, module="charging")
    operator_principal = Principal(user_id="OP1", role=Role.OPERATOR, module="charging")
    app.dependency_overrides[current_principal] = lambda: student_principal
    app.dependency_overrides[require_operator] = lambda: operator_principal

    client = TestClient(app)

    response_sessions = client.get("/charging/sessions")
    assert response_sessions.status_code == 200
    assert isinstance(response_sessions.json(), list)

    response_demand = client.get("/charging/demand?hub_id=H1&horizon_minutes=60")
    assert response_demand.status_code == 200
    assert isinstance(response_demand.json(), list)


def test_charging_router_private_endpoints() -> None:
    core, clock, service = _setup()

    app = FastAPI()
    app.include_router(create_charging_router(service, core))

    operator_principal = Principal(user_id="OP1", role=Role.OPERATOR, module="charging")
    app.dependency_overrides[current_principal] = lambda: operator_principal
    app.dependency_overrides[require_operator] = lambda: operator_principal

    client = TestClient(app)

    response = client.get("/charging/queue?hub_id=H1")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_charging_router_demand_endpoint() -> None:
    core, clock, service = _setup()

    app = FastAPI()
    app.include_router(create_charging_router(service, core))

    operator_principal = Principal(user_id="OP1", role=Role.OPERATOR, module="charging")
    app.dependency_overrides[current_principal] = lambda: operator_principal
    app.dependency_overrides[require_operator] = lambda: operator_principal

    client = TestClient(app)

    response = client.get("/charging/demand?hub_id=H1&horizon_minutes=60")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


# --- M3-19 Additional Core State & Security Tests ---

STUDENT_P = Principal(user_id="STU1", role=Role.STUDENT, module="charging")
STUDENT_2_P = Principal(user_id="STU2", role=Role.STUDENT, module="charging")
OPERATOR_P = Principal(user_id="OP1", role=Role.OPERATOR, module="charging")


def _client(
    core: CoreFacade,
    service: ChargingQueueService,
    principal: Principal,
    *,
    operator: Principal | None = None,
) -> TestClient:
    """TestClient acting as `principal`; `operator` also overrides require_operator."""
    app = FastAPI()
    app.include_router(create_charging_router(service, core))
    app.dependency_overrides[current_principal] = lambda: principal
    if operator is not None:
        app.dependency_overrides[require_operator] = lambda: operator
    return TestClient(app)


def _core_state(
    core: CoreFacade, vehicle_id: str, point_id: str
) -> tuple[VehicleState, ChargingPointStatus]:
    """Read the vehicle state and charging-point status straight from Core."""
    with core.unit_of_work() as uow:
        veh = uow.queries.get_vehicle(vehicle_id)
        assert isinstance(veh, Ok)
        points = {p.charging_point_id: p for p in uow.queries.list_charging_points("H1")}
        return veh.value.state, points[point_id].status


def _claim_ids(core: CoreFacade, point_id: str, start: datetime, end: datetime) -> set[str]:
    with core.unit_of_work() as uow:
        return {c.claim_id for c in uow.queries.get_claims(point_id, start, end)}


def _schedule_docked(service: ChargingQueueService, request_id: str = "REQ-SCHED"):
    """SCHEDULED session for the docked vehicle, starting T0 + 30 min."""
    res = service.submit_charging_request(
        request_id,
        "V-DOCKED",
        "H1",
        STUDENT,
        target_soc=80.0,
        start_at=T0 + timedelta(minutes=30),
        duration_minutes=30,
    )
    assert isinstance(res, Ok)
    assert res.value.status is ChargingSessionStatus.SCHEDULED
    assert res.value.charger_id == "H1-CP01"
    return res.value


ALL_ENDPOINTS = [
    ("post", "/charging/requests/immediate"),
    ("post", "/charging/requests/schedule"),
    ("post", "/charging/sessions/X/start"),
    ("post", "/charging/sessions/X/finish"),
    ("post", "/charging/sessions/X/interrupt"),
    ("patch", "/charging/requests/X"),
    ("delete", "/charging/requests/X"),
    ("post", "/charging/private/vehicles"),
    ("post", "/charging/private/slots"),
    ("get", "/charging/queue?hub_id=H1"),
    ("post", "/charging/schedule/optimize?hub_id=H1"),
    ("get", "/charging/sessions"),
    ("get", "/charging/demand?hub_id=H1"),
]


def test_install_mounts_router_and_every_endpoint_needs_a_token() -> None:
    """install() mounts /charging on the app; no token gives 401 on every endpoint (M3-13)."""
    _, _, _, client = _api()

    for method, path in ALL_ENDPOINTS:
        res = getattr(client, method)(path)
        assert res.status_code == 401, (method, path, res.status_code)
        bad = getattr(client, method)(path, headers={"Authorization": "Bearer garbage"})
        assert bad.status_code == 401, (method, path, bad.status_code)


def test_student_gets_403_on_operator_endpoints_through_app() -> None:
    """A student token is rejected with 403 on /queue, /demand and /schedule/optimize."""
    _, _, _, client = _api()
    student = _bearer(client, "2452030")

    for method, path in (
        ("get", "/charging/queue?hub_id=H1"),
        ("get", "/charging/demand?hub_id=H1"),
        ("post", "/charging/schedule/optimize?hub_id=H1"),
    ):
        res = getattr(client, method)(path, headers=student)
        assert res.status_code == 403, (method, path)
        assert res.json()["error"]["code"] == "FORBIDDEN"


def test_operator_token_reaches_operator_endpoints_through_app() -> None:
    _, _, _, client = _api()
    operator = _bearer(client, "OP-01")

    assert client.get("/charging/queue?hub_id=H1", headers=operator).status_code == 200
    assert client.get("/charging/demand?hub_id=H1", headers=operator).status_code == 200
    assert client.post("/charging/schedule/optimize?hub_id=H1", headers=operator).status_code == 200


def test_schedule_start_finish_lifecycle_through_app() -> None:
    """Token-authenticated flow: schedule, start by owner only, finish; state checked in Core."""
    core, clock, _, client = _api()
    owner = _bearer(client, "2452030")
    other = _bearer(client, "2452031")
    operator = _bearer(client, "OP-01")

    res = client.post(
        "/charging/requests/schedule",
        headers=owner,
        json={
            "request_id": "R-APP-1",
            "vehicle_id": "V-DOCKED",
            "hub_id": "H1",
            "start_at": (T0 + timedelta(minutes=30)).isoformat(),
            "duration_minutes": 30,
            "target_soc": 80.0,
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "SCHEDULED"

    assert client.post("/charging/sessions/R-APP-1/start", headers=owner).status_code == 409
    clock.advance(timedelta(minutes=30))
    assert client.post("/charging/sessions/R-APP-1/start", headers=other).status_code == 404

    started = client.post("/charging/sessions/R-APP-1/start", headers=owner)
    assert started.status_code == 200
    assert _core_state(core, "V-DOCKED", "H1-CP01") == (
        VehicleState.CHARGING,
        ChargingPointStatus.CHARGING,
    )

    done = client.post("/charging/sessions/R-APP-1/finish", headers=owner, json={"final_soc": 80.0})
    assert done.status_code == 200
    assert done.json()["status"] == "COMPLETED"

    mine = client.get("/charging/sessions", headers=owner).json()
    assert [r["request_id"] for r in mine] == ["R-APP-1"]
    assert client.get("/charging/sessions", headers=other).json() == []
    assert [r["request_id"] for r in client.get("/charging/sessions", headers=operator).json()] == [
        "R-APP-1"
    ]


def test_operator_allowed_on_operator_endpoints() -> None:
    core, _, service = _setup()
    client = _client(core, service, OPERATOR_P, operator=OPERATOR_P)

    assert client.get("/charging/queue?hub_id=H1").status_code == 200
    assert client.get("/charging/demand?hub_id=H1&horizon_minutes=60").status_code == 200


def test_private_vehicle_creation_and_ownership() -> None:
    """/private/vehicles creates a PRIVATE vehicle owned by the caller (checked in Core)."""
    core, _, service = _setup()
    client = _client(core, service, STUDENT_P)

    res = client.post(
        "/charging/private/vehicles",
        json={
            "plate_or_code": "PRIV123",
            "vehicle_type": "E_BIKE",
            "battery_capacity_kwh": 2.5,
            "current_soc": 30.0,
            "connector_type": "Type2",
        },
    )
    assert res.status_code == 200
    created_vehicle_id = res.json()["vehicle_id"]
    assert created_vehicle_id == "V-PRIV-PRIV123"

    with core.unit_of_work() as uow:
        veh_res = uow.queries.get_vehicle(created_vehicle_id)
        assert isinstance(veh_res, Ok)
        assert veh_res.value.ownership is Ownership.PRIVATE
        assert veh_res.value.owner_user_id == "STU1"
        assert veh_res.value.battery_pct == 30.0


def test_private_vehicle_owner_comes_from_principal_not_body() -> None:
    """A second student registering gets their own ownership."""
    core, _, service = _setup()
    client = _client(core, service, STUDENT_2_P)

    res = client.post(
        "/charging/private/vehicles",
        json={
            "plate_or_code": "PRIV999",
            "vehicle_type": "E_BIKE",
            "battery_capacity_kwh": 2.0,
            "current_soc": 20.0,
            "connector_type": "Type2",
        },
    )
    assert res.status_code == 200
    with core.unit_of_work() as uow:
        veh_res = uow.queries.get_vehicle(res.json()["vehicle_id"])
        assert isinstance(veh_res, Ok)
        assert veh_res.value.owner_user_id == "STU2"


def test_optimize_queue_turns_queued_into_scheduled() -> None:
    """optimize_queue binds a QUEUED request to a free bay and claims it in Core."""
    core, _, service = _setup()
    occupied = service.submit_charging_request("REQ-OCC", "V-DOCKED", "H1", STUDENT)
    assert isinstance(occupied, Ok)
    assert occupied.value.status is ChargingSessionStatus.CHARGING
    assert occupied.value.charger_id == "H1-CP01"

    queued = service.submit_charging_request("REQ-Q", "V-149", "H1", STUDENT)
    assert isinstance(queued, Ok)
    assert schema.read(core, "REQ-Q").status is ChargingSessionStatus.QUEUED

    res_opt = service.optimize_queue("H1", OPERATOR)
    assert isinstance(res_opt, Ok)
    assert [r.request_id for r in res_opt.value] == ["REQ-Q"]

    req = schema.read(core, "REQ-Q")
    assert req.status is ChargingSessionStatus.SCHEDULED
    assert req.charger_id == "H1-CP02"
    assert req.start_time == T0
    assert req.end_time == T0 + timedelta(minutes=60)
    assert req.point_claim_id in _claim_ids(core, "H1-CP02", req.start_time, req.end_time)
    # Scheduled only: the vehicle is not started and the point stays free.
    assert _core_state(core, "V-149", "H1-CP02") == (
        VehicleState.AVAILABLE,
        ChargingPointStatus.AVAILABLE,
    )


def test_optimize_endpoint_requires_hub_id_and_returns_sessions() -> None:
    core, _, service = _setup()
    assert isinstance(service.submit_charging_request("REQ-OCC", "V-DOCKED", "H1", STUDENT), Ok)
    assert isinstance(service.submit_charging_request("REQ-Q", "V-149", "H1", STUDENT), Ok)
    client = _client(core, service, OPERATOR_P, operator=OPERATOR_P)

    assert client.post("/charging/schedule/optimize").status_code == 422
    res = client.post("/charging/schedule/optimize?hub_id=H1")
    assert res.status_code == 200
    assert [(s["request_id"], s["status"]) for s in res.json()] == [("REQ-Q", "SCHEDULED")]
    assert schema.read(core, "REQ-Q").status is ChargingSessionStatus.SCHEDULED


def test_start_scheduled_session_unknown_id_is_not_found() -> None:
    _, clock, service = _setup()
    _schedule_docked(service)
    clock.advance(timedelta(minutes=30))

    missing = service.start_scheduled_session("NON-EXISTENT", STUDENT)
    assert isinstance(missing, ChargingError)
    assert missing.code is ChargingErrorCode.NOT_FOUND


def test_start_scheduled_session_before_start_time_changes_nothing() -> None:
    """Before start_time: INVALID_STATE and Core state is untouched."""
    core, _, service = _setup()
    _schedule_docked(service)

    res = service.start_scheduled_session("REQ-SCHED", STUDENT)
    assert isinstance(res, ChargingError)
    assert res.code is ChargingErrorCode.INVALID_STATE
    assert schema.read(core, "REQ-SCHED").status is ChargingSessionStatus.SCHEDULED
    assert _core_state(core, "V-DOCKED", "H1-CP01") == (
        VehicleState.AVAILABLE,
        ChargingPointStatus.AVAILABLE,
    )


def test_start_scheduled_session_by_other_student_changes_nothing() -> None:
    """Another student gets NOT_FOUND even when the session is due; Core is untouched."""
    core, clock, service = _setup()
    _schedule_docked(service)
    clock.advance(timedelta(minutes=30))

    res = service.start_scheduled_session("REQ-SCHED", STUDENT_2)
    assert isinstance(res, ChargingError)
    assert res.code is ChargingErrorCode.NOT_FOUND
    assert schema.read(core, "REQ-SCHED").status is ChargingSessionStatus.SCHEDULED
    assert _core_state(core, "V-DOCKED", "H1-CP01") == (
        VehicleState.AVAILABLE,
        ChargingPointStatus.AVAILABLE,
    )


def test_start_scheduled_session_after_start_time_updates_core_then_finish() -> None:
    """Due session: vehicle, point and session are all CHARGING, so finish succeeds."""
    core, clock, service = _setup()
    _schedule_docked(service)
    clock.advance(timedelta(minutes=30))

    started = service.start_scheduled_session("REQ-SCHED", STUDENT)
    assert isinstance(started, Ok)
    assert started.value.status is ChargingSessionStatus.CHARGING
    assert schema.read(core, "REQ-SCHED").status is ChargingSessionStatus.CHARGING
    assert _core_state(core, "V-DOCKED", "H1-CP01") == (
        VehicleState.CHARGING,
        ChargingPointStatus.CHARGING,
    )

    again = service.start_scheduled_session("REQ-SCHED", STUDENT)
    assert isinstance(again, ChargingError)
    assert again.code is ChargingErrorCode.INVALID_STATE

    finished = service.finish_charging("REQ-SCHED", STUDENT, final_soc=80.0)
    assert isinstance(finished, Ok)
    assert finished.value.status is ChargingSessionStatus.COMPLETED
    vehicle_state, point_status = _core_state(core, "V-DOCKED", "H1-CP01")
    assert vehicle_state is not VehicleState.CHARGING
    assert point_status is ChargingPointStatus.AVAILABLE


def test_start_scheduled_session_operator_allowed() -> None:
    """An operator may start another user's due SCHEDULED session."""
    core, clock, service = _setup()
    _schedule_docked(service)
    clock.advance(timedelta(minutes=30))

    res = service.start_scheduled_session("REQ-SCHED", OPERATOR)
    assert isinstance(res, Ok)
    assert res.value.status is ChargingSessionStatus.CHARGING
    assert _core_state(core, "V-DOCKED", "H1-CP01")[0] is VehicleState.CHARGING


def test_start_endpoint_before_and_after_start_time() -> None:
    core, clock, service = _setup()
    _schedule_docked(service)
    owner = _client(core, service, STUDENT_P)
    other = _client(core, service, STUDENT_2_P)

    assert owner.post("/charging/sessions/REQ-SCHED/start").status_code == 409
    clock.advance(timedelta(minutes=30))
    assert other.post("/charging/sessions/REQ-SCHED/start").status_code == 404
    assert owner.post("/charging/sessions/NOPE/start").status_code == 404

    res = owner.post("/charging/sessions/REQ-SCHED/start")
    assert res.status_code == 200
    assert res.json()["status"] == "CHARGING"
    assert _core_state(core, "V-DOCKED", "H1-CP01") == (
        VehicleState.CHARGING,
        ChargingPointStatus.CHARGING,
    )
    assert owner.post("/charging/sessions/REQ-SCHED/finish", json={}).status_code == 200


def _point_event(point_id: str, new: ChargingPointStatus) -> object:
    return type(
        "MockEvent",
        (),
        {"payload": {"charging_point_id": point_id, "hub_id": "H1", "new": new}},
    )()


def test_point_failure_moves_session_to_other_bay() -> None:
    """CP01 fails mid-charge: the session is interrupted and re-booked on CP02 (UC-M3-08)."""
    core, _, service = _setup()
    res = service.submit_charging_request("REQ-S1", "V-DOCKED", "H1", STUDENT)
    assert isinstance(res, Ok)
    assert res.value.status is ChargingSessionStatus.CHARGING
    assert res.value.charger_id == "H1-CP01"

    # Take CP01 out of service in Core, then deliver the status-change event.
    with core.unit_of_work() as uow:
        cp01 = next(
            p for p in uow.queries.list_charging_points("H1") if p.charging_point_id == "H1-CP01"
        )
        out = uow.commands.set_charging_point_status(
            "H1-CP01", ChargingPointStatus.OUT_OF_SERVICE, cp01.version, OPERATOR
        )
        assert isinstance(out, Ok)
        assert not isinstance(uow.commit(), Err)
    # Idempotent if the bus already delivered it.
    service._on_point_status_changed(_point_event("H1-CP01", ChargingPointStatus.OUT_OF_SERVICE))

    old = schema.read(core, "REQ-S1")
    assert old.status is ChargingSessionStatus.INTERRUPTED
    moved = schema.read(core, "REQ-S1-R1")
    assert moved is not None
    assert moved.user_id == "STU1"
    assert moved.vehicle_id == "V-DOCKED"
    assert moved.status is ChargingSessionStatus.SCHEDULED
    assert moved.charger_id == "H1-CP02"
    window = (moved.start_time, moved.end_time)
    assert moved.point_claim_id in _claim_ids(core, "H1-CP02", *window)
    assert _claim_ids(core, "H1-CP01", T0, T0 + timedelta(hours=2)) == set()
    assert _core_state(core, "V-DOCKED", "H1-CP01")[1] is ChargingPointStatus.OUT_OF_SERVICE


def test_point_available_event_schedules_queued_request() -> None:
    """A point becoming AVAILABLE triggers optimize_queue (UC-M3-07, UC-M3-08)."""
    core, _, service = _setup()
    assert isinstance(service.submit_charging_request("REQ-OCC", "V-DOCKED", "H1", STUDENT), Ok)
    queued = service.submit_charging_request("REQ-Q", "V-149", "H1", STUDENT)
    assert isinstance(queued, Ok)
    assert queued.value.status is ChargingSessionStatus.QUEUED

    service._on_point_status_changed(_point_event("H1-CP02", ChargingPointStatus.AVAILABLE))

    req = schema.read(core, "REQ-Q")
    assert req.status is ChargingSessionStatus.SCHEDULED
    assert req.charger_id == "H1-CP02"


def test_point_status_event_without_data_is_ignored() -> None:
    core, _, service = _setup()
    assert isinstance(service.submit_charging_request("REQ-S1", "V-DOCKED", "H1", STUDENT), Ok)

    service._on_point_status_changed(type("E", (), {"payload": {}})())

    assert schema.read(core, "REQ-S1").status is ChargingSessionStatus.CHARGING


def test_stub_reservation_demand_provider_prioritizes_booked() -> None:
    """A stub RESERVATION_DEMAND provider puts the booked vehicle first (after emergencies)."""
    core, clock, service = _setup()
    for rid, vid in (("R-400", "V-400"), ("R-151", "V-151"), ("R-149", "V-149")):
        res = service.submit_charging_request(rid, vid, "H1", STUDENT)
        assert isinstance(res, Ok)
        assert res.value.status is ChargingSessionStatus.QUEUED
        clock.advance(timedelta(minutes=1))

    # Without bookings: emergency first, then lowest SoC.
    baseline = [r.vehicle_id for r in service.compute_priority_queue("H1")]
    assert baseline == ["V-149", "V-151", "V-400"]

    class _StubReservationDemand:
        def upcoming_bookings(self, hub_id: str, horizon: timedelta):
            return Ok(SimpleNamespace(bookings=[SimpleNamespace(vehicle_id="V-400")]))

    core.register_provider(ProviderPort.RESERVATION_DEMAND, _StubReservationDemand())

    ranked = service.compute_priority_queue("H1")
    assert [r.vehicle_id for r in ranked] == ["V-149", "V-400", "V-151"]
    assert [r.is_emergency for r in ranked] == [True, False, False]


def test_student_sees_only_own_sessions() -> None:
    """/sessions returns only the caller's rows for students; operators see all."""
    core, _, service = _setup()
    assert isinstance(service.submit_charging_request("REQ-STU1", "V-DOCKED", "H1", STUDENT), Ok)
    assert isinstance(service.submit_charging_request("REQ-STU2", "V-149", "H1", STUDENT_2), Ok)
    assert schema.read(core, "REQ-STU1").user_id == "STU1"
    assert schema.read(core, "REQ-STU2").user_id == "STU2"

    def ids(principal: Principal) -> set[str]:
        res = _client(core, service, principal).get("/charging/sessions")
        assert res.status_code == 200
        return {s["request_id"] for s in res.json()}

    assert ids(STUDENT_P) == {"REQ-STU1"}
    assert ids(STUDENT_2_P) == {"REQ-STU2"}
    assert ids(OPERATOR_P) == {"REQ-STU1", "REQ-STU2"}


def test_reservation_demand_error_falls_back_to_battery_only() -> None:
    """On Err from RESERVATION_DEMAND the queue ranks by battery only (BR-M3-03)."""
    core, clock, service = _setup()
    for rid, vid in (("R-400", "V-400"), ("R-151", "V-151")):
        assert isinstance(service.submit_charging_request(rid, vid, "H1", STUDENT), Ok)
        clock.advance(timedelta(minutes=1))

    class _UnavailableReservationDemand:
        def upcoming_bookings(self, hub_id: str, horizon: timedelta):
            return Err(ErrorCode.RESOURCE_UNAVAILABLE, "M2 is down")

    core.register_provider(ProviderPort.RESERVATION_DEMAND, _UnavailableReservationDemand())

    ranked = service.compute_priority_queue("H1")
    assert [r.vehicle_id for r in ranked] == ["V-151", "V-400"]


def test_immediate_endpoint_conflict_when_no_bay_and_no_queue() -> None:
    core, _, service = _setup()
    client = _client(core, service, STUDENT_P)

    res = client.post(
        "/charging/requests/immediate",
        json={
            "request_id": "R-NOQ",
            "vehicle_id": "V-149",
            "hub_id": "H1",
            "target_soc": 80.0,
            "queue_if_full": False,
        },
    )
    assert res.status_code == 409
    assert schema.read(core, "R-NOQ") is None


def test_request_endpoints_immediate_interrupt_and_schedule_lifecycle() -> None:
    """immediate -> interrupt, then schedule -> modify -> cancel, checked in Core."""
    core, _, service = _setup()
    client = _client(core, service, STUDENT_P)

    started = client.post(
        "/charging/requests/immediate",
        json={
            "request_id": "R-API-1",
            "vehicle_id": "V-DOCKED",
            "hub_id": "H1",
            "target_soc": 90.0,
        },
    )
    assert started.status_code == 200
    assert started.json()["status"] == "CHARGING"
    assert _core_state(core, "V-DOCKED", "H1-CP01")[0] is VehicleState.CHARGING

    stopped = client.post("/charging/sessions/R-API-1/interrupt", json={"current_soc": 60.0})
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "INTERRUPTED"
    assert schema.read(core, "R-API-1").current_soc == 60.0
    assert _core_state(core, "V-DOCKED", "H1-CP01")[0] is not VehicleState.CHARGING

    first_start = T0 + timedelta(hours=1)
    scheduled = client.post(
        "/charging/requests/schedule",
        json={
            "request_id": "R-API-2",
            "vehicle_id": "V-149",
            "hub_id": "H1",
            "start_at": first_start.isoformat(),
            "duration_minutes": 30,
            "target_soc": 80.0,
        },
    )
    assert scheduled.status_code == 200
    assert scheduled.json()["status"] == "SCHEDULED"

    new_start = T0 + timedelta(hours=2)
    modified = client.patch(
        "/charging/requests/R-API-2",
        json={"start_at": new_start.isoformat(), "duration_minutes": 45},
    )
    assert modified.status_code == 200
    req = schema.read(core, "R-API-2")
    assert req.start_time == new_start
    assert req.end_time == new_start + timedelta(minutes=45)
    assert req.point_claim_id in _claim_ids(core, req.charger_id, req.start_time, req.end_time)

    cancelled = client.delete("/charging/requests/R-API-2")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    assert _claim_ids(core, req.charger_id, req.start_time, req.end_time) == set()


def test_other_student_cannot_modify_or_cancel_via_api() -> None:
    core, _, service = _setup()
    assert isinstance(
        service.submit_charging_request(
            "R-OWN",
            "V-149",
            "H1",
            STUDENT,
            target_soc=80.0,
            start_at=T0 + timedelta(hours=1),
            duration_minutes=30,
        ),
        Ok,
    )
    other = _client(core, service, STUDENT_2_P)

    patched = other.patch(
        "/charging/requests/R-OWN",
        json={
            "start_at": (T0 + timedelta(hours=2)).isoformat(),
            "duration_minutes": 30,
        },
    )
    assert patched.status_code == 404
    assert other.delete("/charging/requests/R-OWN").status_code == 404
    assert schema.read(core, "R-OWN").status is ChargingSessionStatus.SCHEDULED


def test_private_vehicle_can_reserve_slot() -> None:
    """Register a private EV, then reserve a slot for it (UC-M3-04, UC-M3-05)."""
    core, _, service = _setup()
    client = _client(core, service, STUDENT_P)

    reg = client.post(
        "/charging/private/vehicles",
        json={
            "plate_or_code": "PRIV42",
            "vehicle_type": "E_BIKE",
            "battery_capacity_kwh": 2.5,
            "current_soc": 30.0,
            "connector_type": "Type2",
        },
    )
    assert reg.status_code == 200

    slot = client.post(
        "/charging/private/slots",
        json={
            "request_id": "R-PRIV-1",
            "vehicle_id": reg.json()["vehicle_id"],
            "hub_id": "H1",
            "start_at": (T0 + timedelta(hours=1)).isoformat(),
            "duration_minutes": 30,
            "target_soc": 80.0,
        },
    )
    assert slot.status_code == 200
    assert slot.json()["status"] == "SCHEDULED"
    req = schema.read(core, "R-PRIV-1")
    assert req.user_id == "STU1"
    assert req.vehicle_id == reg.json()["vehicle_id"]


def _queued_three(service: ChargingQueueService) -> list[str]:
    ids = ["R-149", "R-150", "R-151"]
    for rid, vid in zip(ids, ("V-149", "V-150", "V-151"), strict=True):
        res = service.submit_charging_request(rid, vid, "H1", STUDENT)
        assert isinstance(res, Ok)
        assert res.value.status is ChargingSessionStatus.QUEUED
    return ids


def test_optimize_queue_binds_three_requests_on_two_bays_without_overlap() -> None:
    """Three QUEUED requests, two bays: all SCHEDULED, no overlap on one point (M3-13)."""
    core, _, service = _setup()
    ids = _queued_three(service)

    res = service.optimize_queue("H1", OPERATOR)

    assert isinstance(res, Ok)
    assert [r.request_id for r in res.value] == ids  # priority order: 14.9, 15.0, 15.1
    bound = [schema.read(core, rid) for rid in ids]
    assert all(r.status is ChargingSessionStatus.SCHEDULED for r in bound)
    assert {r.charger_id for r in bound} == {"H1-CP01", "H1-CP02"}
    for i, first in enumerate(bound):
        assert first.point_claim_id in _claim_ids(
            core, first.charger_id, first.start_time, first.end_time
        )
        for second in bound[i + 1 :]:
            if first.charger_id == second.charger_id:
                assert first.end_time <= second.start_time or second.end_time <= first.start_time


def test_optimize_endpoint_binds_three_queued_requests() -> None:
    """POST /schedule/optimize returns 200 with all three requests SCHEDULED."""
    core, _, service = _setup()
    ids = _queued_three(service)
    client = _client(core, service, OPERATOR_P, operator=OPERATOR_P)

    res = client.post("/charging/schedule/optimize?hub_id=H1")

    assert res.status_code == 200
    assert [(s["request_id"], s["status"]) for s in res.json()] == [
        (rid, "SCHEDULED") for rid in ids
    ]
    assert all(schema.read(core, rid).status is ChargingSessionStatus.SCHEDULED for rid in ids)


def test_optimize_queue_leaves_requests_queued_when_no_slot() -> None:
    """With no free slot in the 2-hour window a request stays QUEUED, no error."""
    core, _, service = _setup()
    for rid, vid in (("BLK-1", "V-DOCKED"), ("BLK-2", "V-400")):
        blocker = service.submit_charging_request(
            rid, vid, "H1", STUDENT, target_soc=100.0, start_at=T0, duration_minutes=240
        )
        assert isinstance(blocker, Ok)
        assert blocker.value.status is ChargingSessionStatus.SCHEDULED
    assert isinstance(service.submit_charging_request("R-Q", "V-149", "H1", STUDENT), Ok)

    res = service.optimize_queue("H1", OPERATOR)

    assert isinstance(res, Ok)
    assert res.value == []
    assert schema.read(core, "R-Q").status is ChargingSessionStatus.QUEUED
