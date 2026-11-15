from core.facade import CoreFacade
from simulation.engine import SimulationEngine
from simulation.models import SimulationConfig, SimulationReport


class SimulationService:
    def __init__(self, core: object) -> None:
        self.core = core

    def run_simulation(self, config: SimulationConfig) -> SimulationReport:
        snapshot = self.core.snapshots.export_snapshot()
        sandbox_core = CoreFacade(snapshot.to_repository())

        # Truyền cả sandbox_core và snapshot vào engine theo mục 1 của MabC06
        engine = SimulationEngine(config, sandbox_core, snapshot)
        return engine.run_demand_surge()
