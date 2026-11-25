"""Calls from a page to the REST routes of M3, M4 and M5 with the user's own token.

``ui`` may not import those modules (NFR-22). The call stays inside the application (no network).
Use call() and read_form() only from a normal ``def`` route.
"""

from typing import Any
from urllib.parse import parse_qs

import anyio.from_thread
import httpx
from fastapi import FastAPI, Request

from ui.auth import TOKEN_COOKIE


async def _send(app: FastAPI, token: str | None, method: str, path: str, **options: Any) -> Any:
    # A route that crashes gives a 500 answer, not an exception in the page (NFR-21).
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(transport=transport, base_url="http://ui", headers=headers) as c:
        response = await c.request(method, path, **options)
    return response.status_code, (response.json() if response.content else None)


def call(request: Request, method: str, path: str, **options: Any) -> tuple[int, Any]:
    """Call a route as the signed-in user: ``(HTTP status, JSON answer)``."""
    token = request.cookies.get(TOKEN_COOKIE)
    return anyio.from_thread.run(lambda: _send(request.app, token, method, path, **options))  # type: ignore[no-any-return]


def read_form(request: Request) -> dict[str, str]:
    """The fields of a submitted HTML form (FastAPI's ``Form`` needs one more package)."""
    body = anyio.from_thread.run(request.body)
    return {name: values[0] for name, values in parse_qs(body.decode("utf-8", "replace")).items()}


def explain(status: int, data: Any) -> tuple[str, str]:
    """``(code, cause)`` of a refused call, for the error block S9 (NFR-21)."""
    body = data if isinstance(data, dict) else {}
    detail = body.get("detail")
    if isinstance(detail, list):  # the values did not pass the route's checks (422)
        return "INVALID_INPUT", "Check the values you entered and try again."
    if isinstance(detail, str):
        return str(status), detail
    found = body.get("error") or detail  # core: {"error": {...}}; M3, M4: {"detail": {...}}
    if isinstance(found, dict):
        return str(found.get("code", status)), str(found.get("message", "The request failed."))
    return str(status), "The request was refused."
