from datetime import timedelta
from typing import Any

from charging.service import ChargingQueueService
from core.facade import CoreFacade
from core.providers import ChargingDemand, ProviderPort, ScheduledChargingSessionRow
from core.result import Result


class _ChargingDemandProvider(ChargingDemand):
    """Adapter exposing M3 scheduled charging demand over D-020 provider port."""

    def __init__(self, service: ChargingQueueService) -> None:
        self._service = service

    def scheduled_sessions(
        self, hub_id: str, horizon: timedelta
    ) -> Result[list[ScheduledChargingSessionRow]]:
        return self._service.get_scheduled_sessions(hub_id, horizon)


def install(core: CoreFacade, app: Any = None) -> ChargingQueueService:
    """Register M3 tables and ChargingDemand provider with Core (D-013, D-020)."""
    service = ChargingQueueService(core)
    core.register_provider(ProviderPort.CHARGING_DEMAND, _ChargingDemandProvider(service))
    if app is not None and hasattr(app, "state"):
        app.state.charging = service
    return service


__all__ = ["ChargingQueueService", "install"]
