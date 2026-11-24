"""Cross-module checks through the actual FastAPI composition root.

Traceability: TC-M8-016..TC-M8-020; Core API spec v1.2 §§6, 8; D-020, D-023.
"""

from datetime import timedelta

from core.providers import ProviderPort
from core.result import Ok


def login(client, code, password):
    response = client.post("/auth/login", json={"code": code, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_build_app_installs_the_expected_modules_and_routes(integration_client):
    client, app = integration_client

    assert app.state.reservation is not None
    assert app.state.reservation_lifecycle is not None
    assert app.state.charging is not None
    assert app.state.simulation_service is not None

    openapi_response = client.get("/openapi.json")
    assert openapi_response.status_code == 200

    paths = set(openapi_response.json()["paths"])

    assert "/charging/queue" in paths
    assert "/allocation/tasks" in paths
    assert "/api/v1/monitoring/incidents" in paths

    # UI routes may be excluded from the OpenAPI schema.
    ui_login_response = client.get("/ui/login")
    assert ui_login_response.status_code != 404


def test_provider_registration_matches_the_phase_3_contract(integration_client):
    _, app = integration_client
    providers = app.state.core.providers

    assert providers.is_registered(ProviderPort.CHARGING_DEMAND)
    assert providers.is_registered(ProviderPort.ALTERNATIVE_HUB)
    assert providers.is_registered(ProviderPort.ALTERNATIVE_CHARGING)
    # M2 registers ReservationDemand (PR #54); HoldConsumer stays unregistered.
    assert providers.is_registered(ProviderPort.RESERVATION_DEMAND)
    assert not providers.is_registered(ProviderPort.HOLD_CONSUMER)

    demand = providers.call(
        ProviderPort.RESERVATION_DEMAND,
        lambda provider: provider.upcoming_bookings("H01", timedelta(hours=1)),
    )
    assert isinstance(demand, Ok)


def test_charging_demand_provider_is_callable_through_core(integration_client):
    _, app = integration_client

    result = app.state.core.providers.call(
        ProviderPort.CHARGING_DEMAND,
        lambda provider: provider.scheduled_sessions("H01", timedelta(hours=1)),
    )

    assert isinstance(result, Ok)
    assert result.value == []


def test_core_read_api_requires_authentication_and_returns_seeded_hubs(integration_client):
    client, _ = integration_client

    assert client.get("/hubs").status_code == 401
    headers = login(client, "STU-TEST", "student-pass")
    response = client.get("/hubs", headers=headers)

    assert response.status_code == 200
    assert {hub["hub_id"] for hub in response.json()} == {"H01", "H02"}


def test_operator_only_module_endpoints_reject_student(integration_client):
    client, _ = integration_client
    student = login(client, "STU-TEST", "student-pass")

    assert client.get("/charging/queue", headers=student).status_code == 403
    assert client.get("/allocation/tasks", headers=student).status_code == 403
    assert client.get("/api/v1/monitoring/incidents", headers=student).status_code == 403


def test_operator_can_read_charging_allocation_and_monitoring_views(integration_client):
    client, _ = integration_client
    operator = login(client, "OPS-TEST", "operator-pass")

    charging = client.get("/charging/queue", headers=operator)
    allocation = client.get("/allocation/tasks", headers=operator)
    monitoring = client.get("/api/v1/monitoring/incidents", headers=operator)

    assert charging.status_code == 200, charging.text
    assert allocation.status_code == 200, allocation.text
    assert monitoring.status_code == 200, monitoring.text
    assert charging.json() == []
    assert allocation.json() == []
    assert monitoring.json() == []


def test_allocation_alternative_hub_endpoint_uses_installed_provider(integration_client):
    client, _ = integration_client
    operator = login(client, "OPS-TEST", "operator-pass")

    response = client.get(
        "/allocation/alternatives/hubs",
        params={"requested_hub_id": "H01", "require_vehicle": "true", "limit": 2},
        headers=operator,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert "candidates" in body
    assert "as_of" in body
    assert "reason_code" in body
