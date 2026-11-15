"""The error that stops a REST request (core-api-spec.md, section 8).

``core`` turns it into the one error body of the interface. It lives in its own file so that the
sign-in checks of ``security.py`` and the endpoints of ``app.py`` can both raise it.
"""

from core.errors import ErrorCode
from core.result import Err


class ApiError(Exception):
    def __init__(self, error: Err) -> None:
        super().__init__(error.message)
        self.error = error


def fail(code: ErrorCode, message: str) -> ApiError:
    return ApiError(Err(code, message))
