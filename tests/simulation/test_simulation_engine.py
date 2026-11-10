import unittest

from simulation.engine import SimulationEngine
from simulation.models import DemandSurgeParams, ScenarioType, SimulationConfig
from simulation.snapshot import (
    IsolatedSandboxState,
    SimulatedHub,
    SimulatedVehicle,
)


class TestSimulationEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.sandbox = IsolatedSandboxState(snapshot_id="SNAP_TEST_42", taken_at=None)

        self.sandbox.hubs["H01"] = SimulatedHub(
            hub_id="H01", name="KTX Khu B", parking_capacity=40, occupied=2
        )
        for i in range(2):
            v = SimulatedVehicle(
                vehicle_id=f"V_H01_{i}",
                hub_id="H01",
                vehicle_type="E_BIKE",
                state="AVAILABLE",
                battery_pct=90.0,
                soc=0.9,
            )
            self.sandbox.vehicles[v.vehicle_id] = v
            self.sandbox.hubs["H01"].vehicles.append(v)

        self.sandbox.hubs["H02"] = SimulatedHub(
            hub_id="H02", name="Ga Metro DHQG", parking_capacity=50, occupied=18
        )
        for i in range(18):
            v = SimulatedVehicle(
                vehicle_id=f"V_H02_{i}",
                hub_id="H02",
                vehicle_type="E_BIKE",
                state="AVAILABLE",
                battery_pct=85.0,
                soc=0.85,
            )
            self.sandbox.vehicles[v.vehicle_id] = v
            self.sandbox.hubs["H02"].vehicles.append(v)

    def test_scenario_1_demand_surge_execution(self) -> None:
        config = SimulationConfig(
            simulation_id="SIM_SURGE_001",
            scenario_id=ScenarioType.DEMAND_SURGE,
            parameters=DemandSurgeParams(
                target_hub_ids=["H01"],
                surge_multiplier=2.5,
                duration_minutes=60,
            ),
        )

        engine = SimulationEngine(config, self.sandbox)
        report = engine.run_demand_surge()

        h01_metric = next(m for m in report.hub_metrics if m.hub_id == "H01")
        self.assertGreater(h01_metric.unmet_requests, 0)
        self.assertGreater(h01_metric.shortage_rate_pct, 0.0)

        self.assertGreater(len(report.recommendations), 0)
        rec = report.recommendations[0]
        self.assertEqual(rec["recommendation_type"], "VEHICLE_REDISTRIBUTION")
        self.assertEqual(rec["source_hub_id"], "H02")
        self.assertEqual(rec["destination_hub_id"], "H01")
        self.assertIn("batch_size", rec)
        self.assertTrue(5 <= int(rec["batch_size"]) <= 20)


if __name__ == "__main__":
    unittest.main()