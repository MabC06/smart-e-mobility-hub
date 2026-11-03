"""Intake of sensor events (docs/design/architecture/core-api-spec.md, section 5).

Rules:
- A bad event (missing field, unknown type, wrong value, unknown entity, or one that contradicts
  the recorded state) is rejected as a whole: no change, a warning in the log, a
  ``SensorEventRejected`` event for M5 and M8, and an ``Err`` for the caller. Core never crashes
  on it (NFR-10).
- An event that only confirms the recorded state is accepted and changes nothing, so a feed that
  repeats itself is harmless.
- Occupancy and faults go through the same commands as every other caller, so the same rules
  and the same log apply. A fleet vehicle never enters or leaves a space on a sensor's word: it
  moves with ``return`` and ``pickup``. Only a private EV arrives and leaves by sensor.
"""

import logging
import math
from datetime import datetime
from typing import TYPE_CHECKING

from core import permissions
from core.actor import Actor
from core.domain.entities import ChargingPoint, DomainEvent, ParkingSpace, Vehicle
from core.domain.enums import (
    ChargingPointStatus,
    Ownership,
    SpaceStatus,
    VehicleEvent,
    VehicleState,
)
from core.errors import ErrorCode
from core.events import EventType
from core.result import Err, Ok, Result
from core.sensors import SensorEvent, SensorEventType, SensorResult
from core.services.runtime import Runtime
from core.services.transition_ctx import TransitionCtx

if TYPE_CHECKING:
    from core.services.commands import StateCommands

logger = logging.getLogger("core.sensors")


def _bad(message: str) -> Err:
    return Err(ErrorCode.INVALID_INPUT, message)


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate(event: SensorEvent) -> Err | None:
    """Everything that can be checked without looking at the stored state."""
    if not _text(event.event_id):
        return _bad("event_id is required")
    if not _text(event.source):
        return _bad("source is required")
    if not _text(event.entity_id):
        return _bad("entity_id is required")
    try:
        kind = SensorEventType(event.type)
    except ValueError:
        return _bad(f"unknown event type {event.type!r}")
    if not isinstance(event.at, datetime) or event.at.utcoffset() is None:
        return _bad("at must be a timezone-aware time")
    value = event.value
    if kind is SensorEventType.BATTERY_LEVEL:
        number = isinstance(value, (int, float)) and not isinstance(value, bool)
        if not number or not math.isfinite(float(value)) or not 0.0 <= float(value) <= 100.0:  # type: ignore[arg-type]
            return _bad(f"BATTERY_LEVEL needs a number between 0 and 100, got {value!r}")
    elif kind is SensorEventType.SPACE_OCCUPIED:
        if not _text(value):
            return _bad("SPACE_OCCUPIED needs the ID of the vehicle in value")
    elif (
        kind is SensorEventType.CHARGER_FAULT and value is not None and not isinstance(value, bool)
    ):
        return _bad(f"CHARGER_FAULT needs True, False or nothing, got {value!r}")
    return None


class SensorIntake:
    def __init__(self, runtime: Runtime, commands: "StateCommands") -> None:
        self._rt = runtime
        self._commands = commands

    def apply(self, event: SensorEvent, actor: Actor) -> Result[SensorResult]:
        result = self._rt.run(lambda: self._apply(event, actor))
        if isinstance(result, Err):
            self._reject(event, result)
        return result

    def _reject(self, event: SensorEvent, error: Err) -> None:
        logger.warning(
            "sensor event rejected: id=%r source=%r type=%r entity=%r code=%s reason=%s",
            event.event_id,
            event.source,
            event.type,
            event.entity_id,
            error.code.value,
            error.message,
        )
        rt = self._rt
        with rt.lock:
            rt.bus.publish(
                DomainEvent(
                    rt.ids.next_id("EVT"),
                    EventType.SENSOR_EVENT_REJECTED.value,
                    rt.now(),
                    {
                        "event_id": str(event.event_id),
                        "source": str(event.source),
                        "type": str(event.type),
                        "entity_id": str(event.entity_id),
                        "code": error.code.value,
                        "reason": error.message,
                    },
                )
            )

    def _apply(self, event: SensorEvent, actor: Actor) -> Result[SensorResult]:
        if not permissions.may_send_sensor_event(actor):
            return Err(ErrorCode.FORBIDDEN, f"{actor.label()} may not send sensor events")
        invalid = validate(event)
        if invalid is not None:
            return invalid
        kind = SensorEventType(event.type)
        match kind:
            case SensorEventType.BATTERY_LEVEL:
                return self._battery(event, kind)
            case SensorEventType.SPACE_OCCUPIED:
                return self._occupied(event, kind, actor)
            case SensorEventType.SPACE_FREED:
                return self._freed(event, kind, actor)
            case SensorEventType.CHARGER_FAULT:
                return self._charger(event, kind, actor)
            case SensorEventType.VEHICLE_FAULT:
                return self._vehicle_fault(event, kind, actor)
            case SensorEventType.HEARTBEAT:
                return self._heartbeat(event, kind)

    # ------------------------------------------------------------------ one handler per type

    def _battery(self, event: SensorEvent, kind: SensorEventType) -> Result[SensorResult]:
        rt = self._rt
        vehicle = rt.repo.get(Vehicle, event.entity_id)
        if vehicle is None:
            return Err(ErrorCode.NOT_FOUND, f"unknown vehicle {event.entity_id!r}")
        level = float(event.value)  # type: ignore[arg-type]
        if vehicle.battery_pct == level:
            return Ok(SensorResult(event.event_id, kind, False, "battery unchanged"))
        previous = vehicle.battery_pct
        vehicle.battery_pct = level
        rt.repo.update(vehicle, vehicle.version)
        rt.emit(
            EventType.VEHICLE_BATTERY_CHANGED,
            {
                "vehicle_id": vehicle.vehicle_id,
                "previous": previous,
                "new": level,
                "low": level <= rt.config.low_battery_threshold,
                "hub_id": vehicle.hub_id,
                "at": event.at.isoformat(),
            },
        )
        return Ok(SensorResult(event.event_id, kind, True))

    def _occupied(
        self, event: SensorEvent, kind: SensorEventType, actor: Actor
    ) -> Result[SensorResult]:
        repo = self._rt.repo
        space = repo.get(ParkingSpace, event.entity_id)
        if space is None:
            return Err(ErrorCode.NOT_FOUND, f"unknown parking space {event.entity_id!r}")
        vehicle_id = str(event.value)
        vehicle = repo.get(Vehicle, vehicle_id)
        if vehicle is None:
            return Err(ErrorCode.NOT_FOUND, f"unknown vehicle {vehicle_id!r}")
        if space.status is SpaceStatus.OCCUPIED and space.occupant_vehicle_id == vehicle_id:
            return Ok(SensorResult(event.event_id, kind, False, "occupancy confirmed"))
        arrives = (
            vehicle.ownership is Ownership.PRIVATE
            and vehicle.state is VehicleState.IN_USE
            and space.status is SpaceStatus.AVAILABLE
        )
        if not arrives:
            return Err(
                ErrorCode.INVALID_TRANSITION,
                f"the sensor sees {vehicle_id!r} in {space.parking_space_id!r}, "
                f"but core records the space as {space.status.value} "
                f"(occupant {space.occupant_vehicle_id!r}) and the vehicle "
                f"in {vehicle.parking_space_id!r}",
            )
        arrived = self._commands._occupy_space(
            vehicle_id, space.parking_space_id, space.version, actor, None
        )
        if isinstance(arrived, Err):
            return arrived
        return Ok(SensorResult(event.event_id, kind, True, "private vehicle arrived"))

    def _freed(
        self, event: SensorEvent, kind: SensorEventType, actor: Actor
    ) -> Result[SensorResult]:
        repo = self._rt.repo
        space = repo.get(ParkingSpace, event.entity_id)
        if space is None:
            return Err(ErrorCode.NOT_FOUND, f"unknown parking space {event.entity_id!r}")
        if space.status is not SpaceStatus.OCCUPIED:
            return Ok(SensorResult(event.event_id, kind, False, "space already free"))
        occupant = repo.get(Vehicle, space.occupant_vehicle_id or "")
        if occupant is None or occupant.ownership is not Ownership.PRIVATE:
            return Err(
                ErrorCode.INVALID_TRANSITION,
                f"the sensor sees {space.parking_space_id!r} freed, but a fleet vehicle "
                f"({space.occupant_vehicle_id!r}) leaves a space only through pickup",
            )
        left = self._commands._free_space(space.parking_space_id, space.version, actor)
        if isinstance(left, Err):
            return left
        return Ok(SensorResult(event.event_id, kind, True, "private vehicle left"))

    def _charger(
        self, event: SensorEvent, kind: SensorEventType, actor: Actor
    ) -> Result[SensorResult]:
        point = self._rt.repo.get(ChargingPoint, event.entity_id)
        if point is None:
            return Err(ErrorCode.NOT_FOUND, f"unknown charging point {event.entity_id!r}")
        faulty = event.value is not False
        out = point.status is ChargingPointStatus.OUT_OF_SERVICE
        if faulty == out:
            return Ok(SensorResult(event.event_id, kind, False, "charging point status confirmed"))
        if not faulty and point.status is not ChargingPointStatus.OUT_OF_SERVICE:
            return Ok(SensorResult(event.event_id, kind, False, "no fault to clear"))
        target = ChargingPointStatus.OUT_OF_SERVICE if faulty else ChargingPointStatus.AVAILABLE
        changed = self._commands._set_charging_point_status(
            point.charging_point_id, target, point.version, actor
        )
        if isinstance(changed, Err):
            return changed
        return Ok(SensorResult(event.event_id, kind, True, target.value))

    def _vehicle_fault(
        self, event: SensorEvent, kind: SensorEventType, actor: Actor
    ) -> Result[SensorResult]:
        vehicle = self._rt.repo.get(Vehicle, event.entity_id)
        if vehicle is None:
            return Err(ErrorCode.NOT_FOUND, f"unknown vehicle {event.entity_id!r}")
        already = vehicle.state is VehicleState.MAINTENANCE or (
            vehicle.state is VehicleState.IN_USE and vehicle.fault_flag
        )
        if already:
            return Ok(SensorResult(event.event_id, kind, False, "fault already recorded"))
        moved = self._commands._transition(
            vehicle.vehicle_id, VehicleEvent.REPORT_FAULT, vehicle.version, actor, TransitionCtx()
        )
        if isinstance(moved, Err):
            return moved
        return Ok(SensorResult(event.event_id, kind, True, moved.value.state.value))

    def _heartbeat(self, event: SensorEvent, kind: SensorEventType) -> Result[SensorResult]:
        rt = self._rt
        rt.emit(
            EventType.SENSOR_HEARTBEAT,
            {
                "source": event.source,
                "entity_id": event.entity_id,
                "sent_at": event.at.isoformat(),
                "received_at": rt.now().isoformat(),
            },
        )
        return Ok(SensorResult(event.event_id, kind, False, "heartbeat"))
