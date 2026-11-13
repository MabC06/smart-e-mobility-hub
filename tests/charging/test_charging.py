from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from charging import install
from charging.models import ChargingSessionStatus
from charging.router import create_charging_router
from charging.service import ChargingQueueService
from core.actor import Actor
from core.api.security import Principal, current_principal, require_operator
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
from core.facade import CoreFacade
from core.providers import ProviderPort
from core.repository.memory import InMemoryRepository
from core.result import Ok

T0 = datetime(2026, 11, 8, 8, 0, tzinfo=UTC)
STUDENT = Actor("STU1", Role.STUDENT, "ui")


def _setup(
    config: CoreConfig | None = None,
) -> tuple[CoreFacade, FixedClock, ChargingQueueService]:
    repo = InMemoryRepository()
    repo.add(Hub("H1", "Hub 1", "Z1", 5, 1))
    repo.add(UserAccount("STU1", "2452030", Role.STUDENT))
    repo.add(ParkingSpace("H1-S001", "H1", "S1", SpaceStatus.OCCUPIED, "V-DOCKED"))
    repo.add(ChargingPoint("H1-CP01", "H1", "H1-S001", 10.0, ChargingPointStatus.AVAILABLE))

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
    core = CoreFacade(repo, clock, config)
    return core, clock, install(core)


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
    assert client.post("/charging/schedule/optimize").status_code == 403


def test_charging_router_endpoints_success() -> None:
    core, clock, service = _setup()

    app = FastAPI()
    app.include_router(create_charging_router(service, core))

    student_principal = Principal(user_id="STU1", role=Role.STUDENT, module="charging")
    app.dependency_overrides[current_principal] = lambda: student_principal

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

    student_principal = Principal(user_id="STU1", role=Role.STUDENT, module="charging")
    app.dependency_overrides[current_principal] = lambda: student_principal

    client = TestClient(app)

    response = client.get("/charging/queue?hub_id=H1")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_charging_router_demand_endpoint() -> None:
    core, clock, service = _setup()

    app = FastAPI()
    app.include_router(create_charging_router(service, core))

    student_principal = Principal(user_id="STU1", role=Role.STUDENT, module="charging")
    app.dependency_overrides[current_principal] = lambda: student_principal

    client = TestClient(app)

    response = client.get("/charging/demand?hub_id=H1&horizon_minutes=60")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
