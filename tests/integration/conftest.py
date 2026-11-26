"""Shared fixtures for full-application integration tests (M8)."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

import main
from core.actor import Actor
from core.auth import hash_password
from core.domain.enums import Role, VehicleType
from core.repository.sql import SqlRepository
from core.result import Err
from core.seed import HubSpec, NetworkSpec, UserSpec, VehicleSpec

TEST_SECRET = "integration-test-secret-key"


def _settings() -> main.Settings:
    return main.Settings.from_env(
        {
            "SECRET_KEY": TEST_SECRET,
            "LOG_LEVEL": "WARNING",
            "PASSWORD_HASH_ITERATIONS": "1000",
        }
    )


def _network() -> NetworkSpec:
    users = (
        UserSpec("U-STUDENT", "STU-TEST", Role.STUDENT, hash_password("student-pass", 1000)),
        UserSpec("U-OPERATOR", "OPS-TEST", Role.OPERATOR, hash_password("operator-pass", 1000)),
    )
    return NetworkSpec(
        hubs=(
            HubSpec(
                "H01",
                "Integration Hub One",
                "CAMPUS",
                4,
                1,
                vehicles=(
                    VehicleSpec("V001", "FLEET-001", VehicleType.E_BIKE, 40.0),
                    VehicleSpec("V002", "FLEET-002", VehicleType.E_SCOOTER, 75.0),
                ),
            ),
            HubSpec(
                "H02",
                "Integration Hub Two",
                "CAMPUS",
                3,
                1,
                vehicles=(VehicleSpec("V003", "FLEET-003", VehicleType.E_BIKE, 85.0),),
            ),
        ),
        users=users,
    )


@pytest.fixture
def integration_client() -> Iterator[tuple[TestClient, main.FastAPI]]:
    """Build the real composition root on an isolated SQL repository and seed small data."""
    repository = SqlRepository.open("sqlite://")
    app = main.build_app(_settings(), repository=repository)
    loaded = app.state.core.commands.load_network(
        _network(), Actor("SIM", Role.OPERATOR, "iot_sim")
    )
    assert not isinstance(loaded, Err), getattr(loaded, "message", "network seed failed")
    with TestClient(app) as client:
        yield client, app
    repository.close()


def login(client: TestClient, code: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"code": code, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def student_headers(integration_client) -> dict[str, str]:
    client, _ = integration_client
    return login(client, "STU-TEST", "student-pass")


@pytest.fixture
def operator_headers(integration_client) -> dict[str, str]:
    client, _ = integration_client
    return login(client, "OPS-TEST", "operator-pass")
