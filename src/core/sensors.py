"""Sensor events: what the IoT simulator sends through the state-update interface (D-004, NFR-10).

The fields are deliberately loose (``type`` is a string, ``value`` is any value), because the feed
is outside the system: core must check them and reject a bad event without a crash.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class SensorEventType(StrEnum):
    """What each type expects in ``entity_id`` and ``value``.

    - BATTERY_LEVEL: vehicle ID, battery percent 0..100.
    - SPACE_OCCUPIED: parking space ID, ID of the vehicle detected there.
    - SPACE_FREED: parking space ID, no value.
    - CHARGER_FAULT: charging point ID, True (fault, the default) or False (fault cleared).
    - VEHICLE_FAULT: vehicle ID, no value.
    - HEARTBEAT: ID of the sensor or Hub that is alive, no value.
    """

    BATTERY_LEVEL = "BATTERY_LEVEL"
    SPACE_OCCUPIED = "SPACE_OCCUPIED"
    SPACE_FREED = "SPACE_FREED"
    CHARGER_FAULT = "CHARGER_FAULT"
    VEHICLE_FAULT = "VEHICLE_FAULT"
    HEARTBEAT = "HEARTBEAT"


@dataclass(frozen=True, slots=True)
class SensorEvent:
    event_id: str
    source: str
    type: str
    entity_id: str
    at: datetime
    value: float | str | bool | None = None


@dataclass(frozen=True, slots=True)
class SensorResult:
    """``changed`` is False when the event only confirmed what core already recorded."""

    event_id: str
    type: SensorEventType
    changed: bool
    detail: str = ""
