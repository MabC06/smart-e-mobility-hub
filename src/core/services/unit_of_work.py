"""Unit of work: several commands that succeed or fail together (NFR-09).

    with core.unit_of_work() as uow:
        uow.commands.place_claim(...)
        uow.commands.transition_vehicle(...)
        uow.commit()

Leaving the block without ``commit()`` rolls everything back, so does an exception. Events are
published only after ``commit()``. A unit of work belongs to one thread and does not nest.

A plan made on a snapshot (M4) opens the unit with ``snapshot_version``: ``commit()`` then fails
with VERSION_CONFLICT if anything the unit wrote was committed by someone else after that version.
"""

from types import TracebackType

from core.errors import ErrorCode
from core.repository.base import Repository
from core.result import Err, Ok, Result
from core.services.commands import StateCommands
from core.services.queries import HubQueries
from core.services.runtime import Runtime


class UnitOfWork:
    def __init__(
        self,
        runtime: Runtime,
        commands: StateCommands,
        queries: HubQueries,
        snapshot_version: int | None = None,
    ) -> None:
        self._rt = runtime
        self.commands = commands
        self.queries = queries
        self._snapshot_version = snapshot_version
        self._open = False

    @property
    def repository(self) -> Repository:
        """The repository of this unit. A module writes its own records here (``add``, ``update``),
        so they commit or roll back together with core's changes. Use it only inside the ``with``
        block and on the same thread."""
        if not self._open:
            raise RuntimeError("the unit of work is not open")
        return self._rt.repo

    def __enter__(self) -> "UnitOfWork":
        self._rt.lock.acquire()
        if self._rt.in_unit_of_work:
            self._rt.lock.release()
            raise RuntimeError("a unit of work does not nest")
        self._rt.in_unit_of_work = True
        self._rt.pending = []
        self._rt.repo.begin()
        self._open = True
        return self

    def commit(self) -> Result[None]:
        if not self._open:
            return Err(ErrorCode.INTERNAL_ERROR, "the unit of work is already finished")
        if self._snapshot_version is not None:
            repo = self._rt.repo
            changed = repo.changed_since(repo.touched(), self._snapshot_version)
            if changed:
                self.rollback()
                return Err(
                    ErrorCode.VERSION_CONFLICT,
                    "an entity written by this unit of work changed after the snapshot",
                    {"snapshot_version": self._snapshot_version, "changed": changed},
                )
        try:
            self._rt.repo.commit()
        except Exception as exc:
            self.rollback()
            return Err(ErrorCode.INTERNAL_ERROR, f"commit failed: {exc}")
        self._finish()
        self._rt.publish_pending()
        return Ok(None)

    def rollback(self) -> None:
        if not self._open:
            return
        self._rt.repo.rollback()
        self._rt.pending = []
        self._finish()

    def _finish(self) -> None:
        self._open = False
        self._rt.in_unit_of_work = False

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if self._open:
                self.rollback()
        finally:
            self._rt.lock.release()
