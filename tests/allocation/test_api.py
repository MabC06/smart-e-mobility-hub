"""Tests for Allocation REST API endpoints."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from core.actor import Actor
from core.auth import AuthConfig, hash_password
from core.clock import FixedClock
from core.config import CoreConfig
from core.domain.enums import Role, VehicleType
from core.facade import CoreFacade
from core.providers import ProviderPort
from core.repository.memory import InMemoryRepository
from core.result import Ok, Result
from core.seed import HubSpec, NetworkSpec, UserSpec, VehicleSpec, charging_point_id
from main import Settings, build_app


@dataclass(frozen=True, slots=True)
class _EmptyBookings:
    as_of: datetime
    horizon_end: datetime
    bookings: tuple[object, ...] = ()


@dataclass(frozen=True, slots=True)
class _EmptyTrips:
    as_of: datetime
    trips: tuple[object, ...] = ()


class _StubReservationDemand:
    def __init__(self, as_of: datetime) -> None:
        self._as_of = as_of

    def upcoming_bookings(self, hub_id: str, horizon: timedelta) -> Result[_EmptyBookings]:
        return Ok(_EmptyBookings(self._as_of, self._as_of + horizon))

    def open_trips(self, hub_id: str) -> Result[_EmptyTrips]:
        return Ok(_EmptyTrips(self._as_of))


def _make_client(*, with_demand_provider: bool = True) -> TestClient:
    repo = InMemoryRepository()
    fixed_now = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
    admin = Actor("OP01", Role.OPERATOR, "core")

    settings = Settings(
        core=CoreConfig(),
        auth=AuthConfig(secret_key="secret-key-at-least-32-bytes-long-padding!"),
    )
    app = build_app(
        settings,
        repository=repo,
        clock=FixedClock(fixed_now),
        module_names=("allocation",),
    )

    core: CoreFacade = app.state.core
    spec = NetworkSpec(
        hubs=(
            HubSpec(
                "H01",
                "Hub 1",
                "Z1",
                10,
                1,
                vehicles=tuple(
                    VehicleSpec(f"V00{i}", f"PLATE-{i}", VehicleType.E_BIKE, 80.0) for i in range(6)
                ),
            ),
            HubSpec("H02", "Hub 2", "Z2", 10, 1),
        ),
        users=(
            UserSpec("OP01", "OP-01", Role.OPERATOR, hash_password("pw-operator", 1000)),
            UserSpec("STU01", "STU-01", Role.STUDENT, hash_password("pw-student", 1000)),
        ),
    )
    core.commands.load_network(spec, admin)
    if with_demand_provider:
        core.register_provider(ProviderPort.RESERVATION_DEMAND, _StubReservationDemand(fixed_now))

    token = app.state.auth.issue_service_token("allocation", "OP01")
    return TestClient(app, headers={"Authorization": f"Bearer {token}"})


@pytest.fixture
def client() -> TestClient:
    return _make_client(with_demand_provider=True)


def test_plan_and_list_tasks_api(client: TestClient) -> None:
    res = client.post("/allocation/tasks/plan", json={"slot_id": "test_slot"})
    assert res.status_code == 200
    tasks = res.json()
    assert len(tasks) >= 1
    task_id = tasks[0]["task_id"]

    list_res = client.get("/allocation/tasks")
    assert list_res.status_code == 200
    assert any(t["task_id"] == task_id for t in list_res.json())

    get_res = client.get(f"/allocation/tasks/{task_id}")
    assert get_res.status_code == 200
    assert get_res.json()["task_id"] == task_id


def test_plan_returns_503_when_reservation_demand_missing() -> None:
    client_no_provider = _make_client(with_demand_provider=False)
    res = client_no_provider.post("/allocation/tasks/plan", json={"slot_id": "test_slot"})
    assert res.status_code == 503
    assert res.json()["detail"]["code"] == "RESOURCE_UNAVAILABLE"


def test_suggest_alternative_hubs_api(client: TestClient) -> None:
    res = client.get("/allocation/alternatives/hubs?requested_hub_id=H02&require_vehicle=true")
    assert res.status_code == 200
    data = res.json()
    assert "candidates" in data
    assert any(c["hub_id"] == "H01" for c in data["candidates"])

    bad_res = client.get("/allocation/alternatives/hubs?requested_hub_id=H02&limit=0")
    assert bad_res.status_code == 400


def test_arbitrate_api(client: TestClient) -> None:
    body = {
        "requests": [
            {
                "request_id": "R1",
                "request_class": 4,
                "requested_at": "2026-11-05T10:00:00Z",
                "requester_id": "U1",
                "target_resource_id": "CP1",
            },
            {
                "request_id": "R2",
                "request_class": 2,
                "requested_at": "2026-11-05T10:05:00Z",
                "requester_id": "U2",
                "target_resource_id": "CP1",
            },
        ]
    }
    res = client.post("/allocation/arbitrate", json=body)
    assert res.status_code == 200
    assert res.json()["winner_request_id"] == "R2"


def test_task_lifecycle_api(client: TestClient) -> None:
    plan_res = client.post("/allocation/tasks/plan", json={"slot_id": "slot_api"})
    assert plan_res.status_code == 200
    tasks = plan_res.json()
    assert len(tasks) >= 1
    task_id = tasks[0]["task_id"]

    app_res = client.post(f"/allocation/tasks/{task_id}/approve")
    assert app_res.status_code == 200
    assert app_res.json()["status"] == "APPROVED"

    pick_res = client.post(f"/allocation/tasks/{task_id}/pickup")
    assert pick_res.status_code == 200
    assert pick_res.json()["status"] == "IN_PROGRESS"

    ret_res = client.post(f"/allocation/tasks/{task_id}/return")
    assert ret_res.status_code == 200
    assert ret_res.json()["status"] == "COMPLETED"


def test_cancel_task_api(client: TestClient) -> None:
    plan_res = client.post("/allocation/tasks/plan", json={"slot_id": "slot_cancel"})
    task_id = plan_res.json()[0]["task_id"]

    cancel_res = client.post(
        f"/allocation/tasks/{task_id}/cancel",
        json={"reason": "Operator test cancel"},
    )
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"


def test_suggest_alternative_charging_api(client: TestClient) -> None:
    body = {
        "displaced_requests": [{"request_id": "REQ-1"}],
        "failed_hub_id": "H01",
    }
    res = client.post("/allocation/alternatives/charging", json=body)
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["status"] == "FOUND"
    assert data[0]["alternative_hub_id"] == "H02"
    assert data[0]["charging_point_id"] == charging_point_id("H02", 1)


def test_config_endpoints(client: TestClient) -> None:
    get_res = client.get("/allocation/config")
    assert get_res.status_code == 200
    cfg = get_res.json()
    assert cfg["horizon_minutes"] == 30
    assert cfg["safety_stock"] == 3
    assert cfg["min_dispatch_battery"] == 30.0

    put_res = client.put(
        "/allocation/config",
        json={"safety_stock": 5, "min_dispatch_battery": 45.0},
    )
    assert put_res.status_code == 200
    updated = put_res.json()
    assert updated["status"] == "updated"
    assert updated["config"]["safety_stock"] == 5
    assert updated["config"]["min_dispatch_battery"] == 45.0

    get_res2 = client.get("/allocation/config")
    assert get_res2.status_code == 200
    assert get_res2.json()["safety_stock"] == 5


def test_endpoints_reject_unauthenticated() -> None:
    """NFR-16, D-014, D-023: Requests without bearer token return 401 UNAUTHENTICATED."""
    raw_client = _make_client()
    raw_client.headers.clear()

    endpoints: list[tuple[str, str, dict[str, object] | None]] = [
        ("POST", "/allocation/tasks/plan", {"slot_id": "s1"}),
        ("GET", "/allocation/tasks", None),
        ("GET", "/allocation/tasks/TASK-1", None),
        ("POST", "/allocation/tasks/TASK-1/approve", {}),
        ("POST", "/allocation/tasks/TASK-1/pickup", None),
        ("POST", "/allocation/tasks/TASK-1/return", {}),
        ("POST", "/allocation/tasks/TASK-1/cancel", {}),
        ("GET", "/allocation/alternatives/hubs?requested_hub_id=H01", None),
        (
            "POST",
            "/allocation/alternatives/charging",
            {"displaced_requests": [], "failed_hub_id": "H01"},
        ),
        ("POST", "/allocation/arbitrate", {"requests": []}),
        ("GET", "/allocation/config", None),
        ("PUT", "/allocation/config", {}),
    ]
    for method, path, json_body in endpoints:
        if method == "GET":
            res = raw_client.get(path)
        elif method == "POST":
            res = raw_client.post(path, json=json_body)
        elif method == "PUT":
            res = raw_client.put(path, json=json_body)
        assert res.status_code == 401, f"{method} {path} gave {res.status_code}"
        assert res.headers["www-authenticate"] == "Bearer"
        assert res.json()["error"]["code"] == "UNAUTHENTICATED"


def test_endpoints_refuse_student_with_403() -> None:
    """NFR-16, D-023: Operator endpoints return 403 FORBIDDEN for student tokens."""
    client = _make_client()
    login_res = client.post("/auth/login", json={"code": "STU-01", "password": "pw-student"})
    assert login_res.status_code == 200
    student_token = login_res.json()["access_token"]
    student_headers = {"Authorization": f"Bearer {student_token}"}

    endpoints: list[tuple[str, str, dict[str, object] | None]] = [
        ("POST", "/allocation/tasks/plan", {"slot_id": "s1"}),
        ("GET", "/allocation/tasks", None),
        ("GET", "/allocation/tasks/TASK-1", None),
        ("POST", "/allocation/tasks/TASK-1/approve", {}),
        ("POST", "/allocation/tasks/TASK-1/pickup", None),
        ("POST", "/allocation/tasks/TASK-1/return", {}),
        ("POST", "/allocation/tasks/TASK-1/cancel", {}),
        ("GET", "/allocation/alternatives/hubs?requested_hub_id=H01", None),
        (
            "POST",
            "/allocation/alternatives/charging",
            {"displaced_requests": [], "failed_hub_id": "H01"},
        ),
        ("POST", "/allocation/arbitrate", {"requests": []}),
        ("GET", "/allocation/config", None),
        ("PUT", "/allocation/config", {}),
    ]
    for method, path, json_body in endpoints:
        if method == "GET":
            res = client.get(path, headers=student_headers)
        elif method == "POST":
            res = client.post(path, json=json_body, headers=student_headers)
        elif method == "PUT":
            res = client.put(path, json=json_body, headers=student_headers)
        assert res.status_code == 403, f"{method} {path} gave {res.status_code}"
        assert res.json()["error"]["code"] == "FORBIDDEN"
