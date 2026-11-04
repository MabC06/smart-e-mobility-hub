"""CoreFacade: the one object other modules use (docs/design/structural/class-diagram-core.md)."""

from collections.abc import Callable
from typing import cast

from core.auth import AuthConfig, AuthService
from core.clock import Clock, SystemClock
from core.config import CoreConfig
from core.domain.entities import CORE_TYPES, Entity, entity_id
from core.domain.invariants import InvariantChecker, Violation
from core.events import EventBus
from core.ids import IdGenerator, SequentialIdGenerator
from core.providers import ProviderPort, ProviderRegistry
from core.repository.base import Repository
from core.repository.memory import InMemoryRepository
from core.repository.schema import TableSpec
from core.services.commands import StateCommands
from core.services.queries import HubQueries
from core.services.runtime import Runtime
from core.services.snapshot import SnapshotService
from core.services.unit_of_work import UnitOfWork


class CoreFacade:
    def __init__(
        self,
        repository: Repository | None = None,
        clock: Clock | None = None,
        config: CoreConfig | None = None,
        ids: IdGenerator | None = None,
        bus: EventBus | None = None,
    ) -> None:
        repo = repository if repository is not None else InMemoryRepository()
        # Restarted stores already contain claim, vehicle, audit and event IDs.
        # Preserve deterministic sequences without reusing committed identifiers.
        default_ids = (
            SequentialIdGenerator(
                entity_id(row)
                for entity_type in CORE_TYPES
                for row in repo.query(cast(type[Entity], entity_type))
            )
            if ids is None
            else ids
        )
        self._runtime = Runtime(
            repo,
            clock if clock is not None else SystemClock(),
            default_ids,
            config if config is not None else CoreConfig(),
            bus if bus is not None else EventBus(),
        )
        self.queries = HubQueries(self._runtime)
        self.commands = StateCommands(self._runtime)
        self.snapshots = SnapshotService(self._runtime)
        self.events = self._runtime.bus
        self._clock = self._runtime.clock
        self.providers = ProviderRegistry()

    def register_provider(self, port: ProviderPort, provider: object) -> None:
        """A module registers what it implements for a port, at start-up (core-api-spec.md, 6.1)."""
        self.providers.register(port, provider)

    def register_entity(self, spec: TableSpec) -> None:
        """A module adds its own table at start-up, so its records join core's transactions.

        Build the ``Table`` on ``core.repository.schema.metadata`` (so foreign keys to core's tables
        resolve) and give the entity class ``ID_FIELD`` and, if it has a ``version``, ``VERSIONED``.
        Write the records through ``unit_of_work().repository``; read them with ``get_entity`` and
        ``query_entities``. Raises ValueError when the spec does not fit (core-api-spec.md, 5.2).
        """
        with self._runtime.lock:
            self._runtime.repo.register_entity(spec)

    def get_entity[E: Entity](self, entity_type: type[E], entity_id: str) -> E | None:
        """Read one record of a registered type (core's lock is held while reading)."""
        with self._runtime.lock:
            return self._runtime.repo.get(entity_type, entity_id)

    def query_entities[E: Entity](
        self, entity_type: type[E], predicate: Callable[[E], bool] | None = None
    ) -> list[E]:
        """Read the records of a registered type, sorted by ID."""
        with self._runtime.lock:
            return self._runtime.repo.query(entity_type, predicate)

    def authentication(self, config: AuthConfig) -> AuthService:
        """The login and token service (needs a secret key, so it is not built by default)."""
        return AuthService(self._runtime, config, self._clock)

    def unit_of_work(self, snapshot_version: int | None = None) -> UnitOfWork:
        return UnitOfWork(self._runtime, self.commands, self.queries, snapshot_version)

    def check_invariants(self) -> list[Violation]:
        """Everything that is wrong with the stored state; empty when all rules hold."""
        with self._runtime.lock:
            return InvariantChecker.check(self._runtime.repo)
