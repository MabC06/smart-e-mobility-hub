from core.facade import CoreFacade
from simulation.engine import SimulationEngine
from simulation.models import SimulationConfig, SimulationReport


class SimulationService:
    def __init__(self, core: object) -> None:
        self.core = core

    def run_simulation(self, config: SimulationConfig) -> SimulationReport:
        if not hasattr(self.core, "snapshots"):
            raise RuntimeError("Core facade does not provide 'snapshots' module.")

        # Lấy isolated sandbox chuẩn từ CoreFacade theo yêu cầu M6-11
        snapshot = self.core.snapshots.export_snapshot()
        sandbox_core = CoreFacade(snapshot.to_repository())

        engine = SimulationEngine(config, sandbox_core)
        return engine.run_demand_surge()
