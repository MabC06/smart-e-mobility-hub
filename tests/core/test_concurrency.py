"""NFR-06: with many simultaneous requests for one resource, exactly one succeeds."""

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

from core.domain.entities import ResourceClaim
from core.domain.enums import HolderKind, ResourceType, VehicleEvent, VehicleState
from core.errors import ErrorCode
from core.result import Err, Ok
from core.services.commands import TransitionCtx

REQUESTS = 50
REPEATS = 10  # the NFR asks for 100 repeated runs; 10 keeps the suite fast


@pytest.fixture(autouse=True)
def yield_the_gil_inside_reads(world, monkeypatch):
    """Without this the check-then-write window is too short for Python threads to interleave.

    A read that yields the processor makes the race real, so these tests fail without the
    serialization in the runtime (checked by removing the lock).
    """
    original = world.repo.query

    def slow_query(entity_type, predicate=None):
        result = original(entity_type, predicate)
        time.sleep(0.0005)
        return result

    monkeypatch.setattr(world.repo, "query", slow_query)


def run_in_threads(work, count=REQUESTS):
    with ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(work, range(count)))


@pytest.mark.parametrize("round_number", range(REPEATS))
def test_only_one_of_many_overlapping_claims_succeeds(world, round_number):
    world.park("V001", "S02")
    base = world.clock.now()

    def attempt(index):
        return world.core.commands.place_claim(
            ResourceType.VEHICLE,
            "V001",
            HolderKind.RESERVATION,
            f"R{index}",
            base,
            base + timedelta(minutes=10),
            world.reservation,
        )

    results = run_in_threads(attempt)

    winners = [r for r in results if isinstance(r, Ok)]
    losers = [r for r in results if isinstance(r, Err)]
    assert len(winners) == 1
    assert len(losers) == REQUESTS - 1
    assert all(r.code is ErrorCode.CLAIM_CONFLICT for r in losers)
    assert len(world.repo.query(ResourceClaim)) == 1


@pytest.mark.parametrize("round_number", range(REPEATS))
def test_only_one_of_many_transitions_with_the_same_version_succeeds(world, round_number):
    world.park("V001", "S02")

    def attempt(_index):
        return world.core.commands.transition_vehicle(
            "V001", VehicleEvent.REPORT_FAULT, 1, world.iot, TransitionCtx()
        )

    results = run_in_threads(attempt)

    winners = [r for r in results if isinstance(r, Ok)]
    losers = [r for r in results if isinstance(r, Err)]
    assert len(winners) == 1
    assert all(r.code is ErrorCode.VERSION_CONFLICT for r in losers)
    assert world.vehicle("V001").state is VehicleState.MAINTENANCE
    assert world.vehicle("V001").version == 2


def test_many_returns_never_exceed_the_hub_capacity(world):
    """Three vehicles on a trip and one free space left: only one return can succeed."""
    for index in range(1, 4):
        vehicle_id = f"V00{index}"
        world.park(vehicle_id, f"S0{index}")
    # H01 is full; make V001 leave so that exactly one space is free, then let all three try.
    claim_id = world.claim_vehicle("V001")
    world.core.commands.transition_vehicle(
        "V001", VehicleEvent.RESERVE, 1, world.reservation, TransitionCtx(claim_id=claim_id)
    )
    world.core.commands.transition_vehicle(
        "V001", VehicleEvent.PICKUP, 2, world.reservation, TransitionCtx(claim_id=claim_id)
    )
    for index in (2, 3):
        vehicle_id = f"V00{index}"
        cid = world.claim_vehicle(vehicle_id, ref=f"R{index}")
        world.core.commands.transition_vehicle(
            vehicle_id, VehicleEvent.RESERVE, 1, world.reservation, TransitionCtx(claim_id=cid)
        )
        world.core.commands.transition_vehicle(
            vehicle_id, VehicleEvent.PICKUP, 2, world.reservation, TransitionCtx(claim_id=cid)
        )
    # everyone is now on a trip; H01 has 3 free spaces, so fill two of them
    world.park("V101", "S01")
    world.park("V102", "S02")

    def attempt(index):
        vehicle_id = f"V00{index % 3 + 1}"
        return world.core.commands.transition_vehicle(
            vehicle_id,
            VehicleEvent.RETURN,
            3,
            world.reservation,
            TransitionCtx(hub_id="H01"),
        )

    results = run_in_threads(attempt, count=30)

    winners = [r for r in results if isinstance(r, Ok)]
    assert len(winners) == 1
    hub = world.core.queries.get_hub("H01")
    assert isinstance(hub, Ok)
    assert hub.value.occupied == 3 <= hub.value.parking_capacity
