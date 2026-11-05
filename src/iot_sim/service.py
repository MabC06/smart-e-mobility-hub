"""Application-facing operations for the IoT simulator."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from core.actor import Actor
from core.domain.enums import Role
from core.facade import CoreFacade
from core.result import Result
from core.seed import NetworkSpec, NetworkSummary
from core.sensors import SensorEvent, SensorResult
from iot_sim.config import SimulatorConfig
from iot_sim.dataset import build_network_spec
from iot_sim.events import iter_minimal_events

SIMULATOR_ACTOR = Actor(user_id="iot-simulator", role=Role.OPERATOR, module="iot_sim")


def seed_core(core: CoreFacade, seed: int = 0) -> Result[NetworkSummary]:
    """Load DS-STD through Core's command interface; never writes to storage directly."""
    return core.commands.load_network(build_network_spec(seed), SIMULATOR_ACTOR)


def apply_events(core: CoreFacade, events: Iterable[SensorEvent]) -> list[Result[SensorResult]]:
    """Apply events sequentially through Core and preserve each result for reporting."""
    return [core.commands.apply_sensor_event(event, SIMULATOR_ACTOR) for event in events]


def run_minimal_feed(
    core: CoreFacade,
    seed: int = 0,
    start_at: datetime | None = None,
    config: SimulatorConfig | None = None,
) -> list[Result[SensorResult]]:
    """Emit the minimal deterministic feed against a network seeded with the same seed."""
    selected = config or SimulatorConfig(seed=seed)
    moment = start_at or datetime.now(UTC)
    spec: NetworkSpec = build_network_spec(selected.seed)
    return apply_events(core, iter_minimal_events(spec, moment, selected))
