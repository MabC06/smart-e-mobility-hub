from core.facade import CoreFacade
from simulation.engine import SimulationEngine
from simulation.models import SimulationConfig, SimulationReport


class SimulationService:
    def __init__(self, core: CoreFacade) -> None:
        self.core = core

    def run_simulation(self, config: SimulationConfig) -> SimulationReport:
        snapshot = self.core.snapshots.export_snapshot()
        sandbox_core = CoreFacade(snapshot.to_repository())

        # The engine reads the sandbox through Core queries and reports the snapshot it ran on.
        engine = SimulationEngine(config, sandbox_core, snapshot)
        return engine.run_demand_surge()
