"""In-memory repository.

Used by unit tests of core and of the other modules, and as a store for a What-if run loaded from
a snapshot, so a simulation never holds a connection to the operational store (NFR-12).
"""

import copy
from collections.abc import Callable
from typing import cast

from core.domain.entities import Entity, entity_id
from core.repository.base import (
    DuplicateEntityError,
    EntityNotFoundError,
    UnknownEntityError,
    VersionConflictError,
    is_versioned,
)
from core.repository.schema import SPECS, TableSpec, add_spec

type _Tables = dict[type, dict[str, Entity]]
type _Key = tuple[str, str]


class InMemoryRepository:
    def __init__(self) -> None:
        self._specs: dict[type, TableSpec] = dict(SPECS)  # core types, plus those modules register
        self._tables: _Tables = {}
        self._backup: _Tables | None = None
        self._version = 0
        self._last_changed: dict[_Key, int] = {}
        self._touched: set[_Key] = set()

    def _touch(self, entity: Entity) -> None:
        self._touched.add((type(entity).__name__, entity_id(entity)))
        if self._backup is None:  # no transaction open: the write commits on its own
            self._commit_touched()

    def _commit_touched(self) -> None:
        if self._touched:
            self._version += 1
            for key in self._touched:
                self._last_changed[key] = self._version
            self._touched = set()

    def register_entity(self, spec: TableSpec) -> None:
        add_spec(self._specs, spec)

    def _known(self, entity_type: type) -> None:
        if entity_type not in self._specs:
            raise UnknownEntityError(f"{entity_type.__name__} is not registered")

    def _table(self, entity_type: type) -> dict[str, Entity]:
        """The table to write to; created on first use."""
        self._known(entity_type)
        return self._tables.setdefault(entity_type, {})

    def _read_table(self, entity_type: type) -> dict[str, Entity]:
        """The table to read from; a read never creates one, so reading changes no state."""
        self._known(entity_type)
        return self._tables.get(entity_type, {})

    def get[E: Entity](self, entity_type: type[E], entity_id: str) -> E | None:
        found = self._read_table(entity_type).get(entity_id)
        return None if found is None else cast(E, copy.deepcopy(found))

    def query[E: Entity](
        self, entity_type: type[E], predicate: Callable[[E], bool] | None = None
    ) -> list[E]:
        table = self._read_table(entity_type)
        result: list[E] = []
        for key in sorted(table):
            item = cast(E, copy.deepcopy(table[key]))
            if predicate is None or predicate(item):
                result.append(item)
        return result

    def add(self, entity: Entity) -> None:
        table = self._table(type(entity))
        key = entity_id(entity)
        if key in table:
            raise DuplicateEntityError(f"{type(entity).__name__} {key!r} already exists")
        table[key] = copy.deepcopy(entity)
        self._touch(entity)

    def update(self, entity: Entity, expected_version: int | None = None) -> None:
        table = self._table(type(entity))
        key = entity_id(entity)
        stored = table.get(key)
        if stored is None:
            raise EntityNotFoundError(f"{type(entity).__name__} {key!r} does not exist")
        if is_versioned(entity):
            if expected_version is None:
                raise ValueError("expected_version is required to update a versioned entity")
            stored_version = cast(int, stored.version)  # type: ignore[union-attr]
            if stored_version != expected_version:
                raise VersionConflictError(
                    f"{type(entity).__name__} {key!r}: stored version {stored_version}, "
                    f"expected {expected_version}"
                )
            entity.version = expected_version + 1  # type: ignore[union-attr]
        elif expected_version is not None:
            raise ValueError("expected_version is only used for versioned entities")
        table[key] = copy.deepcopy(entity)
        self._touch(entity)

    def begin(self) -> None:
        if self._backup is not None:
            raise RuntimeError("a transaction is already open")
        self._backup = copy.deepcopy(self._tables)

    def commit(self) -> None:
        self._backup = None
        self._commit_touched()

    def rollback(self) -> None:
        if self._backup is not None:
            self._tables = self._backup
            self._backup = None
        self._touched = set()

    def savepoint(self) -> object:
        return (copy.deepcopy(self._tables), set(self._touched))

    def rollback_to(self, savepoint: object) -> None:
        tables, touched = cast(tuple[_Tables, set[_Key]], savepoint)
        self._tables = copy.deepcopy(tables)
        self._touched = set(touched)

    def version(self) -> int:
        return self._version

    def touched(self) -> frozenset[tuple[str, str]]:
        return frozenset(self._touched)

    def changed_since(
        self, keys: frozenset[tuple[str, str]], version: int
    ) -> list[tuple[str, str]]:
        return [key for key in sorted(keys) if self._last_changed.get(key, 0) > version]

    def release(self, savepoint: object) -> None:
        return None

    def export_state(self) -> _Tables:
        """A deep copy of everything stored; used by the unit of work to roll back."""
        return copy.deepcopy(self._tables)

    def import_state(self, state: _Tables) -> None:
        self._tables = copy.deepcopy(state)
