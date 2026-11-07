"""Entrypoint service for Simulation Module (M6).

Traces: FR-12, core-api-spec.md Section 7
"""

from typing import Any
from .engine import SimulationEngine
from .models import SimulationConfig, SimulationReport
from .snapshot import IsolatedSandboxState, SnapshotAdapter


class SimulationService:
    def __init__(self, core_facade: Any = None):
        self.core = core_facade

    def run_simulation(self, config: SimulationConfig) -> SimulationReport:
        if self.core and hasattr(self.core, "snapshots"):
            core_snap = self.core.snapshots.export_snapshot()
            sandbox = SnapshotAdapter.from_core_snapshot(core_snap)
        elif self.core and hasattr(self.core, "export_snapshot"):
            core_snap = self.core.export_snapshot()
            sandbox = SnapshotAdapter.from_core_snapshot(core_snap)
        else:
            sandbox = IsolatedSandboxState(snapshot_id="SNAP_DEFAULT_SANDBOX", taken_at=None)

        engine = SimulationEngine(config, sandbox)
        return engine.run_demand_surge()