"""Repository interface (docs/design/structural/class-diagram-core.md, section 3).

Rules every implementation follows:
- ``get`` and ``query`` return copies; changing a returned object never changes the store.
- ``add`` inserts a new entity; it fails if the ID already exists.
- ``update`` replaces an existing entity. For versioned entities (Hub, ParkingSpace,
  ChargingPoint, Vehicle) the caller passes the version it read; if the stored version differs,
  the update fails and nothing changes (optimistic locking, D-002). On success the stored
  version is ``expected_version + 1`` and the same value is written back to the passed entity.
- ``query`` returns entities sorted by ID, so results are repeatable (NFR-13).
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from core.domain.entities import VERSIONED_TYPES, Entity

if TYPE_CHECKING:
    from core.repository.schema import TableSpec


class RepositoryError(Exception):
    """Base class of errors raised by repositories. The command layer maps them to error codes."""


class DuplicateEntityError(RepositoryError):
    """``add`` was called with an ID that already exists."""


class EntityNotFoundError(RepositoryError):
    """``update`` was called for an entity that does not exist."""


class VersionConflictError(RepositoryError):
    """The stored version differs from the version the caller read."""


class UnknownEntityError(RepositoryError):
    """The entity type is neither a core type nor registered by a module (``register_entity``)."""


class IntegrityViolationError(RepositoryError):
    """The store refused a change that breaks one of its own constraints (a SQL database does)."""


class Repository(Protocol):
    def get[E: Entity](self, entity_type: type[E], entity_id: str) -> E | None: ...

    def query[E: Entity](
        self, entity_type: type[E], predicate: Callable[[E], bool] | None = None
    ) -> list[E]: ...

    def add(self, entity: Entity) -> None: ...

    def update(self, entity: Entity, expected_version: int | None = None) -> None: ...

    def register_entity(self, spec: "TableSpec") -> None:
        """Add a module's entity type, so it is stored in the same transaction as core's data.

        Registering the same spec again changes nothing; a clashing name or table is refused with
        ValueError. See ``core.repository.schema.check_spec`` for what a spec must satisfy.
        """
        ...

    def begin(self) -> None:
        """Open the outermost transaction. Only one can be open at a time."""
        ...

    def commit(self) -> None: ...

    def rollback(self) -> None:
        """Undo everything since ``begin``."""
        ...

    def savepoint(self) -> object:
        """Mark a point inside the open transaction (or outside one, for a single command)."""
        ...

    def rollback_to(self, savepoint: object) -> None: ...

    def release(self, savepoint: object) -> None: ...

    def version(self) -> int:
        """A counter that grows with every commit that changed something (never on a rollback)."""
        ...

    def touched(self) -> frozenset[tuple[str, str]]:
        """(entity type name, ID) of everything written in the open transaction."""
        ...

    def changed_since(
        self, keys: frozenset[tuple[str, str]], version: int
    ) -> list[tuple[str, str]]:
        """The keys among ``keys`` that were committed with a version greater than ``version``."""
        ...


def is_versioned(entity: Entity) -> bool:
    """Core's versioned types, and module entities that declare ``VERSIONED = True``."""
    return isinstance(entity, VERSIONED_TYPES) or getattr(type(entity), "VERSIONED", False) is True
