from core.facade import CoreFacade
from simulation.service import SimulationService


def install(core: CoreFacade, app: object) -> None:
    """Register simulation service and endpoints into core & app."""
    service = SimulationService(core)
    if hasattr(app, "state"):
        app.state.simulation_service = service
