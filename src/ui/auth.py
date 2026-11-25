"""Sign-in for the pages: the token that ``core`` gives at login is kept in a cookie.

``main.build_app`` puts ``core`` and the sign-in checker on ``app.state``; the pages read them here.
"""

from typing import Any

from fastapi import Request

from core.api.security import Principal
from core.facade import CoreFacade
from core.result import Err

TOKEN_COOKIE = "ui_token"


def get_core(request: Request) -> CoreFacade:
    """The shared state (Hubs, vehicles...)."""
    core = getattr(request.app.state, "core", None)
    if not isinstance(core, CoreFacade):
        raise RuntimeError("app.state.core is missing: build the application with main.build_app")
    return core


def get_auth(request: Request) -> Any:
    """The sign-in checker. Typed ``Any``: ``core.auth`` is not open to modules for import."""
    auth = getattr(request.app.state, "auth", None)
    if auth is None:
        raise RuntimeError("app.state.auth is missing: build the application with main.build_app")
    return auth


def current_user(request: Request) -> Principal | None:
    """The user behind the cookie, or None if there is no valid token."""
    token = request.cookies.get(TOKEN_COOKIE)
    if not token:
        return None
    result = get_auth(request).authenticate(token)
    return None if isinstance(result, Err) else result.value  # type: ignore[no-any-return]
