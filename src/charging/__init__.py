from datetime import datetime
from typing import Any

from charging.service import ChargingQueueService
from core.errors import ErrorCode
from core.providers import ProviderPort, ScheduledChargingSessionRow
from core.result import Err, Ok, Result

__all__ = [
    "ChargingDemandProvider",
    "ChargingQueueService",
    "ProviderPort",
    "install",
]


class ChargingDemandProvider:
    """Provider adapter for Module M3 Charging Demand (D-020)."""

    def __init__(self, service: ChargingQueueService) -> None:
        self.service = service

    def scheduled_sessions(
        self, hub_id: str, horizon: datetime
    ) -> Result[list[ScheduledChargingSessionRow]]:
        """Expose scheduled charging sessions to other modules via Core (D-020)."""
        try:
            requests = self.service.get_scheduled_sessions(hub_id, horizon)
            rows = [
                ScheduledChargingSessionRow(
                    session_id=str(r.request_id),
                    vehicle_id=str(r.vehicle_id),
                    charger_id=str(getattr(r, "charger_id", "default_charger")),
                    energy_kwh=float(getattr(r, "target_soc", 100.0) - r.current_soc),
                    start_time=r.requested_at,
                    end_time=r.requested_at,
                )
                for r in requests
            ]
            return Ok(rows)
        except Exception as e:
            return Err(ErrorCode.INTERNAL_ERROR, str(e))


def install(core: Any, app: Any) -> None:
    service = ChargingQueueService(core=core)
    provider = ChargingDemandProvider(service)
    core.register_provider(ProviderPort.CHARGING_DEMAND, provider)
