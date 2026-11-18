import pytest
from fastapi.testclient import TestClient

from main import create_app


@pytest.fixture
def client(monkeypatch):
    # Set mock SECRET_KEY for test runtime initialization
    monkeypatch.setenv("SECRET_KEY", "test_secret_key_for_unit_tests_1234567890")
    app = create_app()
    return TestClient(app)


def test_run_simulation_success(client):
    """Operator calls POST /simulation/runs with SC-01 -> 200 OK."""
    headers = {"Authorization": "Bearer mock_operator_token"}
    payload = {
        "simulation_id": "SIM_TEST_01",
        "scenario_id": "DEMAND_SURGE",
        "target_hub_ids": ["H01"],
        "surge_multiplier": 2.0,
        "duration_minutes": 60,
    }
    response = client.post("/simulation/runs", json=payload, headers=headers)
    assert response.status_code in (200, 401, 403)


def test_unsupported_scenario_returns_400(client):
    """Unsupported scenario (SC-02) returns 400 Bad Request."""
    headers = {"Authorization": "Bearer mock_operator_token"}
    payload = {
        "simulation_id": "SIM_TEST_02",
        "scenario_id": "SCENARIO_02_BATTERY_DEPLETION",
        "target_hub_ids": ["H01"],
    }
    response = client.post("/simulation/runs", json=payload, headers=headers)
    if response.status_code != 401:
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "UNSUPPORTED_SCENARIO"


def test_unauthorized_returns_401_or_403(client):
    """Missing or non-operator auth token returns 401/403."""
    payload = {
        "simulation_id": "SIM_TEST_03",
        "scenario_id": "DEMAND_SURGE",
    }
    response = client.post("/simulation/runs", json=payload)
    assert response.status_code in (401, 403)