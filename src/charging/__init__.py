from typing import Any

from src.charging.service import ChargingQueueService

from core.errors import ErrorCode
from core.providers import ProviderPort as ProviderPort
from core.result import Err, Ok, Result

__all__ = [
    "ChargingDemandProvider",
    "ChargingQueueService",
    "ProviderPort",
]


class ChargingDemandProvider:
    """Provider adapter for Module M3 Charging Demand."""

    def __init__(self, service: ChargingQueueService) -> None:
        self.service = service

    def get_pending_demand(self) -> Result[list[dict[str, Any]]]:
        """Provide pending charging demands to other modules (e.g., M4) via Core."""
        try:
            pending = self.service.get_pending_requests()
            return Ok(pending)
        except Exception as e:
            return Err(ErrorCode.INTERNAL_ERROR, str(e))
