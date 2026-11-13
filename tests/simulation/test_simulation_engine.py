import unittest
from unittest.mock import MagicMock

from simulation.engine import SimulationEngine
from simulation.models import (
    DemandSurgeParams,
    ScenarioType,
    SimulationConfig,
)
from simulation.service import SimulationService


class TestSimulationEngineAndService(unittest.TestCase):
    def setUp(self) -> None:
        # Giả lập sandbox core theo đúng spec của MabC06 (M6-12)
        self.mock_sandbox = MagicMock()

        # Mock metadata snapshot
        mock_meta = MagicMock()
        mock_meta.snapshot_id = "SNAP_TEST_42"
        mock_meta.taken_at = "2026-11-13T20:00:00Z"
        self.mock_sandbox.snapshots.get_metadata.return_value = mock_meta

        # Mock danh sách Hubs
        mock_hub_1 = MagicMock()
        mock_hub_1.id = "H01"
        mock_hub_2 = MagicMock()
        mock_hub_2.id = "H02"
        self.mock_sandbox.queries.list_hubs.return_value = [mock_hub_1, mock_hub_2]

        # Mock danh sách Xe của từng Hub
        def mock_find_vehicles(hub_id: str):
            vehicles = []
            count = 2 if hub_id == "H01" else 10
            for i in range(count):
                v = MagicMock()
                v.state = "AVAILABLE"
                v.soc = 0.9
                vehicles.append(v)
            return vehicles

        self.mock_sandbox.queries.find_vehicles.side_effect = mock_find_vehicles

    def test_run_demand_surge_engine(self) -> None:
        config = SimulationConfig(
            simulation_id="SIM_SURGE_001",
            scenario_id=ScenarioType.DEMAND_SURGE,
            parameters=DemandSurgeParams(
                target_hub_ids=["H01"],
                surge_multiplier=2.5,
                duration_minutes=60,
            ),
        )

        engine = SimulationEngine(config, self.mock_sandbox)
        report = engine.run_demand_surge()

        self.assertEqual(report.simulation_id, "SIM_SURGE_001")
        self.assertEqual(report.snapshot_id, "SNAP_TEST_42")
        self.assertGreater(len(report.hub_metrics), 0)

    def test_simulation_service_integration(self) -> None:
        mock_core = MagicMock()
        mock_core.snapshots.export_snapshot.return_value.to_repository.return_value = (
            self.mock_sandbox
        )

        service = SimulationService(mock_core)
        config = SimulationConfig(
            simulation_id="SIM_SURGE_002",
            scenario_id=ScenarioType.DEMAND_SURGE,
            parameters=DemandSurgeParams(
                target_hub_ids=["H01"],
                surge_multiplier=2.0,
                duration_minutes=30,
            ),
        )

        report = service.run_simulation(config)
        self.assertEqual(report.simulation_id, "SIM_SURGE_002")


if __name__ == "__main__":
    unittest.main()
