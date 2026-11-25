from fastapi import FastAPI

from core.facade import CoreFacade
from simulation.router import router as simulation_router
from simulation.router import set_simulation_service
from simulation.service import SimulationService


def install(core: CoreFacade, app: FastAPI) -> None:
    """Register simulation service and endpoints into core & app."""
    service = SimulationService(core)

    set_simulation_service(service)

    if hasattr(app, "state"):
        app.state.simulation_service = service

    app.include_router(simulation_router)
