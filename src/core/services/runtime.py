"""Shared runtime of the services: repository, clock, IDs, configuration, event bus and the
transaction handling that makes every command atomic (NFR-09).

- A command that runs on its own is one transaction: it commits when it succeeds and rolls back
  when it returns an error.
- A command that runs inside a unit of work is wrapped in a savepoint: when it returns an error,
  its own changes are undone and the rest of the unit is untouched, so the caller can choose to
  continue or to roll back the whole unit.
- Events are collected during the transaction and published only after the commit.
- One re-entrant lock serializes all writers of one process (one deployment, A-08).
"""

import logging
import threading
from collections.abc import Callable
from datetime import datetime

from core.clock import Clock
from core.config import CoreConfig
from core.domain.entities import DomainEvent, ParkingSpace, StateChangeRecord
from core.domain.enums import SpaceStatus
from core.domain.state_machine import VehicleStateMachine
from core.errors import ErrorCode
from core.events import EventBus, EventType
from core.ids import IdGenerator
from core.repository.base import (
    DuplicateEntityError,
    EntityNotFoundError,
    IntegrityViolationError,
    Repository,
    VersionConflictError,
)
from core.result import Err, Result

logger = logging.getLogger("core")


class Runtime:
    def __init__(
        self,
        repository: Repository,
        clock: Clock,
        ids: IdGenerator,
        config: CoreConfig,
        bus: EventBus,
    ) -> None:
        self.repo = repository
        self.clock = clock
        self.ids = ids
        self.config = config
        self.bus = bus
        self.machine = VehicleStateMachine(config)
        self.lock = threading.RLock()
        self.in_unit_of_work = False
        self.pending: list[DomainEvent] = []

    def now(self) -> datetime:
        return self.clock.now()

    def emit(self, event_type: EventType, payload: dict[str, object]) -> None:
        self.pending.append(
            DomainEvent(self.ids.next_id("EVT"), event_type.value, self.now(), payload)
        )

    def log_change(
        self,
        entity_type: str,
        entity_id: str,
        previous_state: str,
        new_state: str,
        trigger: str,
        actor_label: str,
    ) -> None:
        self.repo.add(
            StateChangeRecord(
                record_id=self.ids.next_id("LOG"),
                at=self.now(),
                entity_type=entity_type,
                entity_id=entity_id,
                previous_state=previous_state,
                new_state=new_state,
                trigger=trigger,
                actor=actor_label,
            )
        )

    def occupied_count(self, hub_id: str) -> int:
        spaces = self.repo.query(
            ParkingSpace, lambda s: s.hub_id == hub_id and s.status is SpaceStatus.OCCUPIED
        )
        return len(spaces)

    def publish_pending(self) -> None:
        events, self.pending = self.pending, []
        for event in events:
            self.bus.publish(event)

    def run[T](self, work: Callable[[], Result[T]]) -> Result[T]:
        """Run one command atomically (see the module docstring)."""
        with self.lock:
            if self.in_unit_of_work:
                return self._run_in_savepoint(work)
            return self._run_alone(work)

    def _run_alone[T](self, work: Callable[[], Result[T]]) -> Result[T]:
        self.repo.begin()
        self.pending = []
        result = self._guarded(work)
        if isinstance(result, Err):
            self.repo.rollback()
            self.pending = []
            return result
        self.repo.commit()
        self.publish_pending()
        return result

    def _run_in_savepoint[T](self, work: Callable[[], Result[T]]) -> Result[T]:
        savepoint = self.repo.savepoint()
        mark = len(self.pending)
        result = self._guarded(work)
        if isinstance(result, Err):
            self.repo.rollback_to(savepoint)
            del self.pending[mark:]
            return result
        self.repo.release(savepoint)
        return result

    @staticmethod
    def _guarded[T](work: Callable[[], Result[T]]) -> Result[T]:
        try:
            return work()
        except VersionConflictError as exc:
            return Err(ErrorCode.VERSION_CONFLICT, str(exc))
        except EntityNotFoundError as exc:
            return Err(ErrorCode.NOT_FOUND, str(exc))
        except (DuplicateEntityError, IntegrityViolationError) as exc:
            return Err(ErrorCode.INVALID_INPUT, str(exc))
        except Exception:
            logger.exception("unexpected failure in a core command; changes are rolled back")
            return Err(ErrorCode.INTERNAL_ERROR, "unexpected failure; changes were rolled back")
