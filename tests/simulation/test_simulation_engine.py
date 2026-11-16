import unittest
from datetime import UTC, datetime

from core.clock import FixedClock
from core.domain.entities import Hub, Vehicle
from core.domain.enums import Ownership, VehicleState, VehicleType
from core.facade import CoreFacade
from core.repository.memory import InMemoryRepository
from simulation.models import (
    DemandSurgeParams,
    ScenarioType,
    SimulationConfig,
)
from simulation.service import SimulationService


class TestSimulationEngineIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = InMemoryRepository()
        self.clock = FixedClock(datetime(2026, 11, 13, 20, 0, 0, tzinfo=UTC))

        # Create two hubs with deterministic IDs.
        hub1 = Hub(
            hub_id="H01",
            name="Hub 1",
            zone_code="ZONE_01",
            parking_capacity=20,
            charging_point_count=0,
        )

        hub2 = Hub(
            hub_id="H02",
            name="Hub 2",
            zone_code="ZONE_01",
            parking_capacity=20,
            charging_point_count=0,
        )

        self.repo.add(hub1)
        self.repo.add(hub2)

        # H01 has 2 available fleet vehicles.
        self._add_vehicles("H01", 2)

        # H02 has 10 available fleet vehicles.
        self._add_vehicles("H02", 10)

        self.core = CoreFacade(self.repo, clock=self.clock)
        self.service = SimulationService(self.core)

    def _add_vehicles(self, hub_id: str, count: int) -> None:
        for i in range(count):
            vehicle = Vehicle(
                vehicle_id=f"V_{hub_id}_{i:02d}",
                plate_or_code=f"CODE_{hub_id}_{i:02d}",
                ownership=Ownership.FLEET,
                vehicle_type=VehicleType.E_BIKE,
                battery_pct=90.0,
                battery_capacity_kwh=1.5,
                state=VehicleState.AVAILABLE,
                hub_id=hub_id,
            )
            self.repo.add(vehicle)

    def _create_config(self) -> SimulationConfig:
        return SimulationConfig(
            simulation_id="SIM_SURGE_TEST",
            scenario_id=ScenarioType.DEMAND_SURGE,
            parameters=DemandSurgeParams(
                target_hub_ids=["H01"],
                surge_multiplier=2.5,
                duration_minutes=60,
            ),
        )

    def test_a_surge_target_is_never_chosen_as_donor(self) -> None:
        # H02 is short too when it is a target; only H03 may give vehicles.
        self.repo.add(
            Hub(
                hub_id="H03",
                name="Hub 3",
                zone_code="ZONE_01",
                parking_capacity=20,
                charging_point_count=0,
            )
        )
        self._add_vehicles("H03", 8)
        config = SimulationConfig(
            simulation_id="SIM_TWO_TARGETS",
            scenario_id=ScenarioType.DEMAND_SURGE,
            parameters=DemandSurgeParams(
                target_hub_ids=["H01", "H02"],
                surge_multiplier=2.5,
                duration_minutes=60,
            ),
        )

        report = self.service.run_simulation(config)

        self.assertEqual(len(report.recommendations), 2)
        for rec in report.recommendations:
            self.assertEqual(rec["source_hub_id"], "H03")

    def test_run_demand_surge_integration(self) -> None:
        config = self._create_config()

        # Capture the original Core state.
        hubs_before = self.core.queries.list_hubs()
        vehicles_before = self.core.queries.find_vehicles()

        # Run the same simulation twice.
        report1 = self.service.run_simulation(config)
        report2 = self.service.run_simulation(config)

        # Verify simulation identity.
        self.assertEqual(report1.simulation_id, "SIM_SURGE_TEST")
        self.assertEqual(report1.scenario_id, ScenarioType.DEMAND_SURGE.value)

        # Verify deterministic results.
        self.assertEqual(report1, report2)
        self.assertEqual(report1.snapshot_id, report2.snapshot_id)

        # Verify shortage metrics.
        self.assertGreater(len(report1.hub_metrics), 0)

        # Verify vehicle redistribution recommendation.
        self.assertGreater(len(report1.recommendations), 0)

        rec = report1.recommendations[0]

        self.assertEqual(
            rec["recommendation_type"],
            "VEHICLE_REDISTRIBUTION",
        )
        self.assertEqual(rec["source_hub_id"], "H02")
        self.assertEqual(rec["destination_hub_id"], "H01")
        self.assertGreaterEqual(rec["batch_size"], 5)
        self.assertLessEqual(rec["batch_size"], 20)

        # Verify that simulation does not modify the live Core state.
        hubs_after = self.core.queries.list_hubs()
        vehicles_after = self.core.queries.find_vehicles()

        self.assertEqual(hubs_before, hubs_after)
        self.assertEqual(vehicles_before, vehicles_after)

    def test_snapshot_isolation(self) -> None:
        config = self._create_config()

        original_version = self.repo.version()
        original_hubs = self.core.queries.list_hubs()
        original_vehicles = self.core.queries.find_vehicles()

        self.service.run_simulation(config)

        # Simulation must not change the original repository.
        self.assertEqual(self.repo.version(), original_version)
        self.assertEqual(self.core.queries.list_hubs(), original_hubs)
        self.assertEqual(self.core.queries.find_vehicles(), original_vehicles)

    def test_nfr12_state_isolation(simulation_service):
        """NFR-12: Ensure 0 writes to live core and state hash remains unchanged."""
        initial_snapshot = simulation_service.core.snapshots.export_snapshot()
        initial_dict = initial_snapshot.to_dict()

        config = {
            "simulation_id": "TEST_ISO_01",
            "scenario_id": "SCENARIO_01_DEMAND_SURGE",
            "time_horizon_minutes": 60,
            "time_step_minutes": 5,
            "random_seed": 42,
            "parameters": {"surge_multiplier": 2.0},
        }
        simulation_service.run_simulation(config)

        final_snapshot = simulation_service.core.snapshots.export_snapshot()
        assert final_snapshot.to_dict() == initial_dict

    def test_nfr13_reproducibility(simulation_service):
        """NFR-13: Identical seed and inputs produce identical output."""
        config = {
            "simulation_id": "TEST_REP_01",
            "scenario_id": "SCENARIO_01_DEMAND_SURGE",
            "time_horizon_minutes": 60,
            "time_step_minutes": 5,
            "random_seed": 12345,
            "parameters": {"surge_multiplier": 1.5},
        }

        report_1 = simulation_service.run_simulation(config)
        report_2 = simulation_service.run_simulation(config)

        assert report_1.baseline_shortage_rate_pct == report_2.baseline_shortage_rate_pct
        assert len(report_1.recommendations) == len(report_2.recommendations)


if __name__ == "__main__":
    unittest.main()
