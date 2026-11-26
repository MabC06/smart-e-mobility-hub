"""In-process event bus (D-002, D-003).

Events are published after a commit. A failing handler never undoes the commit and never stops
the other handlers; the failure is logged. Handlers run in the order they subscribed.
"""

import logging
from collections.abc import Callable
from enum import StrEnum

from core.domain.entities import DomainEvent

logger = logging.getLogger("core.events")


class EventType(StrEnum):
    VEHICLE_STATE_CHANGED = "VehicleStateChanged"
    SPACE_OCCUPANCY_CHANGED = "SpaceOccupancyChanged"
    CHARGING_POINT_STATUS_CHANGED = "ChargingPointStatusChanged"
    HUB_STATUS_CHANGED = "HubStatusChanged"
    CLAIM_PLACED = "ClaimPlaced"
    CLAIM_RELEASED = "ClaimReleased"
    VEHICLE_BATTERY_CHANGED = "VehicleBatteryChanged"
    SENSOR_HEARTBEAT = "SensorHeartbeat"
    SENSOR_EVENT_REJECTED = "SensorEventRejected"


type Handler = Callable[[DomainEvent], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = {}

    def subscribe(self, event_type: EventType | str, handler: Handler) -> None:
        self._handlers.setdefault(str(event_type), []).append(handler)

    def publish(self, event: DomainEvent) -> None:
        for handler in list(self._handlers.get(event.type, [])):
            try:
                handler(event)
            except Exception:
                logger.exception("handler failed for event %s (%s)", event.event_id, event.type)
