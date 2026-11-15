"""Monitoring module (M5): Operator Monitoring & Incident Handling.

Traceability:
- FR-08 (System Monitoring)
- FR-09 (Incident Handling)
- D-013, D-018
"""

from fastapi import FastAPI

from core.events import EventType
from core.facade import CoreFacade
from monitoring.router import router, set_service
from monitoring.schema import AUDIT_SPEC, INCIDENT_SPEC
from monitoring.service import MonitoringService

__all__ = ["install", "MonitoringService"]


def install(core: CoreFacade, app: FastAPI) -> None:
    """Install the monitoring module into core and the FastAPI application (D-013).

    1. Register relational tables into core's transaction manager (D-018).
    2. Instantiate the MonitoringService.
    3. Subscribe to domain events (SpaceOccupancyChanged, ChargingPointStatusChanged,
       VehicleBatteryChanged).
    4. Mount the monitoring API router on the FastAPI application.
    """
    # Register schemas
    core.register_entity(INCIDENT_SPEC)
    core.register_entity(AUDIT_SPEC)

    # Initialize service
    service = MonitoringService(core)

    # Subscribe to core domain events
    core.events.subscribe(EventType.SPACE_OCCUPANCY_CHANGED, service.on_space_occupancy_changed)
    core.events.subscribe(
        EventType.CHARGING_POINT_STATUS_CHANGED, service.on_charging_point_status_changed
    )
    core.events.subscribe(EventType.VEHICLE_BATTERY_CHANGED, service.on_vehicle_battery_changed)

    # Inject service into router and mount
    set_service(service)
    app.include_router(router)
