# Test Cases: Module M6 — What-if Simulation

| Test Case ID | Test Name | Verifies | Technique | Summary |
|---|---|---|---|---|
| TC-M6-001 | test_simulation_engine_initialization | FR-12 | Unit | Verify that SimulationEngine correctly initializes state from snapshot. |
| TC-M6-002 | test_run_simulation_demand_surge | FR-12 | Integration | Verify execution of SC-01 (Demand Surge) scenario and recommendation generation. |
| TC-M6-003 | test_simulation_invalid_config | FR-12 | Negative | Verify error handling when invalid parameters are provided to simulation engine. |
| TC-M6-004 | test_nfr12_state_isolation | NFR-12 | Integration | Verify zero writes to live core state and state immutability during simulation. |
| TC-M6-005 | test_nfr13_reproducibility | NFR-13 | Integration | Verify identical random seed and inputs produce identical simulation output. |