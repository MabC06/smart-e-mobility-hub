"""Resource Allocation & Vehicle Dispatching module (M4).

Implements FR-10 and FR-11 (allocation side), UC-M4-01 through UC-M4-09,
business rules BR-M4-01 through BR-M4-06, BR-M4-08, BR-M4-10, and D-020 provider ports.
"""

from fastapi import FastAPI

from core.facade import CoreFacade
from core.providers import ProviderPort

from .alternatives import AlternativeChargingService, AlternativeHubService
from .arbitration import ContenderRequest, RequestClass, settle_competing_requests
from .config import AllocationConfig, default_config
from .models import DISPATCH_TASK_SPEC, DispatchTask, DispatchTaskStatus
from .planner import HubDemandInfo, HubStateView, HubVehicleInfo, plan_redistribution
from .router import create_allocation_router
from .service import AllocationService


def install(core: CoreFacade, app: FastAPI) -> None:
    """Module install contract called by src/main.py (composition root).

    1. Registers DispatchTask table with core's metadata (D-018).
    2. Registers provider ports: ALTERNATIVE_HUB and ALTERNATIVE_CHARGING (D-020).
    3. Mounts the REST API router under /allocation.
    """
    # 1. Register entity in core transaction schema
    core.register_entity(DISPATCH_TASK_SPEC)

    # 2. Instantiate services and providers
    config = default_config()
    service = AllocationService(core, config)
    alt_hub_service = AlternativeHubService(core, config)
    alt_charging_service = AlternativeChargingService(core, config)

    # 3. Register provider ports for other modules (D-020)
    core.register_provider(ProviderPort.ALTERNATIVE_HUB, alt_hub_service)
    core.register_provider(ProviderPort.ALTERNATIVE_CHARGING, alt_charging_service)

    # 4. Mount API router
    router = create_allocation_router(service, alt_hub_service, alt_charging_service)
    app.include_router(router, prefix="/allocation", tags=["allocation"])


__all__ = [
    "install",
    "AllocationConfig",
    "AllocationService",
    "AlternativeHubService",
    "AlternativeChargingService",
    "ContenderRequest",
    "DispatchTask",
    "DispatchTaskStatus",
    "HubDemandInfo",
    "HubStateView",
    "HubVehicleInfo",
    "RequestClass",
    "plan_redistribution",
    "settle_competing_requests",
]
