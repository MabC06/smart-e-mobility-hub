"""Simulation Service Facade entrypoint.

Traces: FR-12.1
"""

from simulation.engine import SimulationEngine
from simulation.models import SimulationConfig, SimulationReport
from simulation.snapshot import SnapshotAdapter


class SimulationService:
    def __init__(self, core_facade: object):
        self.core = core_facade

    def run_simulation(self, config: SimulationConfig) -> SimulationReport:
        # M6-4: Direct call without silent fallback
        if not hasattr(self.core, "snapshots"):
            raise RuntimeError("Core facade does not provide 'snapshots' module.")

        core_snap = self.core.snapshots.export_snapshot()
        sandbox = SnapshotAdapter.from_core_snapshot(core_snap)

        engine = SimulationEngine(config, sandbox)
        return engine.run_demand_surge()