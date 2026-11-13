import unittest
from datetime import UTC, datetime

from core.snapshots import Snapshot

from core.facade import CoreFacade
from simulation.models import (
    DemandSurgeParams,
    ScenarioType,
    SimulationConfig,
)
from simulation.service import SimulationService


class TestSimulationService(unittest.TestCase):
    def setUp(self) -> None:
        # Mock hoặc khởi tạo CoreFacade sandbox cho test
        self.snapshot = Snapshot(
            snapshot_id="SNAP_TEST_42",
            taken_at=datetime.now(UTC),
        )
        self.core = CoreFacade(self.snapshot.to_repository())
        self.service = SimulationService(self.core)

    def test_run_simulation_integration(self) -> None:
        config = SimulationConfig(
            simulation_id="SIM_SURGE_001",
            scenario_id=ScenarioType.DEMAND_SURGE,
            parameters=DemandSurgeParams(
                target_hub_ids=["H01"],
                surge_multiplier=2.5,
                duration_minutes=60,
            ),
        )

        report = self.service.run_simulation(config)
        self.assertEqual(report.simulation_id, "SIM_SURGE_001")
        self.assertEqual(report.snapshot_id, "SNAP_TEST_42")


if __name__ == "__main__":
    unittest.main()
