"""SQL repository for SQLite (D-002), the persistent store behind ``Repository``.

How it keeps the guarantees of ``Repository`` (see base.py):
- One dedicated connection. All callers go through the core runtime lock, so a single shared
  connection is safe (``check_same_thread=False``).
- A transaction starts with ``BEGIN IMMEDIATE`` when it writes, so a writer never meets a lock
  upgrade failure. Foreign keys are switched on for every connection (SQLite has them off by
  default), the file uses write-ahead logging, and a busy database is waited for, not failed.
- ``update`` of a versioned entity is ``UPDATE ... WHERE id = ? AND version = ?``: no row changed
  means someone else got there first, which is the optimistic lock (D-002).
- ``savepoint`` is an SQL SAVEPOINT, so a failing command inside a unit of work is undone alone.
- The commit counter and the per-entity change log are written in the same transaction as the
  data, so they can never disagree with it.

Reads and writes outside an explicit transaction run in a short transaction of their own.
``query`` filters in Python: fine at the size of the reference dataset (400 spaces, 250 vehicles).
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import fields
from enum import Enum
from pathlib import Path
from typing import cast

from sqlalchemy import Connection, Engine, create_engine, event, insert, select, tuple_, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import CursorResult, NestedTransaction, RootTransaction, Row
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from core.domain.entities import Entity, entity_id
from core.repository.base import (
    DuplicateEntityError,
    EntityNotFoundError,
    IntegrityViolationError,
    UnknownEntityError,
    VersionConflictError,
    is_versioned,
)
from core.repository.schema import SPECS, TableSpec, add_spec, change_log, meta, metadata

DEFAULT_URL = "sqlite://"
_MEMORY_URLS = frozenset({"sqlite://", "sqlite:///:memory:"})
_VERSION_KEY = "version"

type _Key = tuple[str, str]


def make_engine(url: str, busy_timeout_ms: int = 5000) -> Engine:
    """An engine whose connections follow the rules in the module docstring."""
    memory = url in _MEMORY_URLS
    if memory:
        engine = create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    else:
        engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def on_connect(dbapi_connection, _record):  # type: ignore[no-untyped-def]
        dbapi_connection.isolation_level = None  # we send BEGIN ourselves, see on_begin
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
        if not memory:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    @event.listens_for(engine, "begin")
    def on_begin(connection: Connection) -> None:
        write = connection.info.get("write", True)
        connection.exec_driver_sql("BEGIN IMMEDIATE" if write else "BEGIN")

    return engine


class SqlRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._specs: dict[type, TableSpec] = dict(SPECS)  # core types, plus those modules register
        self._conn = engine.connect()
        self._tx: RootTransaction | None = None
        self._touched: set[_Key] = set()

    @classmethod
    def open(cls, url: str = DEFAULT_URL, busy_timeout_ms: int = 5000) -> "SqlRepository":
        """Open (and create, if new) the database at ``url``, e.g. ``sqlite:///data/hub.db``."""
        prefix = "sqlite:///"
        if url.startswith(prefix) and url not in _MEMORY_URLS:
            Path(url[len(prefix) :]).parent.mkdir(parents=True, exist_ok=True)
        repository = cls(make_engine(url, busy_timeout_ms))
        repository.create_schema()
        return repository

    def create_schema(self) -> None:
        """Create the tables that do not exist yet (no migration tool: create and seed)."""
        with self._scope(write=True):
            metadata.create_all(self._conn)
            exists = self._conn.execute(
                select(meta.c.key).where(meta.c.key == _VERSION_KEY)
            ).first()
            if exists is None:
                self._conn.execute(insert(meta).values(key=_VERSION_KEY, value=0))

    def register_entity(self, spec: TableSpec) -> None:
        """Add a module's table (created now if it does not exist) and its entity type."""
        if add_spec(self._specs, spec):
            with self._scope(write=True):
                spec.table.create(self._conn, checkfirst=True)

    def _spec(self, entity_type: type) -> TableSpec:
        try:
            return self._specs[entity_type]
        except KeyError:
            raise UnknownEntityError(f"{entity_type.__name__} is not registered") from None

    def close(self) -> None:
        self.rollback()
        self._conn.close()
        self._engine.dispose()

    # ------------------------------------------------------------------ transactions

    def _begin_tx(self, write: bool) -> None:
        self._conn.info["write"] = write
        self._tx = self._conn.begin()

    def _finish_tx(self, commit: bool) -> None:
        tx = self._tx
        if tx is None:
            return
        try:
            if commit:
                self._flush_changes()
                tx.commit()
            else:
                tx.rollback()
        except BaseException:
            if commit:
                with suppress(Exception):  # the original error is the one worth reporting
                    tx.rollback()
            raise
        finally:
            self._tx = None
            self._touched = set()

    @contextmanager
    def _scope(self, write: bool) -> Iterator[None]:
        """Use the open transaction, or run one short transaction for a single operation."""
        if self._tx is not None:
            yield
            return
        self._begin_tx(write)
        try:
            yield
        except BaseException:
            self._finish_tx(commit=False)
            raise
        self._finish_tx(commit=True)

    def _flush_changes(self) -> None:
        """Count the commit and note which entities it changed, inside the same transaction."""
        if not self._touched:
            return
        current = self._conn.execute(
            select(meta.c.value).where(meta.c.key == _VERSION_KEY)
        ).scalar_one()
        new_version = current + 1
        self._conn.execute(update(meta).where(meta.c.key == _VERSION_KEY).values(value=new_version))
        statement = sqlite_insert(change_log)
        statement = statement.on_conflict_do_update(
            index_elements=["entity_type", "entity_id"],
            set_={"version": statement.excluded.version},
        )
        self._conn.execute(
            statement,
            [
                {"entity_type": kind, "entity_id": key, "version": new_version}
                for kind, key in sorted(self._touched)
            ],
        )

    def begin(self) -> None:
        if self._tx is not None:
            raise RuntimeError("a transaction is already open")
        self._begin_tx(write=True)

    def commit(self) -> None:
        self._finish_tx(commit=True)

    def rollback(self) -> None:
        self._finish_tx(commit=False)

    def savepoint(self) -> object:
        if self._tx is None:
            raise RuntimeError("a savepoint needs an open transaction")
        return (self._conn.begin_nested(), set(self._touched))

    def rollback_to(self, savepoint: object) -> None:
        nested, touched = cast(tuple[NestedTransaction, set[_Key]], savepoint)
        nested.rollback()
        self._touched = set(touched)

    def release(self, savepoint: object) -> None:
        nested, _touched = cast(tuple[NestedTransaction, set[_Key]], savepoint)
        nested.commit()

    # ------------------------------------------------------------------ change tracking

    def version(self) -> int:
        with self._scope(write=False):
            return int(
                self._conn.execute(
                    select(meta.c.value).where(meta.c.key == _VERSION_KEY)
                ).scalar_one()
            )

    def touched(self) -> frozenset[tuple[str, str]]:
        return frozenset(self._touched)

    def changed_since(
        self, keys: frozenset[tuple[str, str]], version: int
    ) -> list[tuple[str, str]]:
        if not keys:
            return []
        with self._scope(write=False):
            rows = self._conn.execute(
                select(change_log.c.entity_type, change_log.c.entity_id).where(
                    tuple_(change_log.c.entity_type, change_log.c.entity_id).in_(sorted(keys)),
                    change_log.c.version > version,
                )
            ).all()
        return sorted((str(row[0]), str(row[1])) for row in rows)

    # ------------------------------------------------------------------ entities

    @staticmethod
    def _values(entity: Entity) -> dict[str, object]:
        values: dict[str, object] = {}
        for field in fields(entity):
            value = getattr(entity, field.name)
            values[field.name] = value.value if isinstance(value, Enum) else value
        return values

    @staticmethod
    def _entity(spec: TableSpec, row: Row[tuple[object, ...]]) -> Entity:
        data = dict(row._mapping)
        for name, enum in spec.enums.items():
            data[name] = enum(data[name])
        return cast(Entity, spec.entity(**data))

    def _exists(self, spec: TableSpec, key: str) -> bool:
        column = spec.table.c[spec.id_column]
        return self._conn.execute(select(column).where(column == key)).first() is not None

    def _write(self, statement: object) -> CursorResult[tuple[object, ...]]:
        try:
            return cast(CursorResult[tuple[object, ...]], self._conn.execute(statement))  # type: ignore[call-overload]
        except IntegrityError as exc:
            raise IntegrityViolationError(str(exc.orig)) from exc

    def get[E: Entity](self, entity_type: type[E], entity_id: str) -> E | None:
        spec = self._spec(entity_type)
        column = spec.table.c[spec.id_column]
        with self._scope(write=False):
            row = self._conn.execute(select(spec.table).where(column == entity_id)).first()
        return None if row is None else cast(E, self._entity(spec, row))

    def query[E: Entity](
        self, entity_type: type[E], predicate: Callable[[E], bool] | None = None
    ) -> list[E]:
        spec = self._spec(entity_type)
        with self._scope(write=False):
            rows = self._conn.execute(
                select(spec.table).order_by(spec.table.c[spec.id_column])
            ).all()
        entities = [cast(E, self._entity(spec, row)) for row in rows]
        return entities if predicate is None else [e for e in entities if predicate(e)]

    def add(self, entity: Entity) -> None:
        spec = self._spec(type(entity))
        key = entity_id(entity)
        with self._scope(write=True):
            if self._exists(spec, key):
                raise DuplicateEntityError(f"{type(entity).__name__} {key!r} already exists")
            self._write(insert(spec.table).values(**self._values(entity)))
            self._touched.add((type(entity).__name__, key))

    def update(self, entity: Entity, expected_version: int | None = None) -> None:
        spec = self._spec(type(entity))
        key = entity_id(entity)
        versioned = is_versioned(entity)
        if versioned and expected_version is None:
            raise ValueError("expected_version is required to update a versioned entity")
        if not versioned and expected_version is not None:
            raise ValueError("expected_version is only used for versioned entities")
        with self._scope(write=True):
            values = self._values(entity)
            id_column = spec.table.c[spec.id_column]
            statement = update(spec.table).where(id_column == key)
            if versioned and expected_version is not None:
                values["version"] = expected_version + 1
                statement = statement.where(spec.table.c.version == expected_version)
            result = self._write(statement.values(**values))
            if result.rowcount == 0:
                if not self._exists(spec, key):
                    raise EntityNotFoundError(f"{type(entity).__name__} {key!r} does not exist")
                stored = self._conn.execute(
                    select(spec.table.c.version).where(id_column == key)
                ).scalar_one()
                raise VersionConflictError(
                    f"{type(entity).__name__} {key!r}: stored version {stored}, "
                    f"expected {expected_version}"
                )
            if versioned and expected_version is not None:
                entity.version = expected_version + 1  # type: ignore[union-attr]
            self._touched.add((type(entity).__name__, key))

    def export_state(self) -> dict[type, dict[str, Entity]]:
        """Everything stored, by entity type and ID (used by tests to compare two states)."""
        return {
            spec.entity: {entity_id(e): e for e in self.query(cast(type[Entity], spec.entity))}
            for spec in self._specs.values()
        }
