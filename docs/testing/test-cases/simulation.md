# Test Cases: Module M6 — What-if Simulation

| Test Case ID | Test Name | Verifies | Technique | Summary |
|---|---|---|---|---|
| TC-M6-001 | test_a_surge_target_is_never_chosen_as_donor | FR-12 | Equivalence Partitioning (EP) | Verify that hubs targeted for demand surge are strictly excluded from donor hub selection. |
| TC-M6-002 | test_run_demand_surge_integration | FR-12 | State Transition | Verify execution of SC-01 demand surge scenario, deterministic metrics calculation, and recommendation generation. |
| TC-M6-003 | test_snapshot_isolation | NFR-12 | Boundary Value Analysis (BVA) | Verify in-memory repository version and core operational state remain untouched during simulation runs. |
| TC-M6-004 | test_nfr12_state_isolation | NFR-12 | State Transition | Verify zero writes to live core and state hash remains identical before and after simulation execution. |
| TC-M6-005 | test_nfr13_reproducibility | NFR-13 | Equivalence Partitioning (EP) | Verify identical random seed and simulation parameters produce 100% identical report outputs. |