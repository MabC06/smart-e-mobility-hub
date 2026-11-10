"""Who runs a command: the user, the user's role and the calling module (NFR-16, NFR-25)."""

from dataclasses import dataclass

from core.domain.enums import Role


@dataclass(frozen=True, slots=True)
class Actor:
    user_id: str
    role: Role
    module: str

    def label(self) -> str:
        return f"{self.module}/{self.user_id}"
