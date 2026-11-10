"""Tests for Allocation REST API endpoints."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from core.actor import Actor
from core.auth import AuthConfig
from core.clock import FixedClock
from core.config import CoreConfig
from core.domain.enums import Role, VehicleType
from core.facade import CoreFacade
from core.providers import ProviderPort
from core.repository.memory import InMemoryRepository
from core.result import Ok, Result
from core.seed import HubSpec, NetworkSpec, VehicleSpec, charging_point_id
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
        )
    )
    core.commands.load_network(spec, admin)
    if with_demand_provider:
        core.register_provider(ProviderPort.RESERVATION_DEMAND, _StubReservationDemand(fixed_now))

    return TestClient(app)


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
