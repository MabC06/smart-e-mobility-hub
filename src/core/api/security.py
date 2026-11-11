"""Sign-in checks for REST endpoints, for ``core`` and for the routers of the modules.

Rules (NFR-16, D-014, core-api-spec.md section 8.1):
- A request needs a bearer token. No token, a wrong scheme, a bad, tampered or expired token, or
  an account that was deactivated gives 401 (``UNAUTHENTICATED``).
- A caller with the wrong role gives 403 (``FORBIDDEN``).
- The module never reads a token itself: it adds one dependency to the endpoint and gets the
  caller back as a ``Principal``. ``acting_as`` turns it into the ``Actor`` a command needs.

A module router uses it like this::

    from typing import Annotated
    from fastapi import APIRouter, Depends
    from core.api.security import Principal, acting_as, require_operator

    router = APIRouter()

    @router.post("/tasks/{task_id}/approve")
    def approve(task_id: str, who: Annotated[Principal, Depends(require_operator)]):
        actor = acting_as(who, "allocation")
        ...

The dependencies read the ``AuthService`` from ``app.state.auth``, which ``core.api.create_app``
sets, so a module does not need to know how the application was built.
"""

from typing import Annotated

from fastapi import Depends, Header, Request

from core.actor import Actor
from core.api.errors import ApiError, fail
from core.auth import AuthService, Principal
from core.domain.enums import Role
from core.errors import ErrorCode
from core.result import Err

__all__ = [
    "Principal",
    "acting_as",
    "check_bearer",
    "check_role",
    "current_principal",
    "require_operator",
    "require_student",
]


def check_bearer(auth: AuthService, authorization: str | None) -> Principal:
    """The caller behind an ``Authorization: Bearer <token>`` header, or a 401."""
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise fail(ErrorCode.UNAUTHENTICATED, "missing, invalid or expired token")
    result = auth.authenticate(token.strip())
    if isinstance(result, Err):
        raise ApiError(result)
    return result.value


def check_role(principal: Principal, role: Role, message: str) -> Principal:
    """The same caller if it has the role, or a 403 with the message."""
    if principal.role is not role:
        raise fail(ErrorCode.FORBIDDEN, message)
    return principal


def current_principal(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> Principal:
    """Any signed-in user: student or operator."""
    auth = getattr(request.app.state, "auth", None)
    if not isinstance(auth, AuthService):
        raise RuntimeError(
            "app.state.auth is not an AuthService: build the application with core.api.create_app"
        )
    return check_bearer(auth, authorization)


def require_operator(who: Annotated[Principal, Depends(current_principal)]) -> Principal:
    """A signed-in operator. A student gets 403."""
    return check_role(who, Role.OPERATOR, "this endpoint is for operators")


def require_student(who: Annotated[Principal, Depends(current_principal)]) -> Principal:
    """A signed-in student. An operator gets 403."""
    return check_role(who, Role.STUDENT, "this endpoint is for students")


def acting_as(principal: Principal, module: str) -> Actor:
    """The actor of a command that ``module`` runs on behalf of the caller (NFR-25)."""
    return Actor(principal.user_id, principal.role, module)
