"""Security and authorization tests for the monitoring router endpoints (NFR-16, D-014, D-023).

Tests verify that all 11 monitoring endpoints:
1. Reject unauthenticated requests with 401 (UNAUTHENTICATED).
2. Reject student callers with 403 (FORBIDDEN).
3. Accept authorized operator callers.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from core.actor import Actor
from core.api import create_app
from core.auth import AuthConfig, hash_password
from core.clock import FixedClock
from core.domain.enums import Role
from core.facade import CoreFacade
from core.repository.memory import InMemoryRepository
from core.result import Ok
from core.seed import HubSpec, NetworkSpec, UserSpec
from monitoring import install
from monitoring.domain import IncidentSeverity, IncidentType

KEY = "test-secret-key-monitoring-auth"
COST = 1000
SIM = Actor("SIM", Role.OPERATOR, "iot_sim")

SAMPLE_PAYLOAD_CREATE = {
    "incident_type": IncidentType.HUB_VEHICLE_DEFICIT.value,
    "severity": IncidentSeverity.MEDIUM.value,
    "hub_id": "H01",
    "entity_type": "Hub",
    "entity_id": "H01",
    "description": "Deficit warning",
}

# The eleven endpoints of M5 router
ENDPOINTS = [
    # 1. Metrics - network
    ("GET", "/api/v1/monitoring/metrics/hubs", None),
    # 2. Metrics - single hub
    ("GET", "/api/v1/monitoring/metrics/hubs/H01", None),
    # 3. Capacity evaluation
    ("POST", "/api/v1/monitoring/hubs/H01/evaluate-capacity", None),
    # 4. List incidents
    ("GET", "/api/v1/monitoring/incidents", None),
    # 5. Get incident
    ("GET", "/api/v1/monitoring/incidents/INC-000001", None),
    # 6. Audit logs
    ("GET", "/api/v1/monitoring/incidents/INC-000001/logs", None),
    # 7. Create incident
    ("POST", "/api/v1/monitoring/incidents", SAMPLE_PAYLOAD_CREATE),
    # 8. Acknowledge incident
    ("POST", "/api/v1/monitoring/incidents/INC-000001/acknowledge", {}),
    # 9. Escalate incident
    ("POST", "/api/v1/monitoring/incidents/INC-000001/escalate", {"reason": "Overdue"}),
    # 10. Resolve incident
    ("POST", "/api/v1/monitoring/incidents/INC-000001/resolve", {"resolution_notes": "Resolved"}),
    # 11. Close incident
    ("POST", "/api/v1/monitoring/incidents/INC-000001/close", {}),
]


class Site:
    def __init__(self, core, clock, auth, client):
        self.core = core
        self.clock = clock
        self.auth = auth
        self.client = client

    def login(self, code: str, password: str) -> dict[str, str]:
        res = self.client.post("/auth/login", json={"code": code, "password": password})
        assert res.status_code == 200, res.text
        return {"Authorization": f"Bearer {res.json()['access_token']}"}

    def student(self) -> dict[str, str]:
        return self.login("2452001", "pw-student")

    def operator(self) -> dict[str, str]:
        return self.login("OP-1", "pw-operator")


@pytest.fixture
def site():
    repo = InMemoryRepository()
    clock = FixedClock(datetime(2026, 11, 10, 12, 0, tzinfo=UTC))
    core = CoreFacade(repo, clock)
    spec = NetworkSpec(
        hubs=(HubSpec("H01", "Metro Hub", "METRO", 5, 2),),
        users=(
            UserSpec("U1", "2452001", Role.STUDENT, hash_password("pw-student", COST)),
            UserSpec("OP1", "OP-1", Role.OPERATOR, hash_password("pw-operator", COST)),
        ),
    )
    assert isinstance(core.commands.load_network(spec, SIM), Ok)
    auth = core.authentication(AuthConfig(secret_key=KEY, token_minutes=30, hash_iterations=COST))
    app = create_app(core, auth)
    install(core, app)
    client = TestClient(app, raise_server_exceptions=False)
    return Site(core, clock, auth, client)


@pytest.mark.parametrize("method,path,payload", ENDPOINTS)
def test_all_eleven_endpoints_require_authentication(site: Site, method: str, path: str, payload):
    """NFR-16, D-014: Any request without token is rejected with 401 UNAUTHENTICATED."""
    kwargs = {"json": payload} if payload is not None else {}
    response = site.client.request(method, path, **kwargs)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.parametrize("method,path,payload", ENDPOINTS)
def test_all_eleven_endpoints_refuse_student_role(site: Site, method: str, path: str, payload):
    """NFR-16, D-014: Any student calling operator endpoints is rejected with 403 FORBIDDEN."""
    kwargs = {"headers": site.student()}
    if payload is not None:
        kwargs["json"] = payload
    response = site.client.request(method, path, **kwargs)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert response.json()["error"]["message"] == "this endpoint is for operators"


def test_operator_can_call_endpoints(site: Site):
    """Authorized operator can successfully access metrics and incident workflows."""
    headers = site.operator()

    # 1. Metrics
    res = site.client.get("/api/v1/monitoring/metrics/hubs", headers=headers)
    assert res.status_code == 200

    # 2. Create incident - reported_by is taken from authenticated operator token (OP1)
    res = site.client.post(
        "/api/v1/monitoring/incidents", json=SAMPLE_PAYLOAD_CREATE, headers=headers
    )
    assert res.status_code == 201
    ticket = res.json()
    incident_id = ticket["incident_id"]
    assert ticket["reported_by"] == "OP1"

    # 3. Acknowledge - assigned_operator_id is taken from token (OP1)
    res = site.client.post(
        f"/api/v1/monitoring/incidents/{incident_id}/acknowledge", headers=headers
    )
    assert res.status_code == 200
    assert res.json()["assigned_operator_id"] == "OP1"

    # 4. Resolve
    res = site.client.post(
        f"/api/v1/monitoring/incidents/{incident_id}/resolve",
        json={"resolution_notes": "Fixed charging cable"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "RESOLVED"

    # 5. Close
    res = site.client.post(f"/api/v1/monitoring/incidents/{incident_id}/close", headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "CLOSED"

    # 6. Audit logs
    res = site.client.get(f"/api/v1/monitoring/incidents/{incident_id}/logs", headers=headers)
    assert res.status_code == 200
    logs = res.json()
    assert len(logs) == 4
    assert all(log["changed_by"] == "OP1" for log in logs)
