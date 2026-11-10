"""Result type: commands return a value or an error, they never raise for business failures."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from core.errors import ErrorCode


@dataclass(frozen=True, slots=True)
class Ok[T]:
    value: T

    @property
    def is_ok(self) -> bool:
        return True

    @property
    def is_err(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class Err:
    code: ErrorCode
    message: str = ""
    details: Mapping[str, object] = field(default_factory=dict)

    @property
    def is_ok(self) -> bool:
        return False

    @property
    def is_err(self) -> bool:
        return True


type Result[T] = Ok[T] | Err
