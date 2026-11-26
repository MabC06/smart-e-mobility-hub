# NFR Evidence for `core`

> **Status:** v3 · **Owner:** M1; M8 results added 2026-11-23, rerun on `develop` 2026-11-26 · **Measured on:** `develop` at `686b4b0` (core tests), `0056f23` / `267919e` (timings, coverage), `01d68e7` (NFR-14 fresh-clone check)
> Which test proves which non-functional requirement (`docs/requirements/nfr.md`) for `core`. M8 uses this table in report section 5 and adds the timed results of NFR-01 to NFR-03 on 18/11 (D-024).

Run on 2026-11-16 (Windows 11, Python 3.12): `python -m pytest tests/core -q` → 1059 passed, 1 skipped. Line coverage of `core` 98.8 %.

**Status values**
- **Met:** the core tests below check the target, and they pass.
- **Core part met:** the part that `core` owns is met; the rest belongs to the module named in the last column.
- **Waiting for M8:** a measurement M8 has not yet completed (see `nfr-measurements.md`).

## 1. Evidence table

| NFR | Target (short) | Evidence in `tests/core/` (main tests) | Result | Status | Rest owned by |
|---|---|---|---|---|---|
| NFR-01 | A read after an accepted update shows it (API ≤ 1 s p95; UI ≤ 5 s) | `test_unit_of_work.py`: `test_commit_applies_everything_and_publishes_after_the_commit`; `test_repository_contract.py` (reads return the committed state, on both stores) | Pass; timed on `develop` (`267919e`): p95 7.2–8.1 ms, 100/100 visible (`nfr-measurements.md`) | Met (API) | M7 (UI refresh) |
| NFR-02 | Reads p95 ≤ 500 ms, max ≤ 2 s, 100 sequential requests on DS-STD | `tests/performance/measure_nfr02_03.py` | p95 5.8–20.9 ms, max ≤ 98.9 ms, 4 endpoints, `develop` (`267919e`) | Met (4 measured endpoints) | — |
| NFR-03 | Writes p95 ≤ 1 s, 100 sequential operations on DS-STD | `tests/performance/measure_nfr02_03.py` | p95 231.4 ms, 100/100 OK, `develop` (`267919e`); includes binding the Hub's queue (TC-M3-039) | Met (measured operation) | — |
| NFR-06 | 20 to 50 simultaneous requests for one resource: exactly one wins; 0 violations in 100 runs | `test_concurrency.py`: 50 threads per run; `test_only_one_of_many_overlapping_claims_succeeds`, `test_only_one_of_many_transitions_with_the_same_version_succeeds`, `test_many_returns_never_exceed_the_hub_capacity` | 10 runs in the suite; **100 runs on 2026-11-16: 402 passed, 0 violations** (see 2.1) | Met | — |
| NFR-07 | Capacity and uniqueness invariants always hold | `test_invariants.py`: one test per rule (capacity, bays, one vehicle per space, one session per point, claims), and `test_random_commands_never_break_an_invariant` (24 seeds, up to 250 random commands each, on both stores) | Pass | Met | Modules call the checker after their own tests |
| NFR-08 | Every disallowed transition rejected with a code, state unchanged; every pair of the Vehicle state machine tested | `test_state_machine.py`: `test_counts_match_the_design_document`, `test_every_valid_transition_is_applied`, `test_every_invalid_pair_is_rejected_and_changes_nothing` (171 cases) | Pass | Met | Other state machines: their module |
| NFR-09 | Pick-up fully applies or fully rolls back; 0 partial states after fault injection | `test_unit_of_work.py`: `test_pickup_is_all_or_nothing_under_fault_injection`, `test_a_failure_halfway_through_a_command_leaves_no_partial_change`, `test_a_storage_failure_halfway_leaves_no_partial_change` | Pass | Met | — |
| NFR-10 | A malformed sensor event is rejected and logged, no state change, no crash; a charging-point failure interrupts sessions and opens an incident within 5 s | `test_sensor_events.py`: `test_a_bad_event_is_rejected_without_any_change_and_is_announced`, `test_a_rejection_is_logged_as_a_warning`, `test_a_garbage_feed_never_crashes_or_breaks_a_rule`, `test_a_charger_fault_takes_the_point_out_of_service_and_a_clear_brings_it_back` | Pass | Core part met | M3 (interrupt sessions), M5 (incident within 5 s) |
| NFR-12 | A What-if run never changes the operational state | `test_snapshot.py`: `test_changing_the_snapshot_never_changes_the_store`, `test_a_loaded_snapshot_is_an_independent_store_that_follows_the_rules`; in `tests/simulation/`: `test_snapshot_isolation` (store version and reads unchanged after a run) | Pass; state unchanged after SC-01 to SC-05 in 3 rounds on `develop` (`267919e`) | Core part met; M6 part met for SC-01 only | M6 (SC-02 to SC-05 not implemented, DEV-08) |
| NFR-13 | Same seed and events give the same state hash and output | `test_snapshot.py`: `test_the_same_state_gives_the_same_id_whatever_the_history`, `test_the_snapshot_can_be_written_as_json_and_is_repeatable`; `test_network_loader.py`: `test_the_same_description_gives_the_same_network`, `test_the_reference_dataset_is_repeatable` | Pass; 5 runs per scenario identical, SC-01 to SC-05, 3 rounds on `develop` (`267919e`) | Core part met; M6 part met for SC-01 only | M6 (SC-02 to SC-05) |
| NFR-14 | Install, run and test from a clean clone in ≤ 15 min, ≤ 5 commands | Fresh clone (`fresh-nfr14` from local repo/worktree on 2026-11-23): 5 commands, total time 4m34s (274 s), `pytest` 1,501 passed, 1 skipped in 95.66 s, `ruff` & `mypy` clean, Uvicorn startup verified | Met (5 commands, 4m34s ≤ 15 min) | — |
| NFR-15 | A new Hub, space, charging point or vehicle needs data only, no code change | `test_network_loader.py`: networks of any size are loaded from a description (`test_a_network_is_loaded_with_deterministic_ids_and_summary`, `test_the_reference_dataset_loads_and_passes_its_sanity_checks`); `test_commands_misc.py`: `register_vehicle` tests | Pass | Met, with a gap (see 2.2) | — |
| NFR-16 | Every API except login needs a token; operator-only operations give 403 to a student; every endpoint has an authorization test | `test_api.py`: `test_each_endpoint_gives_the_right_status_to_each_kind_of_caller`, `test_no_endpoint_is_missing_from_the_authorization_matrix`; `test_api_security.py` (the checks module routers import, D-023) | Pass | Core part met | M2–M5, M7 (their own routers) |
| NFR-17 | Passwords salted and hashed; 0 secrets in the repository | `test_auth.py`: `test_a_hash_is_salted_and_never_contains_the_password`, `test_there_is_no_default_secret`, `test_the_token_does_not_contain_the_password_or_its_hash`; `.gitignore` ignores `.env` and `.env.*` | Pass | Core part met | M1 to confirm secret scanning is on in the GitHub settings |
| NFR-18 | Invalid input gives a 4xx with a message, never a 5xx | `test_api.py`: `test_bad_filter_values_are_400s_never_500s`, `test_a_malformed_login_is_a_400_with_a_message`, `test_a_body_that_is_not_an_object_is_a_400`; `test_entities_config_clock.py` (entity validation) | Pass | Core part met | Each module for its own endpoints |
| NFR-22 | 0 imports of another module's internals | `test_import_boundaries.py`: `test_no_package_breaks_the_import_rules`, and tests that the checker flags what it should (`test_the_checker_flags_what_the_rules_forbid`) | Pass; runs in CI on every PR | Met | — |
| NFR-24 | Line coverage `core` ≥ 70 % | CI step "Coverage per module (NFR-24)" (D-025) | `core` 98.8 % on `develop` `0056f23`; other modules 87.3–99.0 %; CI run `45666388041` success | Met | — |
| NFR-25 | Every state transition logged with UTC time, entity, previous and new state, trigger, actor; operators can read one entity's log | `test_commands_transition.py`: `test_pickup_writes_a_log_entry_for_the_vehicle_and_the_space`, `test_a_disallowed_pair_is_rejected_and_not_logged`; `test_api.py`: `test_the_state_log_is_newest_first_and_can_be_limited` | Pass | Met | — |

NFRs with no `core` part, left to their owners: NFR-04 (M3, M4), NFR-05 (M6), NFR-20 and NFR-21 (M7; the error body of NFR-21 is checked in `test_api.py`), NFR-26 (M8). NFR-11, 19, 23 and 27 are withdrawn.

## 2. Notes

### 2.1 NFR-06 with 100 runs

The suite runs each concurrency test 10 times so that it stays fast (`REPEATS = 10` in `test_concurrency.py`). For the evidence it was run once with `REPEATS = 100` on 2026-11-16: 402 passed (two tests × 100 runs × two stores, plus the capacity test on both stores), 0 violations, 38 s. To repeat it, change `REPEATS` to 100 locally, run `python -m pytest tests/core/test_concurrency.py -q` and do not commit the change.

### 2.2 NFR-15 gap

The size of the network comes only from data: `load_network` reads a description, and DS-STD (10 Hubs) and the small test networks use the same code. There is no command to add a Hub to a network that is already loaded; a new Hub means loading a new description into an empty store. This is a limitation for report section 4.4, not a failed test.

### 2.3 What M8 added on 2026-11-23

- NFR-01, NFR-02, NFR-03: p95 and max from the timed tests on DS-STD (D-024), with the commit they ran on.
- NFR-14: completed on 2026-11-23 in `fresh-nfr14` (5 commands, 4m34s total, `pytest` 1,501 passed, 1 skipped in 95.66 s, `ruff` & `mypy` clean, Uvicorn startup verified). Full figures and limits: `nfr-measurements.md`.