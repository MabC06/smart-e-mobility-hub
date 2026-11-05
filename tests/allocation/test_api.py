"""Tests for Allocation REST API endpoints."""

import pytest
from fastapi.testclient import TestClient

from core.actor import Actor
from core.auth import AuthConfig
from core.config import CoreConfig
from core.domain.enums import Role, VehicleType
from core.facade import CoreFacade
from core.repository.memory import InMemoryRepository
from core.seed import HubSpec, NetworkSpec, VehicleSpec
from main import Settings, build_app


@pytest.fixture
def client():
    repo = InMemoryRepository()
    admin = Actor("OP01", Role.OPERATOR, "core")

    settings = Settings(
        core=CoreConfig(),
        auth=AuthConfig(secret_key="secret-key-at-least-32-bytes-long-padding!"),
    )
    app = build_app(settings, repository=repo, module_names=("allocation",))

    core: CoreFacade = app.state.core
    spec = NetworkSpec(
        hubs=(
            HubSpec(
                "H01",
                "Hub 1",
                "Z1",
                10,
                0,
                vehicles=tuple(
                    VehicleSpec(f"V00{i}", f"PLATE-{i}", VehicleType.E_BIKE, 80.0) for i in range(6)
                ),
            ),
            HubSpec("H02", "Hub 2", "Z2", 10, 0),
        )
    )
    core.commands.load_network(spec, admin)

    return TestClient(app)


def test_plan_and_list_tasks_api(client):
    # Plan
    res = client.post("/allocation/tasks/plan", json={"slot_id": "test_slot"})
    assert res.status_code == 200
    tasks = res.json()
    assert len(tasks) >= 1
    task_id = tasks[0]["task_id"]

    # List
    list_res = client.get("/allocation/tasks")
    assert list_res.status_code == 200
    assert any(t["task_id"] == task_id for t in list_res.json())

    # Get
    get_res = client.get(f"/allocation/tasks/{task_id}")
    assert get_res.status_code == 200
    assert get_res.json()["task_id"] == task_id


def test_suggest_alternative_hubs_api(client):
    res = client.get("/allocation/alternatives/hubs?requested_hub_id=H02&require_vehicle=true")
    assert res.status_code == 200
    data = res.json()
    assert "candidates" in data
    assert any(c["hub_id"] == "H01" for c in data["candidates"])


def test_arbitrate_api(client):
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


def test_task_lifecycle_api(client):
    plan_res = client.post("/allocation/tasks/plan", json={"slot_id": "slot_api"})
    assert plan_res.status_code == 200
    tasks = plan_res.json()
    assert len(tasks) >= 1
    task_id = tasks[0]["task_id"]

    # Approve
    app_res = client.post(f"/allocation/tasks/{task_id}/approve")
    assert app_res.status_code == 200
    assert app_res.json()["status"] == "APPROVED"

    # Pickup
    pick_res = client.post(f"/allocation/tasks/{task_id}/pickup")
    assert pick_res.status_code == 200
    assert pick_res.json()["status"] == "IN_PROGRESS"

    # Return
    ret_res = client.post(f"/allocation/tasks/{task_id}/return")
    assert ret_res.status_code == 200
    assert ret_res.json()["status"] == "COMPLETED"


def test_cancel_task_api(client):
    plan_res = client.post("/allocation/tasks/plan", json={"slot_id": "slot_cancel"})
    task_id = plan_res.json()[0]["task_id"]

    cancel_res = client.post(
        f"/allocation/tasks/{task_id}/cancel",
        json={"reason": "Operator test cancel"},
    )
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"


def test_suggest_alternative_charging_api(client):
    body = {
        "displaced_requests": [{"request_id": "REQ-1"}],
        "failed_hub_id": "H01",
    }
    res = client.post("/allocation/alternatives/charging", json=body)
    assert res.status_code == 200
    assert isinstance(res.json(), list)
