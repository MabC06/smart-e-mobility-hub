"""HubQueries, the event bus and the id generator."""

from datetime import timedelta

from core.domain.entities import DomainEvent
from core.domain.enums import (
    ChargingPointStatus,
    HolderKind,
    Ownership,
    ResourceType,
    SpaceStatus,
    VehicleEvent,
    VehicleState,
    VehicleType,
)
from core.errors import ErrorCode
from core.events import EventBus, EventType
from core.ids import SequentialIdGenerator
from core.result import Err, Ok
from core.services.commands import TransitionCtx
from core.views import VehicleFilter


def test_hub_view_numbers(world):
    world.park("V001", "S02")
    world.park("V002", "S03", state=VehicleState.MAINTENANCE)

    hub = world.core.queries.get_hub("H01")

    assert isinstance(hub, Ok)
    view = hub.value
    assert (view.parking_capacity, view.occupied, view.free_spaces) == (3, 2, 1)
    assert (view.charging_points, view.charging_in_use) == (1, 0)
    assert view.available_vehicles == 1  # the one in maintenance does not count
    assert view.occupied <= view.parking_capacity
    assert view.as_of == world.clock.now()


def test_list_hubs_is_sorted_and_unknown_hub_is_not_found(world):
    assert [h.hub_id for h in world.core.queries.list_hubs()] == ["H01", "H02"]
    result = world.core.queries.get_hub("NOPE")
    assert isinstance(result, Err)
    assert result.code is ErrorCode.NOT_FOUND


def test_charging_in_use_counts_points_that_are_charging(world):
    world.core.commands.set_charging_point_status(
        "CP01", ChargingPointStatus.CHARGING, 1, world.charging
    )

    hub = world.core.queries.get_hub("H01")

    assert isinstance(hub, Ok)
    assert hub.value.charging_in_use == 1


def test_find_vehicles_filters_and_sorts_by_id(world):
    world.park("V003", "S01", battery_pct=90.0)
    world.park("V001", "S02", battery_pct=20.0)
    world.park("V002", "S11", battery_pct=60.0)

    everyone = world.core.queries.find_vehicles()
    in_h01 = world.core.queries.find_vehicles(VehicleFilter(hub_id="H01"))
    charged = world.core.queries.find_vehicles(VehicleFilter(min_battery=50.0))
    none = world.core.queries.find_vehicles(VehicleFilter(vehicle_type=VehicleType.E_MOTORCYCLE))
    private = world.core.queries.find_vehicles(VehicleFilter(ownership=Ownership.PRIVATE))

    assert [v.vehicle_id for v in everyone] == ["V001", "V002", "V003"]
    assert [v.vehicle_id for v in in_h01] == ["V001", "V003"]
    assert [v.vehicle_id for v in charged] == ["V002", "V003"]
    assert none == [] and private == []


def test_find_vehicles_by_state(world):
    world.park("V001", "S02")
    world.park("V002", "S03", state=VehicleState.MAINTENANCE)

    found = world.core.queries.find_vehicles(VehicleFilter(state=VehicleState.MAINTENANCE))

    assert [v.vehicle_id for v in found] == ["V002"]


def test_get_vehicle(world):
    world.park("V001", "S02")

    ok = world.core.queries.get_vehicle("V001")
    missing = world.core.queries.get_vehicle("NOPE")

    assert isinstance(ok, Ok) and ok.value.version == 1
    assert isinstance(missing, Err) and missing.code is ErrorCode.NOT_FOUND


def test_list_spaces_and_charging_points(world):
    world.park("V001", "S02")

    all_spaces = world.core.queries.list_spaces("H01")
    free = world.core.queries.list_spaces("H01", SpaceStatus.AVAILABLE)
    points = world.core.queries.list_charging_points("H01")
    none = world.core.queries.list_charging_points("H02")

    assert [s.parking_space_id for s in all_spaces] == ["S01", "S02", "S03"]
    assert [s.parking_space_id for s in free] == ["S01", "S03"]
    assert [p.charging_point_id for p in points] == ["CP01"]
    assert none == []


def space_claim(world, space_id, start, minutes):
    placed = world.core.commands.place_claim(
        ResourceType.SPACE,
        space_id,
        HolderKind.RESERVATION,
        f"R-{space_id}-{minutes}",
        start,
        start + timedelta(minutes=minutes),
        world.reservation,
    )
    assert isinstance(placed, Ok)
    return placed.value


def find_space(world, hub_id="H01", start_minutes=0, minutes=10, **kw):
    start = world.clock.now() + timedelta(minutes=start_minutes)
    return world.core.queries.find_free_space(
        hub_id, start, start + timedelta(minutes=minutes), **kw
    )


def test_find_free_space_gives_the_lowest_free_space(world):
    world.park("V001", "S01")

    found = find_space(world)

    assert isinstance(found, Ok) and found.value.parking_space_id == "S02"
    assert find_space(world).value == found.value  # asking twice gives the same answer


def test_find_free_space_skips_spaces_held_in_the_window(world):
    base = world.clock.now()
    space_claim(world, "S01", base, 30)

    assert find_space(world).value.parking_space_id == "S02"
    # A hold that ends at the start of the window, or starts at its end, does not block.
    assert find_space(world, start_minutes=30).value.parking_space_id == "S01"
    later = base + timedelta(minutes=60)
    first = space_claim(world, "S01", later, 10)
    space_claim(world, "S02", later, 10)
    assert find_space(world, start_minutes=55, minutes=10).value.parking_space_id == "S03"
    world.core.commands.release_claim(first.claim_id, world.reservation)
    assert find_space(world, start_minutes=55, minutes=10).value.parking_space_id == "S01"


def test_find_free_space_can_choose_bays_or_ordinary_spaces(world):
    bay = find_space(world, charging_bay=True)
    ordinary = find_space(world, charging_bay=False)

    assert bay.value.parking_space_id == "S01"  # the bay of CP01
    assert ordinary.value.parking_space_id == "S02"


def test_find_free_space_errors(world):
    world.park("V001", "S01")
    world.park("V002", "S02")
    world.park("V003", "S03")
    start = world.clock.now()

    full = find_space(world)
    unknown = find_space(world, hub_id="NOPE")
    reversed_window = world.core.queries.find_free_space("H01", start, start)

    assert isinstance(full, Err) and full.code is ErrorCode.HUB_FULL
    assert isinstance(unknown, Err) and unknown.code is ErrorCode.NOT_FOUND
    assert isinstance(reversed_window, Err) and reversed_window.code is ErrorCode.INVALID_INPUT


def test_get_claims_returns_active_claims_overlapping_the_window(world):
    world.park("V001", "S02")
    base = world.clock.now()
    commands = world.core.commands
    first = commands.place_claim(
        ResourceType.VEHICLE,
        "V001",
        HolderKind.RESERVATION,
        "R1",
        base,
        base + timedelta(minutes=10),
        world.reservation,
    )
    assert isinstance(first, Ok)
    commands.place_claim(
        ResourceType.VEHICLE,
        "V001",
        HolderKind.RESERVATION,
        "R2",
        base + timedelta(minutes=30),
        base + timedelta(minutes=40),
        world.reservation,
    )

    early = world.core.queries.get_claims("V001", base, base + timedelta(minutes=20))
    touching = world.core.queries.get_claims(
        "V001", base + timedelta(minutes=10), base + timedelta(minutes=30)
    )
    commands.release_claim(first.value.claim_id, world.reservation)
    after_release = world.core.queries.get_claims("V001", base, base + timedelta(minutes=20))

    assert [c.holder_ref for c in early] == ["R1"]
    assert touching == []
    assert after_release == []


def test_state_log_is_newest_first_and_can_be_limited(world):
    world.park("V001", "S02")
    claim_id = world.claim_vehicle("V001")
    world.core.commands.transition_vehicle(
        "V001", VehicleEvent.RESERVE, 1, world.reservation, TransitionCtx(claim_id=claim_id)
    )
    world.clock.advance(timedelta(minutes=1))
    world.core.commands.transition_vehicle(
        "V001", VehicleEvent.RELEASE_RESERVATION, 2, world.reservation
    )

    log = world.core.queries.get_state_log("V001")
    limited = world.core.queries.get_state_log("V001", limit=1)

    assert [r.trigger for r in log] == ["release_reservation", "reserve"]
    assert [r.trigger for r in limited] == ["release_reservation"]
    assert world.core.queries.get_state_log("NOPE") == []


def test_config_view(world):
    config = world.core.queries.get_config()

    assert config.low_battery_threshold == 15.0
    assert config.near_capacity_threshold == 90.0


def test_event_bus_order_filtering_and_isolation():
    bus = EventBus()
    seen: list[str] = []
    bus.subscribe(EventType.CLAIM_PLACED, lambda e: seen.append(f"a:{e.event_id}"))
    bus.subscribe(EventType.CLAIM_PLACED, lambda e: seen.append(f"b:{e.event_id}"))
    bus.subscribe(EventType.HUB_STATUS_CHANGED, lambda e: seen.append("hub"))

    from datetime import UTC, datetime

    bus.publish(DomainEvent("E1", EventType.CLAIM_PLACED.value, datetime(2026, 11, 2, tzinfo=UTC)))
    bus.publish(DomainEvent("E2", "Unsubscribed", datetime(2026, 11, 2, tzinfo=UTC)))

    assert seen == ["a:E1", "b:E1"]


def test_id_generator_is_sequential_per_prefix():
    ids = SequentialIdGenerator()

    assert [ids.next_id("C"), ids.next_id("C"), ids.next_id("V")] == [
        "C-000001",
        "C-000002",
        "V-000001",
    ]
