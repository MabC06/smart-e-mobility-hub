"""Unit tests for M6 Simulation Engine.

Traces: FR-12.2, FR-12.4, FR-12.5, NFR-12, NFR-13, UC-M6-01
"""

import unittest
from src.simulation.models import DemandSurgeParams, ScenarioType, SimulationConfig
from src.simulation.snapshot import IsolatedSandboxState, SimulatedHub, SimulatedVehicle
from src.simulation.engine import SimulationEngine


class TestSimulationEngine(unittest.TestCase):

    def setUp(self):
        self.sandbox = IsolatedSandboxState(snapshot_id="SNAP_TEST_42", taken_at=None)

        # Trạm H01: thiếu xe (2 xe)
        self.sandbox.hubs["H01"] = SimulatedHub(
            hub_id="H01", name="KTX Khu B", parking_capacity=40, occupied=2
        )
        for i in range(2):
            v = SimulatedVehicle(
                vehicle_id=f"V_H01_{i}", hub_id="H01", vehicle_type="E_BIKE",
                state="AVAILABLE", battery_pct=90.0, soc=0.9
            )
            self.sandbox.vehicles[v.vehicle_id] = v
            self.sandbox.hubs["H01"].vehicles.append(v)

        # Trạm H02: thừa xe (18 xe)
        self.sandbox.hubs["H02"] = SimulatedHub(
            hub_id="H02", name="Ga Metro DHQG", parking_capacity=50, occupied=18
        )
        for i in range(18):
            v = SimulatedVehicle(
                vehicle_id=f"V_H02_{i}", hub_id="H02", vehicle_type="E_BIKE",
                state="AVAILABLE", battery_pct=85.0, soc=0.85
            )
            self.sandbox.vehicles[v.vehicle_id] = v
            self.sandbox.hubs["H02"].vehicles.append(v)

    def test_scenario_1_demand_surge_execution(self):
        config = SimulationConfig(
            simulation_id="SIM_SURGE_001",
            scenario_id=ScenarioType.DEMAND_SURGE,
            parameters=DemandSurgeParams(
                target_hub_ids=["H01"],
                surge_multiplier=2.5,
                duration_minutes=60
            )
        )

        engine = SimulationEngine(config, self.sandbox)
        report = engine.run_demand_surge()

        # 1. Kiểm tra tính toán metrics
        h01_metric = next(m for m in report.hub_metrics if m.hub_id == "H01")
        self.assertGreater(h01_metric.unmet_requests, 0)
        self.assertGreater(h01_metric.shortage_rate_pct, 0.0)

        # 2. Kiểm tra khuyến nghị điều phối
        self.assertGreater(len(report.recommendations), 0)
        rec = report.recommendations[0]
        self.assertEqual(rec["recommendation_type"], "VEHICLE_REDISTRIBUTION")
        self.assertEqual(rec["source_hub_id"], "H02")
        self.assertEqual(rec["destination_hub_id"], "H01")
        self.assertIn("batch_size", rec)
        self.assertTrue(1 <= rec["batch_size"] <= 20)
        self.assertNotIn("truck", rec)


if __name__ == "__main__":
    unittest.main()