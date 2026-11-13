"""The sign-in checks that a module router adds with ``Depends`` (NFR-16, D-014, spec 8.1).

``demo`` stands in for the router of a module (allocation, monitoring ...): it only uses
``core.api.security`` and ``core.auth.Principal``, like a real module must.
"""

from datetime import timedelta
from typing import Annotated

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from core.actor import Actor
from core.api import create_app
from core.api.security import (
    Principal,
    acting_as,
    current_principal,
    require_operator,
    require_student,
)
from core.auth import AuthConfig, hash_password
from core.clock import FixedClock
from core.domain.entities import UserAccount
from core.domain.enums import Role
from core.facade import CoreFacade
from core.repository.memory import InMemoryRepository
from core.result import Ok
from core.seed import HubSpec, NetworkSpec, UserSpec

KEY = "test-secret-key-0123456789"  # test data, not a real secret
COST = 1000  # a cheap hash cost so the tests are fast
SIM = Actor("SIM", Role.OPERATOR, "iot_sim")

demo = APIRouter(prefix="/demo")


@demo.get("/any")
def any_user(who: Annotated[Principal, Depends(current_principal)]) -> dict[str, str]:
    return {"user": who.user_id, "role": who.role.value}


@demo.get("/operator")
def operator_only(who: Annotated[Principal, Depends(require_operator)]) -> dict[str, str]:
    return {"actor": acting_as(who, "allocation").label()}


@demo.get("/student")
def student_only(who: Annotated[Principal, Depends(require_student)]) -> dict[str, str]:
    return {"user": who.user_id}


PATHS = ["/demo/any", "/demo/operator", "/demo/student"]


class Site:
    def __init__(self, repo, clock, auth, client):
        self.repo, self.clock, self.auth, self.client = repo, clock, auth, client

    def login(self, code, password):
        response = self.client.post("/auth/login", json={"code": code, "password": password})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def student(self):
        return self.login("2452001", "pw-student")

    def operator(self):
        return self.login("OP-1", "pw-operator")


@pytest.fixture
def site(t0):
    repo = InMemoryRepository()
    clock = FixedClock(t0)
    core = CoreFacade(repo, clock)
    spec = NetworkSpec(
        hubs=(HubSpec("H01", "Metro", "METRO", 4, 0),),
        users=(
            UserSpec("U1", "2452001", Role.STUDENT, hash_password("pw-student", COST)),
            UserSpec("OP1", "OP-1", Role.OPERATOR, hash_password("pw-operator", COST)),
        ),
    )
    assert isinstance(core.commands.load_network(spec, SIM), Ok)
    auth = core.authentication(AuthConfig(secret_key=KEY, token_minutes=30, hash_iterations=COST))
    app = create_app(core, auth)
    app.include_router(demo)
    return Site(repo, clock, auth, TestClient(app, raise_server_exceptions=False))


# ------------------------------------------------------------------------------- no sign-in


@pytest.mark.parametrize("path", PATHS)
def test_no_token_gives_401_with_the_one_error_body(site, path):
    response = site.client.get(path)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.parametrize(
    "header",
    ["Basic abc", "Bearer", "Bearer ", "Bearer not-a-token", "token-without-a-scheme", ""],
)
def test_a_wrong_scheme_or_a_bad_token_gives_401(site, header):
    response = site.client.get("/demo/any", headers={"Authorization": header})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.parametrize("scheme", ["Basic", "Token", "Bearertoken"])
def test_a_valid_token_under_another_scheme_gives_401(site, scheme):
    token = site.student()["Authorization"].removeprefix("Bearer ")

    response = site.client.get("/demo/any", headers={"Authorization": f"{scheme} {token}"})

    assert response.status_code == 401


def test_the_scheme_name_is_not_case_sensitive(site):
    token = site.student()["Authorization"].removeprefix("Bearer ")

    response = site.client.get("/demo/any", headers={"Authorization": f"bearer {token}"})

    assert response.status_code == 200


def test_a_tampered_token_gives_401(site):
    token = site.student()["Authorization"].removeprefix("Bearer ")
    tampered = token[:-2] + ("AA" if not token.endswith("AA") else "BB")

    response = site.client.get("/demo/any", headers={"Authorization": f"Bearer {tampered}"})

    assert response.status_code == 401


def test_an_expired_token_gives_401(site):
    headers = site.student()
    site.clock.set(site.clock.now() + timedelta(minutes=31))

    assert site.client.get("/demo/any", headers=headers).status_code == 401


def test_a_deactivated_account_gives_401_even_with_a_valid_token(site):
    headers = site.student()
    site.repo.update(UserAccount("U1", "2452001", Role.STUDENT, is_active=False))

    assert site.client.get("/demo/any", headers=headers).status_code == 401


# --------------------------------------------------------------------------------- roles


def test_any_signed_in_user_passes_current_principal(site):
    student = site.client.get("/demo/any", headers=site.student())
    operator = site.client.get("/demo/any", headers=site.operator())

    assert student.json() == {"user": "U1", "role": "STUDENT"}
    assert operator.json() == {"user": "OP1", "role": "OPERATOR"}


def test_an_operator_endpoint_refuses_a_student_with_403(site):
    response = site.client.get("/demo/operator", headers=site.student())

    assert response.status_code == 403
    assert response.json()["error"] == {
        "code": "FORBIDDEN",
        "message": "this endpoint is for operators",
        "details": {},
    }


def test_an_operator_endpoint_accepts_an_operator_and_a_service_credential(site):
    by_operator = site.client.get("/demo/operator", headers=site.operator())
    service = {"Authorization": f"Bearer {site.auth.issue_service_token('iot_sim', 'SIM')}"}
    by_service = site.client.get("/demo/operator", headers=service)

    assert by_operator.status_code == 200
    assert by_service.status_code == 200


def test_a_student_endpoint_refuses_an_operator_with_403(site):
    response = site.client.get("/demo/student", headers=site.operator())

    assert response.status_code == 403
    assert response.json()["error"]["message"] == "this endpoint is for students"


def test_a_student_endpoint_accepts_a_student(site):
    response = site.client.get("/demo/student", headers=site.student())

    assert response.json() == {"user": "U1"}


# ------------------------------------------------------------------------------ the actor


def test_acting_as_names_the_module_and_keeps_the_user_and_the_role():
    actor = acting_as(Principal("OP1", Role.OPERATOR, "ui"), "allocation")

    assert actor == Actor("OP1", Role.OPERATOR, "allocation")
    assert actor.label() == "allocation/OP1"


def test_the_actor_of_an_endpoint_carries_the_module_that_runs_the_command(site):
    response = site.client.get("/demo/operator", headers=site.operator())

    assert response.json() == {"actor": "allocation/OP1"}


# ------------------------------------------------------------------------------- set-up


def test_create_app_keeps_the_auth_service_for_the_module_routers(site):
    assert site.client.app.state.auth is site.auth


def test_an_application_built_without_create_app_fails_loudly_not_open():
    app = FastAPI()
    app.include_router(demo)

    response = TestClient(app, raise_server_exceptions=False).get("/demo/any")

    assert response.status_code == 500
