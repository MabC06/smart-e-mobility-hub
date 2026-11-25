# Test Cases: Module M6 — What-if Simulation

| Test Case ID | Test Name | Verifies | Technique | Summary |
|---|---|---|---|---|
| TC-M6-001 | test_a_surge_target_is_never_chosen_as_donor | FR-12 | Equivalence Partitioning (EP) | Verify that hubs targeted for demand surge are strictly excluded from donor hub selection. |
| TC-M6-002 | test_run_demand_surge_integration | FR-12 | State Transition | Verify execution of SC-01 demand surge scenario, deterministic metrics calculation, and recommendation generation. |
| TC-M6-003 | test_snapshot_isolation | NFR-12 | Boundary Value Analysis (BVA) | Verify in-memory repository version and core operational state remain untouched during simulation runs. |
| TC-M6-004 | test_nfr12_state_isolation | NFR-12 | State Transition | Verify zero writes to live core and state hash remains identical before and after simulation execution. |
| TC-M6-005 | test_nfr13_reproducibility | NFR-13 | Equivalence Partitioning (EP) | Verify identical random seed and simulation parameters produce 100% identical report outputs. |
| TC-M6-006 | test_hub_at_capacity_sends_returns_to_the_hub_with_most_space | FR-12, UC-M6-01 | Equivalence Partitioning (EP) | SC-02: 36 returns at a Hub with 1 free space leave 35 unmet; the ALTERNATIVE_RETURN_HUB recommendation sends 10 to the Hub with most space, so 25 remain in the mitigated plan; the live state does not change. |
| TC-M6-007 | test_charging_surge_shifts_drained_vehicles_to_spare_chargers | FR-12, UC-M6-01 | Equivalence Partitioning (EP) | SC-03: 5 drained vehicles for 2 points over 60 min leave 3 unmet; a CHARGING_SHIFT of 3 to a Hub with spare chargers gives 0 in the mitigated plan. |
| TC-M6-008 | test_charger_failure_lowers_capacity_for_the_repair_time | FR-12, UC-M6-01 | Boundary Value Analysis (BVA) | SC-04: both points of a Hub down for the whole horizon leave its 2 drained vehicles unserved; an unknown point is refused. |
| TC-M6-009 | test_imbalance_moves_a_batch_that_arrives_after_the_transit_delay | FR-12, BR-M6-03 | Boundary Value Analysis (BVA) | SC-05: a batch of 9 (limited by the shortage and the donor's 5 kept vehicles) counts 7 after 15 of 120 min in transit; a Hub cannot be both source and destination. |
| TC-M6-010 | test_every_standard_scenario_runs_through_the_route | FR-12, UC-M7-09, NFR-21 | Equivalence Partitioning (EP) | `POST /simulation/runs` returns 200 with baseline and mitigated rates for SC-01 to SC-05; an unknown Hub is 400 INVALID_INPUT. |

Execution record: 2026-11-25 (M1, branch `feat/backend-planned-gaps`), `python -m pytest -q tests/simulation --cov=simulation`: 18 passed, 92.18% (371 statements, 29 missed).
