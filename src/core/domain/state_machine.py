"""Vehicle state machine as a data-driven table (BR-M1-03, NFR-08).

The table mirrors docs/design/behavioral/vehicle-state-machine.md, rows T1 to T15. Every pair
(state, event) that is not in the table is rejected with INVALID_TRANSITION and changes nothing.

This module holds only the rules that depend on the vehicle itself (battery, fault flag). Rules
that need other data (a free space at the destination, a claim on the vehicle, a free charging
point) are checked by the command layer, which reads them from the repository.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from core.config import CoreConfig
from core.domain.entities import Vehicle
from core.domain.enums import VehicleEvent, VehicleState
from core.errors import ErrorCode
from core.result import Err, Ok, Result


@dataclass(frozen=True, slots=True)
class TransitionContext:
    """Caller-supplied inputs of a transition. ``min_battery`` is used by ``reserve`` (T1)."""

    min_battery: float = 0.0


@dataclass(frozen=True, slots=True)
class TransitionOutcome:
    previous_state: VehicleState
    new_state: VehicleState
    event: VehicleEvent
    ref: str


type Guard = Callable[[Vehicle, TransitionContext, CoreConfig], Err | None]


@dataclass(frozen=True, slots=True)
class Transition:
    ref: str
    source: VehicleState
    event: VehicleEvent
    target: VehicleState
    guard: Guard | None = None
    set_fault_flag: bool | None = None


def _unavailable(vehicle: Vehicle, message: str) -> Err:
    return Err(
        ErrorCode.RESOURCE_UNAVAILABLE,
        message,
        {"vehicle_id": vehicle.vehicle_id, "fault_flag": vehicle.fault_flag},
    )


def _battery_too_low(vehicle: Vehicle, required: float, message: str) -> Err:
    details = {
        "vehicle_id": vehicle.vehicle_id,
        "battery_pct": vehicle.battery_pct,
        "required": required,
    }
    return Err(ErrorCode.BATTERY_TOO_LOW, message, details)


def _guard_reserve(vehicle: Vehicle, ctx: TransitionContext, config: CoreConfig) -> Err | None:
    """T1: no fault, battery above the low threshold and at least the caller's minimum."""
    if vehicle.fault_flag:
        return _unavailable(vehicle, "vehicle has a fault")
    if vehicle.battery_pct <= config.low_battery_threshold:
        return _battery_too_low(
            vehicle, config.low_battery_threshold, "battery is at or below the low threshold"
        )
    if vehicle.battery_pct < ctx.min_battery:
        return _battery_too_low(vehicle, ctx.min_battery, "battery is below the requested minimum")
    return None


def _guard_return(vehicle: Vehicle, ctx: TransitionContext, config: CoreConfig) -> Err | None:
    """T4: a vehicle with a reported fault ends its trip with ``return_faulty`` (T5)."""
    if vehicle.fault_flag:
        return _unavailable(vehicle, "vehicle has a reported fault; use return_faulty")
    return None


def _guard_mark_ready(vehicle: Vehicle, ctx: TransitionContext, config: CoreConfig) -> Err | None:
    """T6: no fault and battery above the low threshold (a vehicle at exactly 15 % is still low)."""
    if vehicle.fault_flag:
        return _unavailable(vehicle, "vehicle has a fault")
    if vehicle.battery_pct <= config.low_battery_threshold:
        return _battery_too_low(
            vehicle, config.low_battery_threshold, "battery is at or below the low threshold"
        )
    return None


S = VehicleState
E = VehicleEvent

_FAULT_SOURCES = (S.AVAILABLE, S.RESERVED, S.RETURNED, S.CHARGING)

TRANSITION_LIST: tuple[Transition, ...] = (
    Transition("T1", S.AVAILABLE, E.RESERVE, S.RESERVED, guard=_guard_reserve),
    Transition("T2", S.RESERVED, E.RELEASE_RESERVATION, S.AVAILABLE),
    Transition("T3", S.RESERVED, E.PICKUP, S.IN_USE),
    Transition("T4", S.IN_USE, E.RETURN, S.RETURNED, guard=_guard_return),
    Transition("T5", S.IN_USE, E.RETURN_FAULTY, S.MAINTENANCE, set_fault_flag=True),
    Transition("T6", S.RETURNED, E.MARK_READY, S.AVAILABLE, guard=_guard_mark_ready),
    Transition("T7", S.RETURNED, E.START_CHARGING, S.CHARGING),
    Transition("T8", S.AVAILABLE, E.START_CHARGING, S.CHARGING),
    Transition("T9", S.CHARGING, E.FINISH_CHARGING, S.AVAILABLE),
    Transition("T10", S.CHARGING, E.INTERRUPT_CHARGING, S.RETURNED),
    *(Transition("T11", src, E.REPORT_FAULT, S.MAINTENANCE) for src in _FAULT_SOURCES),
    Transition("T12", S.MAINTENANCE, E.REPAIR, S.RETURNED, set_fault_flag=False),
    # A private EV is IN_USE while it is away from every Hub (the command layer keeps these two
    # events for private vehicles and rejects the rental events for them).
    Transition("T13", S.IN_USE, E.ARRIVE, S.AVAILABLE),
    Transition("T14", S.AVAILABLE, E.DEPART, S.IN_USE),
    Transition("T15", S.RETURNED, E.DEPART, S.IN_USE),
    # Special case of T11: a fault reported during a trip only sets the flag; the trip ends with T5.
    Transition("T11s", S.IN_USE, E.REPORT_FAULT, S.IN_USE, set_fault_flag=True),
)

TRANSITIONS: Mapping[tuple[VehicleState, VehicleEvent], Transition] = {
    (t.source, t.event): t for t in TRANSITION_LIST
}


class VehicleStateMachine:
    def __init__(self, config: CoreConfig | None = None) -> None:
        self._config = config or CoreConfig()

    def allowed(self, state: VehicleState, event: VehicleEvent) -> VehicleState | None:
        """Target state of (state, event), or None when the pair is not allowed."""
        transition = TRANSITIONS.get((state, event))
        return None if transition is None else transition.target

    def check(
        self,
        vehicle: Vehicle,
        event: VehicleEvent,
        ctx: TransitionContext | None = None,
    ) -> Result[Transition]:
        """Evaluate the table and the vehicle-level guard without changing the vehicle."""
        transition = TRANSITIONS.get((vehicle.state, event))
        if transition is None:
            return Err(
                ErrorCode.INVALID_TRANSITION,
                f"event {event.value!r} is not allowed in state {vehicle.state.value!r}",
                {"vehicle_id": vehicle.vehicle_id, "state": vehicle.state, "event": event},
            )
        if transition.guard is not None:
            failure = transition.guard(vehicle, ctx or TransitionContext(), self._config)
            if failure is not None:
                return failure
        return Ok(transition)

    def apply(
        self,
        vehicle: Vehicle,
        event: VehicleEvent,
        ctx: TransitionContext | None = None,
    ) -> Result[TransitionOutcome]:
        """Change ``vehicle.state`` and ``vehicle.fault_flag``. Nothing changes on an error.

        The version is not touched here: the repository bumps it when the vehicle is saved.
        """
        checked = self.check(vehicle, event, ctx)
        if isinstance(checked, Err):
            return checked
        transition = checked.value
        previous = vehicle.state
        vehicle.state = transition.target
        if transition.set_fault_flag is not None:
            vehicle.fault_flag = transition.set_fault_flag
        return Ok(TransitionOutcome(previous, transition.target, event, transition.ref))
