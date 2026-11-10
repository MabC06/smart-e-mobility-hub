"""State-transition tests of the Vehicle state machine (BR-M1-03, NFR-08).

The expected table below is written out by hand from docs/design/behavioral/vehicle-state-machine.md
and is deliberately not derived from the implementation.
"""

from collections.abc import Callable
from itertools import product

import pytest

from core.config import CoreConfig
from core.domain.entities import Vehicle
from core.domain.enums import VehicleEvent, VehicleState
from core.domain.state_machine import (
    TRANSITION_LIST,
    TransitionContext,
    VehicleStateMachine,
)
from core.errors import ErrorCode
from core.result import Err, Ok

S = VehicleState
E = VehicleEvent

# (state, event) -> state after a successful transition
EXPECTED_VALID: dict[tuple[VehicleState, VehicleEvent], VehicleState] = {
    (S.AVAILABLE, E.RESERVE): S.RESERVED,  # T1
    (S.RESERVED, E.RELEASE_RESERVATION): S.AVAILABLE,  # T2
    (S.RESERVED, E.PICKUP): S.IN_USE,  # T3
    (S.IN_USE, E.RETURN): S.RETURNED,  # T4
    (S.IN_USE, E.RETURN_FAULTY): S.MAINTENANCE,  # T5
    (S.RETURNED, E.MARK_READY): S.AVAILABLE,  # T6
    (S.RETURNED, E.START_CHARGING): S.CHARGING,  # T7
    (S.AVAILABLE, E.START_CHARGING): S.CHARGING,  # T8
    (S.CHARGING, E.FINISH_CHARGING): S.AVAILABLE,  # T9
    (S.CHARGING, E.INTERRUPT_CHARGING): S.RETURNED,  # T10
    (S.AVAILABLE, E.REPORT_FAULT): S.MAINTENANCE,  # T11
    (S.RESERVED, E.REPORT_FAULT): S.MAINTENANCE,  # T11
    (S.RETURNED, E.REPORT_FAULT): S.MAINTENANCE,  # T11
    (S.CHARGING, E.REPORT_FAULT): S.MAINTENANCE,  # T11
    (S.MAINTENANCE, E.REPAIR): S.RETURNED,  # T12
    (S.IN_USE, E.ARRIVE): S.AVAILABLE,  # T13, private EV only
    (S.AVAILABLE, E.DEPART): S.IN_USE,  # T14, private EV only
    (S.RETURNED, E.DEPART): S.IN_USE,  # T15, private EV only
}
# Special case of T11: accepted, the state stays IN_USE and the fault flag is set.
SPECIAL = (S.IN_USE, E.REPORT_FAULT)

ALL_PAIRS = list(product(VehicleState, VehicleEvent))
INVALID_PAIRS = [p for p in ALL_PAIRS if p not in EXPECTED_VALID and p != SPECIAL]


@pytest.fixture
def machine() -> VehicleStateMachine:
    return VehicleStateMachine(CoreConfig())


def test_counts_match_the_design_document() -> None:
    assert len(ALL_PAIRS) == 78
    assert len(EXPECTED_VALID) == 18
    assert len(INVALID_PAIRS) == 59
    # 15 rows, T11 has four sources, T15 shares the event of T14, plus the special case
    assert len(TRANSITION_LIST) == 19


@pytest.mark.parametrize(("state", "event"), ALL_PAIRS)
def test_allowed_matches_the_table(
    machine: VehicleStateMachine, state: VehicleState, event: VehicleEvent
) -> None:
    if (state, event) == SPECIAL:
        assert machine.allowed(state, event) is S.IN_USE
    else:
        assert machine.allowed(state, event) is EXPECTED_VALID.get((state, event))


@pytest.mark.parametrize(("pair", "target"), list(EXPECTED_VALID.items()))
def test_every_valid_transition_is_applied(
    machine: VehicleStateMachine,
    make_vehicle: Callable[..., Vehicle],
    pair: tuple[VehicleState, VehicleEvent],
    target: VehicleState,
) -> None:
    state, event = pair
    vehicle = make_vehicle(state=state, battery_pct=80.0)

    result = machine.apply(vehicle, event, TransitionContext(min_battery=20.0))

    assert isinstance(result, Ok)
    assert result.value.previous_state is state
    assert result.value.new_state is target
    assert vehicle.state is target


@pytest.mark.parametrize(("state", "event"), INVALID_PAIRS)
def test_every_invalid_pair_is_rejected_and_changes_nothing(
    machine: VehicleStateMachine,
    make_vehicle: Callable[..., Vehicle],
    state: VehicleState,
    event: VehicleEvent,
) -> None:
    vehicle = make_vehicle(state=state)

    result = machine.apply(vehicle, event)

    assert isinstance(result, Err)
    assert result.code is ErrorCode.INVALID_TRANSITION
    assert vehicle.state is state
    assert vehicle.fault_flag is False


def test_fault_reported_during_a_trip_only_sets_the_flag(
    machine: VehicleStateMachine, make_vehicle: Callable[..., Vehicle]
) -> None:
    vehicle = make_vehicle(state=S.IN_USE)

    result = machine.apply(vehicle, E.REPORT_FAULT)

    assert isinstance(result, Ok)
    assert vehicle.state is S.IN_USE
    assert vehicle.fault_flag is True


def test_return_faulty_sets_the_flag_and_repair_clears_it(
    machine: VehicleStateMachine, make_vehicle: Callable[..., Vehicle]
) -> None:
    vehicle = make_vehicle(state=S.IN_USE)

    assert isinstance(machine.apply(vehicle, E.RETURN_FAULTY), Ok)
    assert vehicle.state is S.MAINTENANCE
    assert vehicle.fault_flag is True

    assert isinstance(machine.apply(vehicle, E.REPAIR), Ok)
    assert vehicle.state is S.RETURNED
    assert vehicle.fault_flag is False


def test_plain_return_is_rejected_when_a_fault_was_reported(
    machine: VehicleStateMachine, make_vehicle: Callable[..., Vehicle]
) -> None:
    vehicle = make_vehicle(state=S.IN_USE, fault_flag=True)

    result = machine.apply(vehicle, E.RETURN)

    assert isinstance(result, Err)
    assert result.code is ErrorCode.RESOURCE_UNAVAILABLE
    assert vehicle.state is S.IN_USE


# Boundary values around LOW_BATTERY_THRESHOLD = 15 (a vehicle at exactly 15 % is still low).
@pytest.mark.parametrize(
    ("battery", "accepted"),
    [(14.99, False), (15.0, False), (15.01, True)],
)
@pytest.mark.parametrize(("state", "event"), [(S.AVAILABLE, E.RESERVE), (S.RETURNED, E.MARK_READY)])
def test_low_battery_threshold_boundary(
    machine: VehicleStateMachine,
    make_vehicle: Callable[..., Vehicle],
    state: VehicleState,
    event: VehicleEvent,
    battery: float,
    accepted: bool,
) -> None:
    vehicle = make_vehicle(state=state, battery_pct=battery)

    result = machine.apply(vehicle, event)

    if accepted:
        assert isinstance(result, Ok)
    else:
        assert isinstance(result, Err)
        assert result.code is ErrorCode.BATTERY_TOO_LOW
        assert vehicle.state is state


# Boundary values around the caller's minimum (M2 passes max(20, the student's request)).
@pytest.mark.parametrize(
    ("battery", "accepted"),
    [(49.99, False), (50.0, True), (50.01, True)],
)
def test_reserve_respects_the_requested_minimum(
    machine: VehicleStateMachine,
    make_vehicle: Callable[..., Vehicle],
    battery: float,
    accepted: bool,
) -> None:
    vehicle = make_vehicle(state=S.AVAILABLE, battery_pct=battery)

    result = machine.apply(vehicle, E.RESERVE, TransitionContext(min_battery=50.0))

    if accepted:
        assert isinstance(result, Ok)
    else:
        assert isinstance(result, Err)
        assert result.code is ErrorCode.BATTERY_TOO_LOW


def test_a_vehicle_with_a_fault_cannot_be_reserved_or_marked_ready(
    machine: VehicleStateMachine, make_vehicle: Callable[..., Vehicle]
) -> None:
    for state, event in [(S.AVAILABLE, E.RESERVE), (S.RETURNED, E.MARK_READY)]:
        vehicle = make_vehicle(state=state, fault_flag=True)
        result = machine.apply(vehicle, event)
        assert isinstance(result, Err)
        assert result.code is ErrorCode.RESOURCE_UNAVAILABLE


def test_threshold_comes_from_configuration(make_vehicle: Callable[..., Vehicle]) -> None:
    strict = VehicleStateMachine(CoreConfig(low_battery_threshold=30.0))
    vehicle = make_vehicle(state=S.AVAILABLE, battery_pct=25.0)

    result = strict.apply(vehicle, E.RESERVE)

    assert isinstance(result, Err)
    assert result.code is ErrorCode.BATTERY_TOO_LOW


def test_check_does_not_change_the_vehicle(
    machine: VehicleStateMachine, make_vehicle: Callable[..., Vehicle]
) -> None:
    vehicle = make_vehicle(state=S.AVAILABLE)

    checked = machine.check(vehicle, E.RESERVE)

    assert isinstance(checked, Ok)
    assert checked.value.ref == "T1"
    assert vehicle.state is S.AVAILABLE
