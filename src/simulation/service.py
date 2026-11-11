from src.simulation.engine import SimulationEngine
from src.simulation.models import SimulationConfig, SimulationReport
from src.simulation.snapshot import SnapshotAdapter


class SimulationService:
    def __init__(self, core_facade: object) -> None:
        self.core = core_facade

    def run_simulation(self, config: SimulationConfig) -> SimulationReport:
        if not hasattr(self.core, "snapshots"):
            raise RuntimeError("Core facade does not provide 'snapshots' module.")

        core_snap = self.core.snapshots.export_snapshot()
        sandbox = SnapshotAdapter.from_core_snapshot(core_snap)

        engine = SimulationEngine(config, sandbox)
        return engine.run_demand_surge()
