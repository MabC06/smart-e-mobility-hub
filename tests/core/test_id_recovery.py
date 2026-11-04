"""Core regression: new writes must work after persistence/snapshot reconstruction."""

from core.domain.entities import DomainEvent, ResourceClaim, StateChangeRecord
from core.domain.enums import HolderKind, Ownership, ResourceType, VehicleEvent, VehicleType
from core.events import EventType
from core.facade import CoreFacade
from core.ids import SequentialIdGenerator
from core.result import Ok
from core.services.transition_ctx import TransitionCtx


def test_counters_resume_from_maximum_per_prefix():
    ids = SequentialIdGenerator(
        [
            "CLM-000009",
            "CLM-000003",
            "EVT-000100",
            "opaque",
            "LOG-not-numeric",
            "-123",
        ]
    )
    assert ids.next_id("CLM") == "CLM-000010"
    assert ids.next_id("EVT") == "EVT-000101"
    assert ids.next_id("LOG") == "LOG-000001"


def test_default_facade_continues_claim_vehicle_audit_and_event_ids(world):
    """Same repository, new process-local facade: exercise every generated ID prefix."""
    from datetime import timedelta

    def create(core, plate, space, ref):
        vehicle = core.commands.register_vehicle(
            Ownership.FLEET,
            plate,
            VehicleType.E_BIKE,
            0.5,
            80,
            world.operator,
            parking_space_id=space,
        )
        assert isinstance(vehicle, Ok)
        claim = core.commands.place_claim(
            ResourceType.VEHICLE,
            vehicle.value.vehicle_id,
            HolderKind.RESERVATION,
            ref,
            world.clock.now(),
            world.clock.now() + timedelta(minutes=10),
            world.reservation,
        )
        assert isinstance(claim, Ok)
        reserved = core.commands.transition_vehicle(
            vehicle.value.vehicle_id,
            VehicleEvent.RESERVE,
            vehicle.value.version,
            world.reservation,
            TransitionCtx(claim_id=claim.value.claim_id),
        )
        assert isinstance(reserved, Ok)
        return vehicle.value.vehicle_id, claim.value.claim_id

    first = create(world.core, "FIRST", "S02", "R1")
    world.repo.add(DomainEvent("EVT-000100", "persisted-event", world.clock.now(), {}))
    before_logs = len(world.repo.query(StateChangeRecord))
    again = CoreFacade(world.repo, world.clock)
    events = []
    for event_type in EventType:
        again.events.subscribe(event_type, events.append)
    second = create(again, "SECOND", "S03", "R2")
    assert first[0] != second[0] and first[1] != second[1]
    assert len(world.repo.query(ResourceClaim)) == 2
    assert events
    assert all(int(e.event_id.rsplit("-", 1)[1]) > 100 for e in events)
    assert len(world.repo.query(StateChangeRecord)) > before_logs
    assert again.check_invariants() == []


def test_explicit_generator_is_used_as_supplied(world):
    class CustomIds(SequentialIdGenerator):
        def next_id(self, prefix: str) -> str:
            return super().next_id(f"{prefix}-CUSTOM")

    core = CoreFacade(world.repo, world.clock, ids=CustomIds())
    result = core.commands.register_vehicle(
        Ownership.FLEET,
        "CUSTOM",
        VehicleType.E_BIKE,
        0.5,
        80,
        world.operator,
        parking_space_id="S02",
    )
    assert isinstance(result, Ok)
    assert result.value.vehicle_id == "VEH-CUSTOM-000001"
