"""Unit of work: all-or-nothing, events after commit, savepoints (NFR-09)."""

from datetime import timedelta

import pytest

from core.domain.entities import ResourceClaim, StateChangeRecord, Vehicle
from core.domain.enums import HolderKind, ResourceType, SpaceStatus, VehicleEvent, VehicleState
from core.errors import ErrorCode
from core.events import EventType
from core.repository.base import VersionConflictError
from core.result import Err, Ok
from core.services.commands import TransitionCtx


def place_args(world, resource="V001", ref="R1"):
    base = world.clock.now()
    return (
        ResourceType.VEHICLE,
        resource,
        HolderKind.RESERVATION,
        ref,
        base,
        base + timedelta(minutes=10),
        world.reservation,
    )


def test_commit_applies_everything_and_publishes_after_the_commit(world):
    world.park("V001", "S02")
    seen_during_block = []

    with world.core.unit_of_work() as uow:
        claim = uow.commands.place_claim(*place_args(world))
        assert isinstance(claim, Ok)
        seen_during_block.append(len(world.events))
        moved = uow.commands.transition_vehicle(
            "V001",
            VehicleEvent.RESERVE,
            1,
            world.reservation,
            TransitionCtx(claim_id=claim.value.claim_id),
        )
        assert isinstance(moved, Ok)
        seen_during_block.append(len(world.events))
        assert isinstance(uow.commit(), Ok)

    assert seen_during_block == [0, 0]  # nothing is published before the commit
    assert world.vehicle("V001").state is VehicleState.RESERVED
    assert [e.type for e in world.events] == [
        EventType.CLAIM_PLACED.value,
        EventType.VEHICLE_STATE_CHANGED.value,
    ]


def test_leaving_the_block_without_commit_rolls_everything_back(world):
    world.park("V001", "S02")

    with world.core.unit_of_work() as uow:
        claim = uow.commands.place_claim(*place_args(world))
        assert isinstance(claim, Ok)
        uow.commands.transition_vehicle(
            "V001",
            VehicleEvent.RESERVE,
            1,
            world.reservation,
            TransitionCtx(claim_id=claim.value.claim_id),
        )

    assert world.vehicle("V001").state is VehicleState.AVAILABLE
    assert world.vehicle("V001").version == 1
    assert world.repo.query(ResourceClaim) == []
    assert world.repo.query(StateChangeRecord) == []
    assert world.events == []


def test_explicit_rollback_discards_changes_and_events(world):
    world.park("V001", "S02")

    with world.core.unit_of_work() as uow:
        uow.commands.place_claim(*place_args(world))
        uow.rollback()

    assert world.repo.query(ResourceClaim) == []
    assert world.events == []


def test_an_exception_inside_the_block_rolls_back_and_propagates(world):
    world.park("V001", "S02")

    with pytest.raises(RuntimeError, match="boom"), world.core.unit_of_work() as uow:
        uow.commands.place_claim(*place_args(world))
        raise RuntimeError("boom")

    assert world.repo.query(ResourceClaim) == []
    assert isinstance(world.core.queries.get_vehicle("V001"), Ok)  # the core is still usable


def test_a_failing_command_undoes_only_itself(world):
    world.park("V001", "S02")

    with world.core.unit_of_work() as uow:
        first = uow.commands.place_claim(*place_args(world, ref="R1"))
        conflict = uow.commands.place_claim(*place_args(world, ref="R2"))
        assert isinstance(first, Ok)
        assert isinstance(conflict, Err)
        assert conflict.code is ErrorCode.CLAIM_CONFLICT
        assert isinstance(uow.commit(), Ok)

    claims = world.repo.query(ResourceClaim)
    assert [c.holder_ref for c in claims] == ["R1"]
    assert [e.type for e in world.events] == [EventType.CLAIM_PLACED.value]


def test_a_failure_halfway_through_a_command_leaves_no_partial_change(world):
    """The return fails after the vehicle was prepared; neither vehicle nor space may change."""
    world.park("V001", "S02")
    claim_id = world.claim_vehicle("V001")
    reserved = world.core.commands.transition_vehicle(
        "V001", VehicleEvent.RESERVE, 1, world.reservation, TransitionCtx(claim_id=claim_id)
    )
    assert isinstance(reserved, Ok)
    picked = world.core.commands.transition_vehicle(
        "V001", VehicleEvent.PICKUP, 2, world.reservation, TransitionCtx(claim_id=claim_id)
    )
    assert isinstance(picked, Ok)
    log_size = len(world.repo.query(StateChangeRecord))
    world.events.clear()

    with world.core.unit_of_work() as uow:
        failed = uow.commands.transition_vehicle(
            "V001",
            VehicleEvent.RETURN,
            3,
            world.reservation,
            TransitionCtx(parking_space_id="NOPE"),
        )
        assert isinstance(failed, Err)
        uow.commit()

    assert world.vehicle("V001").state is VehicleState.IN_USE
    assert len(world.repo.query(StateChangeRecord)) == log_size
    assert world.events == []


@pytest.mark.parametrize("fail_after_step", [0, 1, 2, 3])
def test_pickup_is_all_or_nothing_under_fault_injection(world, fail_after_step):
    """NFR-09: inject a failure after each step of a multi-step operation."""
    world.park("V001", "S02")
    claim_id = world.claim_vehicle("V001")
    reserved = world.core.commands.transition_vehicle(
        "V001", VehicleEvent.RESERVE, 1, world.reservation, TransitionCtx(claim_id=claim_id)
    )
    assert isinstance(reserved, Ok)
    world.events.clear()
    state_before = world.repo.export_state()

    with pytest.raises(RuntimeError), world.core.unit_of_work() as uow:
        steps = [
            lambda: uow.commands.transition_vehicle(
                "V001",
                VehicleEvent.PICKUP,
                reserved.value.version,
                world.reservation,
                TransitionCtx(claim_id=claim_id),
            ),
            lambda: uow.commands.release_claim(claim_id, world.reservation),
            lambda: uow.queries.get_vehicle("V001"),
        ]
        for index, step in enumerate(steps):
            if index == fail_after_step:
                raise RuntimeError("injected fault")
            step()
        raise RuntimeError("injected fault")

    assert world.repo.export_state() == state_before  # not one field of the store changed
    assert world.events == []
    assert world.vehicle("V001").state is VehicleState.RESERVED
    assert world.space("S02").status is SpaceStatus.OCCUPIED


def test_pickup_with_its_claim_release_commits_together(world):
    world.park("V001", "S02")
    claim_id = world.claim_vehicle("V001")
    world.core.commands.transition_vehicle(
        "V001", VehicleEvent.RESERVE, 1, world.reservation, TransitionCtx(claim_id=claim_id)
    )

    with world.core.unit_of_work() as uow:
        picked = uow.commands.transition_vehicle(
            "V001", VehicleEvent.PICKUP, 2, world.reservation, TransitionCtx(claim_id=claim_id)
        )
        released = uow.commands.release_claim(claim_id, world.reservation)
        assert isinstance(picked, Ok) and isinstance(released, Ok)
        assert isinstance(uow.commit(), Ok)

    assert world.vehicle("V001").state is VehicleState.IN_USE
    assert world.repo.get(ResourceClaim, claim_id).status.value == "RELEASED"  # type: ignore[union-attr]


def test_a_unit_of_work_does_not_nest_and_the_lock_is_freed(world):
    with (
        world.core.unit_of_work(),
        pytest.raises(RuntimeError, match="does not nest"),
        world.core.unit_of_work(),
    ):
        pass

    with world.core.unit_of_work() as again:  # usable again afterwards
        assert isinstance(again.queries.get_config().low_battery_threshold, float)


def test_commit_twice_reports_an_error(world):
    with world.core.unit_of_work() as uow:
        assert isinstance(uow.commit(), Ok)
        second = uow.commit()

    assert isinstance(second, Err)
    assert second.code is ErrorCode.INTERNAL_ERROR


def test_a_failing_event_handler_does_not_undo_the_commit(world):
    world.park("V001", "S02")

    def broken(_event):
        raise ValueError("handler bug")

    world.core.events.subscribe(EventType.CLAIM_PLACED, broken)

    result = world.core.commands.place_claim(*place_args(world))

    assert isinstance(result, Ok)
    assert len(world.repo.query(ResourceClaim)) == 1
    assert len(world.events) == 1  # the other handler still ran


def test_a_command_alone_commits_and_publishes(world):
    world.park("V001", "S02")

    result = world.core.commands.place_claim(*place_args(world))

    assert isinstance(result, Ok)
    assert len(world.events) == 1
    assert isinstance(world.repo.get(Vehicle, "V001"), Vehicle)


def reserved_and_claimed(world):
    world.park("V001", "S02")
    claim_id = world.claim_vehicle("V001")
    reserved = world.core.commands.transition_vehicle(
        "V001", VehicleEvent.RESERVE, 1, world.reservation, TransitionCtx(claim_id=claim_id)
    )
    assert isinstance(reserved, Ok)
    world.events.clear()
    return claim_id, reserved.value.version


def fail_on_space_update(world, monkeypatch):
    """Make the storage fail on the second write of a pickup (the space, after the vehicle)."""
    original = world.repo.update

    def update(entity, expected_version=None):
        if type(entity).__name__ == "ParkingSpace":
            raise VersionConflictError("injected: the space changed meanwhile")
        original(entity, expected_version)

    monkeypatch.setattr(world.repo, "update", update)


def test_a_storage_failure_halfway_leaves_no_partial_change(world, monkeypatch):
    claim_id, version = reserved_and_claimed(world)
    state_before = world.repo.export_state()
    fail_on_space_update(world, monkeypatch)

    result = world.core.commands.transition_vehicle(
        "V001", VehicleEvent.PICKUP, version, world.reservation, TransitionCtx(claim_id=claim_id)
    )

    assert isinstance(result, Err)
    assert result.code is ErrorCode.VERSION_CONFLICT
    assert world.repo.export_state() == state_before  # the vehicle write was undone too
    assert world.events == []


def test_inside_a_unit_of_work_a_storage_failure_undoes_only_that_command(world, monkeypatch):
    claim_id, version = reserved_and_claimed(world)
    fail_on_space_update(world, monkeypatch)

    with world.core.unit_of_work() as uow:
        placed = uow.commands.place_claim(*place_args(world, resource="V002", ref="R9"))
        failed = uow.commands.transition_vehicle(
            "V001",
            VehicleEvent.PICKUP,
            version,
            world.reservation,
            TransitionCtx(claim_id=claim_id),
        )
        assert isinstance(failed, Err)
        assert isinstance(uow.commit(), Ok)

    assert isinstance(placed, Err)  # V002 does not exist, so this one failed on its own
    assert world.vehicle("V001").state is VehicleState.RESERVED
    assert world.vehicle("V001").version == 2
    assert world.events == []


def test_an_unexpected_exception_in_a_command_becomes_internal_error(world, monkeypatch):
    claim_id, version = reserved_and_claimed(world)
    state_before = world.repo.export_state()

    def explode(_entity, _expected_version=None):
        raise ZeroDivisionError("bug")

    monkeypatch.setattr(world.repo, "update", explode)

    result = world.core.commands.transition_vehicle(
        "V001", VehicleEvent.PICKUP, version, world.reservation, TransitionCtx(claim_id=claim_id)
    )

    assert isinstance(result, Err)
    assert result.code is ErrorCode.INTERNAL_ERROR
    assert world.repo.export_state() == state_before
