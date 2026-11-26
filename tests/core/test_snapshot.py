"""Snapshot (NFR-12, NFR-13), the commit counter, snapshot_version and change tracking."""

import hashlib
import json
from datetime import timedelta

from core.domain.entities import ResourceClaim, Vehicle
from core.domain.enums import (
    ClaimStatus,
    HolderKind,
    HubStatus,
    ResourceType,
    SpaceStatus,
    VehicleEvent,
    VehicleState,
)
from core.errors import ErrorCode
from core.repository.memory import InMemoryRepository
from core.result import Err, Ok
from core.services.commands import TransitionCtx


def state_hash(repo):
    """A hash of everything stored; used as the write guard of the NFR-12 test."""
    parts = []
    for table_type, table in sorted(repo.export_state().items(), key=lambda item: item[0].__name__):
        for key in sorted(table):
            parts.append(f"{table_type.__name__}:{key}:{table[key]!r}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def reserve_v001(world, park=True):
    if park:
        world.park("V001", "S02")
    claim_id = world.claim_vehicle("V001")
    result = world.core.commands.transition_vehicle(
        "V001", VehicleEvent.RESERVE, 1, world.reservation, TransitionCtx(claim_id=claim_id)
    )
    assert isinstance(result, Ok)
    return claim_id


# ------------------------------------------------------------------------------ the snapshot


def test_snapshot_holds_sorted_copies_of_everything_but_only_active_claims(world):
    world.park("V002", "S03")
    world.park("V001", "S02")
    kept = world.claim_vehicle("V001", ref="R1")
    dropped = world.claim_vehicle("V002", ref="R2")
    world.core.commands.release_claim(dropped, world.reservation)

    snapshot = world.core.snapshots.export_snapshot()

    assert [h.hub_id for h in snapshot.hubs] == ["H01", "H02"]
    assert [s.parking_space_id for s in snapshot.parking_spaces] == [
        "S01",
        "S02",
        "S03",
        "S11",
        "S12",
    ]
    assert [p.charging_point_id for p in snapshot.charging_points] == ["CP01"]
    assert [v.vehicle_id for v in snapshot.vehicles] == ["V001", "V002"]
    assert [c.claim_id for c in snapshot.claims] == [kept]
    assert snapshot.taken_at == world.clock.now()


def test_changing_the_snapshot_never_changes_the_store(world):
    world.park("V001", "S02")
    before = state_hash(world.repo)
    snapshot = world.core.snapshots.export_snapshot()

    snapshot.vehicles[0].state = VehicleState.MAINTENANCE
    snapshot.parking_spaces[1].status = SpaceStatus.MAINTENANCE

    assert state_hash(world.repo) == before
    assert world.vehicle("V001").state is VehicleState.AVAILABLE


def test_the_same_state_gives_the_same_id_whatever_the_history(world):
    world.park("V001", "S02")
    first = world.core.snapshots.export_snapshot()
    world.clock.advance(timedelta(hours=1))
    world.core.commands.place_claim(
        ResourceType.VEHICLE,
        "V001",
        HolderKind.RESERVATION,
        "R1",
        world.clock.now(),
        world.clock.now() + timedelta(minutes=10),
        world.reservation,
    )
    claim = world.repo.query(ResourceClaim)[0]
    world.core.commands.release_claim(claim.claim_id, world.reservation)  # state is as before
    second = world.core.snapshots.export_snapshot()

    assert second.version > first.version
    assert second.taken_at != first.taken_at
    assert second.snapshot_id == first.snapshot_id  # the active content is the same


def test_a_different_state_gives_a_different_id(world):
    world.park("V001", "S02")
    first = world.core.snapshots.export_snapshot()
    reserve_v001(world, park=False)

    assert world.core.snapshots.export_snapshot().snapshot_id != first.snapshot_id


def test_the_snapshot_can_be_written_as_json_and_is_repeatable(world):
    reserve_v001(world)

    first = json.dumps(world.core.snapshots.export_snapshot().to_dict(), sort_keys=True)
    second = json.dumps(world.core.snapshots.export_snapshot().to_dict(), sort_keys=True)

    assert first == second
    data = json.loads(first)
    assert data["vehicles"][0]["state"] == "RESERVED"
    assert data["claims"][0]["status"] == "ACTIVE"
    assert data["snapshot_id"].startswith("SNAP-")


# ------------------------------------------------------------------------------- the version


def test_the_version_grows_with_commits_not_with_reads_failures_or_rollbacks(world):
    start = world.core.snapshots.export_snapshot().version
    world.park("V001", "S02")  # two direct writes: the vehicle and the space
    after_setup = world.core.snapshots.export_snapshot().version
    assert after_setup > start

    world.core.queries.list_hubs()
    world.core.queries.find_vehicles()
    failed = world.core.commands.transition_vehicle(
        "V404", VehicleEvent.RESERVE, 1, world.reservation
    )
    assert isinstance(failed, Err)
    with world.core.unit_of_work() as uow:
        uow.commands.place_claim(
            ResourceType.VEHICLE,
            "V001",
            HolderKind.RESERVATION,
            "R1",
            world.clock.now(),
            world.clock.now() + timedelta(minutes=10),
            world.reservation,
        )
        uow.rollback()
    assert world.core.snapshots.export_snapshot().version == after_setup

    world.claim_vehicle("V001")
    assert world.core.snapshots.export_snapshot().version == after_setup + 1


def test_a_unit_of_work_is_one_commit(world):
    world.park("V001", "S02")
    before = world.core.snapshots.export_snapshot().version

    with world.core.unit_of_work() as uow:
        claim = uow.commands.place_claim(
            ResourceType.VEHICLE,
            "V001",
            HolderKind.RESERVATION,
            "R1",
            world.clock.now(),
            world.clock.now() + timedelta(minutes=10),
            world.reservation,
        )
        assert isinstance(claim, Ok)
        uow.commands.transition_vehicle(
            "V001",
            VehicleEvent.RESERVE,
            1,
            world.reservation,
            TransitionCtx(claim_id=claim.value.claim_id),
        )
        uow.commit()

    assert world.core.snapshots.export_snapshot().version == before + 1


# ------------------------------------------------------------------------ snapshot_version


def test_snapshot_version_commits_when_nothing_the_unit_wrote_has_changed(world):
    world.park("V001", "S02")
    world.park("V002", "S03")
    version = world.core.snapshots.export_snapshot().version
    world.core.commands.set_hub_status("H02", HubStatus.WARNING, 1, world.monitoring)  # unrelated

    with world.core.unit_of_work(snapshot_version=version) as uow:
        claim = uow.commands.place_claim(
            ResourceType.VEHICLE,
            "V001",
            HolderKind.DISPATCH_TASK,
            "T1",
            world.clock.now(),
            world.clock.now() + timedelta(minutes=10),
            world.allocation,
        )
        assert isinstance(claim, Ok)
        assert isinstance(uow.commit(), Ok)


def test_snapshot_version_refuses_when_a_written_entity_changed_since(world):
    world.park("V001", "S02")
    version = world.core.snapshots.export_snapshot().version
    # someone else changes V001 after the plan was made
    world.core.commands.transition_vehicle("V001", VehicleEvent.REPORT_FAULT, 1, world.iot)

    with world.core.unit_of_work(snapshot_version=version) as uow:
        fresh = world.vehicle("V001")
        moved = uow.commands.transition_vehicle(
            "V001", VehicleEvent.REPAIR, fresh.version, world.operator
        )
        assert isinstance(moved, Ok)
        committed = uow.commit()

    assert isinstance(committed, Err)
    assert committed.code is ErrorCode.VERSION_CONFLICT
    assert ("Vehicle", "V001") in committed.details["changed"]
    assert world.vehicle("V001").state is VehicleState.MAINTENANCE  # the unit was rolled back


def test_the_new_claim_of_someone_else_does_not_block_other_resources(world):
    world.park("V001", "S02")
    world.park("V002", "S03")
    version = world.core.snapshots.export_snapshot().version
    world.claim_vehicle("V002", ref="R-OTHER")  # a change after the snapshot, on another resource

    with world.core.unit_of_work(snapshot_version=version) as uow:
        uow.commands.place_claim(
            ResourceType.VEHICLE,
            "V001",
            HolderKind.RESERVATION,
            "R1",
            world.clock.now(),
            world.clock.now() + timedelta(minutes=10),
            world.reservation,
        )
        assert isinstance(uow.commit(), Ok)


# ------------------------------------------------------------ loading a snapshot (NFR-12)


def test_a_loaded_snapshot_is_an_independent_store_that_follows_the_rules(world):
    reserve_v001(world)
    snapshot = world.core.snapshots.export_snapshot()
    live_hash = state_hash(world.repo)

    sandbox = snapshot.to_repository()

    assert isinstance(sandbox, InMemoryRepository)
    assert [v.vehicle_id for v in sandbox.query(Vehicle)] == ["V001"]
    assert len(sandbox.query(ResourceClaim, lambda c: c.status is ClaimStatus.ACTIVE)) == 1

    # run a whole simulated hour in the sandbox
    from core.clock import FixedClock
    from core.facade import CoreFacade

    sim = CoreFacade(sandbox, FixedClock(world.clock.now()))
    assert sim.check_invariants() == []
    result = sim.commands.transition_vehicle(
        "V001", VehicleEvent.RELEASE_RESERVATION, 2, world.reservation
    )
    assert isinstance(result, Ok)
    assert sim.queries.get_vehicle("V001").value.state is VehicleState.AVAILABLE  # type: ignore[union-attr]
    assert sim.check_invariants() == []

    assert state_hash(world.repo) == live_hash  # not one write reached the operational store
    assert world.vehicle("V001").state is VehicleState.RESERVED


def test_change_tracking_of_the_repository(world):
    repo = world.repo
    world.park("V001", "S02")
    version = repo.version()

    repo.begin()
    vehicle = repo.get(Vehicle, "V001")
    assert vehicle is not None
    repo.update(vehicle, vehicle.version)
    assert repo.touched() == frozenset({("Vehicle", "V001")})
    savepoint = repo.savepoint()
    repo.update(repo.get(Vehicle, "V001"), 2)  # type: ignore[arg-type]
    repo.rollback_to(savepoint)
    assert repo.touched() == frozenset({("Vehicle", "V001")})
    repo.commit()

    assert repo.version() == version + 1
    assert repo.touched() == frozenset()
    assert repo.changed_since(frozenset({("Vehicle", "V001")}), version) == [("Vehicle", "V001")]
    assert repo.changed_since(frozenset({("Vehicle", "V001")}), version + 1) == []
    assert repo.changed_since(frozenset({("Vehicle", "NEVER")}), 0) == []
