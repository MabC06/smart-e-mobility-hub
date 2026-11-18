import pytest
from fastapi.testclient import TestClient

from core.auth import hash_password
from core.domain.entities import UserAccount
from core.domain.enums import Role
from core.repository.memory import InMemoryRepository
from main import Settings, build_app


@pytest.fixture
def client():
    settings = Settings.from_env(
        {
            "APP_ENV": "test",
            "SECRET_KEY": "test_secret_key_for_unit_tests_1234567890",
            "DATABASE_URL": "sqlite://",
        }
    )

    repository = InMemoryRepository()
    app = build_app(settings, repository=repository, module_names=("simulation",))

    repository.add(
        UserAccount(
            user_id="U_OPERATOR_01",
            code="OPERATOR01",
            role=Role.OPERATOR,
            password_hash=hash_password("operator123"),
        )
    )
    repository.add(
        UserAccount(
            user_id="U_STUDENT_01",
            code="STUDENT01",
            role=Role.STUDENT,
            password_hash=hash_password("student123"),
        )
    )

    return TestClient(app)


def get_token(client: TestClient, code: str, password: str) -> str:
    response = client.post(
        "/auth/login",
        json={"code": code, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_run_simulation_sc01_success(client):
    """Operator runs a supported demand-surge scenario."""
    token = get_token(client, "OPERATOR01", "operator123")
    response = client.post(
        "/simulation/runs",
        json={
            "simulation_id": "SIM_TEST_01",
            "scenario_id": "DEMAND_SURGE",
            "target_hub_ids": ["H01"],
            "surge_multiplier": 2.0,
            "duration_minutes": 60,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["simulation_id"] == "SIM_TEST_01"


def test_unsupported_scenario_sc02_returns_400(client):
    """An unsupported scenario is rejected."""
    token = get_token(client, "OPERATOR01", "operator123")
    response = client.post(
        "/simulation/runs",
        json={
            "simulation_id": "SIM_TEST_02",
            "scenario_id": "SCENARIO_02_BATTERY_DEPLETION",
            "target_hub_ids": ["H01"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "UNSUPPORTED_SCENARIO"


def test_invalid_input_returns_400(client):
    """A negative duration is rejected."""
    token = get_token(client, "OPERATOR01", "operator123")
    response = client.post(
        "/simulation/runs",
        json={
            "simulation_id": "SIM_TEST_INVALID",
            "scenario_id": "DEMAND_SURGE",
            "duration_minutes": -10,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400, response.text


def test_student_user_returns_403(client):
    """A student cannot run an operator-only simulation."""
    token = get_token(client, "STUDENT01", "student123")
    response = client.post(
        "/simulation/runs",
        json={
            "simulation_id": "SIM_TEST_03",
            "scenario_id": "DEMAND_SURGE",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403, response.text
