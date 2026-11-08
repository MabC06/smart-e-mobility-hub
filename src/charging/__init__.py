from typing import List, Dict, Any
from src.charging.service import ChargingQueueService
from core.providers import ProviderPort
from core.result import Ok, Err
from core.errors import ErrorCode

# 1. Initialize the main M3 service
charging_service = ChargingQueueService()


class ChargingDemandProvider:
    """Provider implementation for the CHARGING_DEMAND port."""

    def __init__(self, service: ChargingQueueService) -> None:
        self.service = service

    def get_pending_demand(self) -> Result[List[Dict[str, Any]]]:
        """Provide pending charging demands to other modules (e.g., M4) via Core."""
        try:
            demands = self.service.get_pending_requests()
            return Ok(demands)
        except Exception as e:
            return Err(ErrorCode.INTERNAL_ERROR, str(e))


charging_provider = ChargingDemandProvider(charging_service)


def install(core: Any, app: Any) -> None:
    """
    Install Module M3 into the system core and app (D-013).
    """
    # Register entity with the Core state manager (D-018)
    if hasattr(core, "register_entity"):
        core.register_entity("charging_requests", ChargingQueueService)

    # Register M3 Provider into the central Core ProviderRegistry (D-020)
    if hasattr(core, "providers") and hasattr(core.providers, "register"):
        core.providers.register(ProviderPort.CHARGING_DEMAND, charging_provider)

    # Attach service to app state if available
    if hasattr(app, "state"):
        app.state.charging_service = charging_service
