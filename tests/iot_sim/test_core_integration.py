"""Core-boundary tests — TC-M8-012 to TC-M8-015."""

from datetime import UTC, datetime

from core.domain.entities import Hub, ParkingSpace, Vehicle
from core.facade import CoreFacade
from core.repository.memory import InMemoryRepository
from core.result import Err
from iot_sim import SimulatorConfig, run_minimal_feed, seed_core


def test_seed_core_loads_ds_std_through_core_command() -> None:
    repo = InMemoryRepository()
    core = CoreFacade(repository=repo)
    result = seed_core(core, seed=21)
    assert not isinstance(result, Err)
    assert len(repo.query(Hub)) == 10
    assert len(repo.query(ParkingSpace)) == 400
    assert len(repo.query(Vehicle)) == 350


def test_minimal_feed_changes_battery_and_restores_private_occupancy() -> None:
    repo = InMemoryRepository()
    core = CoreFacade(repository=repo)
    seeded = seed_core(core, seed=21)
    assert not isinstance(seeded, Err)

    before = {v.vehicle_id: v.battery_pct for v in repo.query(Vehicle)}
    results = run_minimal_feed(
        core,
        seed=21,
        start_at=datetime(2026, 11, 6, tzinfo=UTC),
        config=SimulatorConfig(seed=21, private_arrival_count=3),
    )
    assert results
    assert all(not isinstance(result, Err) for result in results)
    after = {v.vehicle_id: v.battery_pct for v in repo.query(Vehicle)}
    assert any(after[key] < value for key, value in before.items() if key.startswith("F-"))
    assert len(repo.query(ParkingSpace, lambda s: s.occupant_vehicle_id is not None)) == 250
    assert core.check_invariants() == []


def test_seed_refuses_to_overwrite_existing_network() -> None:
    core = CoreFacade()
    assert not isinstance(seed_core(core, seed=3), Err)
    second = seed_core(core, seed=3)
    assert isinstance(second, Err)
