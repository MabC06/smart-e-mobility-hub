# Defect Log

> **Status:** template with the first entries · **Consolidated by:** M8 (`test-plan-v1.md` section 8) · **Started by:** M1, 2026-11-16
> Every member records the defects of their own module in their own block by 17/11 (`task-assignment-timeline.md`, Phase 4). M8 merges the summary into report section 5.4. A failed test is never changed to pass to close a defect (`test-plan-v1.md` section 8).

## 1. How to record a defect

1. Add **one row** to your module's table in section 3. Copy an existing row and change it.
2. Only for a **Critical** or **High** defect, or one with status **Accepted**, also add a short detail block under the table (steps, expected, actual, resolution), like DEF-M6-001. Medium and Low defects are one row only.
3. ID: `DEF-M<n>-###`, numbered per module, never reused (same rule as `TC-M<n>-###`, D-011).
4. Severity, from the scale below. If unsure, pick the higher one.
5. Status: `Open` → `Fixed` (fix merged) → `Closed` (retest passed). `Accepted` means it stays, with a reason; it then also goes into report section 4.4.
6. "Found by": a test case (`TC-...`), a PR review (with the review code), or integration.
7. Update your line in the summary table (section 2).

| Severity | Meaning | Example |
|---|---|---|
| Critical | Shared state becomes wrong or the system cannot run | Two reservations hold the same space |
| High | A required feature gives a wrong result | A recommendation moves vehicles out of a Hub that is itself short |
| Medium | A feature works but part of it is wrong or missing, with a workaround | A filter ignores one parameter |
| Low | Documentation, naming, typing or duplicated code; behaviour is right | A formula in the report does not render |

## 2. Summary (for report section 5.4)

| Module | Found | Critical | High | Medium | Low | Closed | Open / Accepted |
|---|---|---|---|---|---|---|---|
| M1 core | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| M2 reservation | 1 | 0 | 1 | 0 | 0 | 1 | 0 |
| M3 charging | 7 | 0 | 3 | 2 | 2 | 6 | 1 |
| M4 allocation | 5 | 0 | 0 | 3 | 2 | 5 | 0 |
| M5 monitoring | 2 | 0 | 0 | 1 | 1 | 2 | 0 |
| M6 simulation | 8 | 0 | 2 | 0 | 6 | 8 | 0 |
| **Total** | **23** | **0** | **6** | **6** | **11** | **22** | **1** |

The initial seven entries were found by reviewing PRs before or at merge (inspection) and fixed by M1 in PR #39, which merged into `develop` on 2026-11-15 (`686b4b0`). Retest for all of them: `python -m pytest -q` on `686b4b0`, 1393 passed, 1 skipped; ruff, format and mypy clean.

## 3. Defects by module

<!-- BEGIN M1: Core -->
### M1 Core

| ID | Title | Severity | Found by | Related IDs | Status | Resolution | Fix |
|---|---|---|---|---|---|---|---|
| — | No defect recorded yet | | | | | | |
<!-- END M1: Core -->

<!-- BEGIN M2: Reservation & Trip -->
### M2 Reservation & Trip

| ID | Title | Severity | Found by | Related IDs | Status | Resolution | Fix |
|---|---|---|---|---|---|---|---|
| DEF-M2-001 | Reopening SQLite could reuse persisted Core IDs and cause a valid pickup to fail | High | TC-M2-021 | D-022, FR-04, UC-M2-04, NFR-09 | Closed | The default Core generator resumes each prefix above the maximum persisted numeric suffix; injected generators retain their own behavior | PR #24, `e25578d`; D-022 released in PR #40 |

**DEF-M2-001** (High)
- Steps: create and reserve V1 on a file-backed SQLite store; close it;
  open a new facade on the same store; call pickup on the original booking.
- Expected: pickup succeeds with fresh shared record IDs and starts one Trip.
  Original failure: the reset default counters reused a stored ID, so a valid
  pickup could fail before commit.
- Resolution: seed the default generator from stored Core IDs. Retest with
  TC-M2-021 and `tests/core/test_id_recovery.py`: 6 passed on `bb5c622`
  on 2026-11-23. See [execution evidence](evidence/m2-validation-2026-11-23.json).
<!-- END M2: Reservation & Trip -->

<!-- BEGIN M3: Charging & Smart Scheduling -->
### M3 Charging & Smart Scheduling

<!-- M3 adds rows here by 17/11. -->

| ID | Title | Severity | Found by | Related IDs | Status | Resolution | Fix |
|---|---|---|---|---|---|---|---|
| DEF-M3-001 | Report section 3.3 (M3) listed session states (`AVAILABLE`, `PREPARING`, `SUSPENDED`, `FAULTED`) that the code does not have | Low | Review of the report at merge (M1) | UC-M3-08, BR-M3-02 | Closed | M3 block rewritten to match the code and `charging-session-state-machine.md` | PR #39, `deac134` |
| DEF-M3-002 | `optimize_queue` bound all requests in one unit of work; the second bind failed with `RuntimeError` and `/schedule/optimize` returned HTTP 500 | High | Review of PR #32 (M3-13) | FR-11.M3.2, UC-M3-07, TC-M3-024, TC-M3-025 | Closed | See below | PR #32, `31914f5` |
| DEF-M3-003 | `/queue` and `/demand` were open to students and `/sessions` returned other users' sessions | High | Review of PR #32 (M3-14) | NFR-16, TC-M3-031, TC-M3-032, TC-M3-033 | Closed | See below | PR #32 |
| DEF-M3-004 | Start-session, private-vehicle and optimize endpoints did not follow the agreed flow (start logic outside the service, owner not taken from the token) | Medium | Review of PR #32 (M3-15) | FR-06.2, FR-07.M3.1, UC-M3-02, UC-M3-04, TC-M3-008 to TC-M3-013, TC-M3-019, TC-M3-020 | Closed | `start_scheduled_session` moved into the service (owner/operator check, due-time check, Core `START_CHARGING` transition); owner of a private EV comes from the token | PR #32 |
| DEF-M3-005 | Claims column of the charging state-machine document did not match the code for `SCHEDULED` transitions | Low | Review of PR #28 (M3-12) | UC-M3-02, UC-M3-03 | Closed | Claims column and section 3 wording corrected | PR #28, `2925a23` |
| DEF-M3-006 | `from_core_error` named `ErrorCode.INVALID_STATE`, which core does not have, so every refused core command raised `AttributeError` and the charging route answered 500 instead of 400/409 | High | Integration, M7 (TC-M7-024) | FR-07.M3.1, UC-M3-04 | Closed | See below | PR #51 |
| DEF-M3-007 | `POST /charging/schedule/optimize` for one Hub takes more than 3 s when the queue holds 50 requests (NFR-04); within the limit at 15 queued per Hub (DS-STD load) | Medium | Integration, M8 (TC-M8-026, depth sweep) | NFR-04, FR-11.M3.2, UC-M3-07, TC-M8-026 | Accepted | See below | — |

**DEF-M3-002** (High)
- Steps: three `QUEUED` requests in a Hub with two bays, then `optimize_queue("H1")` or `POST /charging/schedule/optimize?hub_id=H1`.
- Expected: all three requests become `SCHEDULED`, no two overlap on one charging point. Actual: `_bind_bay` commits, a commit closes the unit of work, so the second bind raised `RuntimeError: the unit of work is not open`; only the first request was `SCHEDULED`, the endpoint returned 500 and the point-status handler stopped.
- Resolution: the priority queue is computed first, then each request is bound in its own unit of work (one `self._run` per request). Retest: `test_optimize_queue_binds_three_requests_on_two_bays_without_overlap` and `test_optimize_endpoint_binds_three_queued_requests` pass.

**DEF-M3-003** (High)
- Steps: log in as a student, call `GET /charging/queue`, `GET /charging/demand` and `GET /charging/sessions`.
- Expected: 403 on `/queue` and `/demand`; `/sessions` lists only the caller's sessions. Actual: students could read the queue and the demand, and `/sessions` returned other users' sessions.
- Resolution: `/queue`, `/demand` and `/schedule/optimize` use `require_operator`; `/sessions` filters by `user_id` for students. Retest: `test_student_gets_403_on_operator_endpoints_through_app` and `test_student_sees_only_own_sessions` pass.

**DEF-M3-006** (High)
- Steps: register a private EV with `POST /charging/private/vehicles`, then register another one with the same `plate_or_code` (TC-M7-024).
- Expected: core refuses the second one with `INVALID_INPUT` and the route answers 400. Actual: building the mapping in `from_core_error` (`src/charging/models.py`) read `ErrorCode.INVALID_STATE`, which does not exist, so the route raised `AttributeError` and answered 500. The same happened for every refused core command.
- Resolution: the mapping names only codes that exist in `core.errors.ErrorCode`, written directly instead of `getattr(..., None)`. Retest: `test_second_registration_of_same_plate_is_400_not_500` passes.

**DEF-M3-007** (Medium, Accepted)
- Steps: load DS-STD, queue 50 requests on one Hub (H01), then `POST /charging/schedule/optimize?hub_id=H01` (`tests/performance/measure_nfr01_04_05.py`, depth sweep).
- Expected: ≤ 3 s (NFR-04). Actual: 2.64, 2.67, 3.56 and 3.83 s in four recorded runs (2 of 4 over the limit; two earlier console runs 3.04 s and 3.10 s). At depth 5, 10, 15 and 30 the call takes 0.02 s, 0.04–0.07 s, 0.12–0.17 s and 0.67–0.94 s. Time per queued request grows from about 4 ms to 53–77 ms, so the growth is faster than linear. Measured on a local merge; to be repeated on `develop` (`nfr-measurements.md` section 2).
- Resolution: not fixed. Lead decision (2026-11-24): accepted as a known limitation because NFR-04 passes at the DS-STD load (15 queued per Hub, worst 1.50 s). M3 adds the limitation to report section 4.4 with its own part.
<!-- END M3: Charging & Smart Scheduling -->

<!-- BEGIN M4: Resource Allocation & Dispatching -->
### M4 Resource Allocation & Dispatching

<!-- M4 adds rows here by 17/11. -->

| ID | Title | Severity | Found by | Related IDs | Status | Resolution | Fix |
|---|---|---|---|---|---|---|---|
| DEF-M4-001 | `allocation/service.py` kept five private copies of M2's port types | Low | Review of PR #27 (M4-6) | FR-10, D-020 | Closed | Copies removed; `ReservationDemand`, `UpcomingBookings`, `OpenTrips` imported from `core.providers`; behaviour unchanged | PR #39, `abeb4ca` |
| DEF-M4-002 | `approve_task()` raised nested `UnitOfWork` error when rolling back failed claim allocations | Medium | PR #27 review & lifecycle tests | UC-M4-02, BR-M4-04 | Closed | Extracted `_mark_task_failed()` outside claim UoW context so failure transition runs in independent transaction | PR #27, `9f4a825` |
| DEF-M4-003 | `carry_out_return()` failed to supply `parking_space_id` and `claim_id` in `TransitionCtx` | Medium | PR #27 review & lifecycle tests | UC-M4-03, BR-M1-02 | Closed | Extracted active `SPACE` claim ID and parking space ID from task claims into `TransitionCtx` for `VehicleEvent.RETURN` | PR #27, `9f4a825` |
| DEF-M4-004 | `AllocationService` and `AlternativeHubService` read simulated time directly from `core._clock.now()` | Low | PR #27 review (M4-3) | D-005, NFR-13 | Closed | Switched all service time reads to `core.queries.get_config().as_of` via injected runtime facade | PR #27, `9f4a825` |
| DEF-M4-005 | Router endpoints allowed unauthenticated operator operations without token verification | Medium | PR #27 review (M4-7) | D-023, NFR-16 | Closed | Guarded all 12 endpoints with `Depends(require_operator)` and constructed actors via `acting_as(principal, "allocation")` | PR #27, `4cdf184` |
<!-- END M4: Resource Allocation & Dispatching -->

<!-- BEGIN M5: Monitoring & Incident Handling -->
### M5 Monitoring & Incident Handling

| ID | Title | Severity | Found by | Related IDs | Status | Resolution | Fix |
|---|---|---|---|---|---|---|---|
| DEF-M5-001 | Monitoring router endpoints lacked explicit operator authorization check | Medium | Security audit (TC-M5-018) | NFR-16, D-014, D-023 | Closed | Enforced `require_operator` dependency on all 11 endpoints | PR #33, `895950d` |
| DEF-M5-002 | Incident timestamps and audit logs did not use Core's injected clock | Low | Review at integration (D-005) | D-005, NFR-13 | Closed | Switched `_now()` to `core.queries.get_config().as_of` | PR #33, `cb17a48` |
<!-- END M5: Monitoring & Incident Handling -->

<!-- BEGIN M6: What-if Simulation -->
### M6 What-if Simulation

<!-- M6 adds rows here by 17/11. -->

| ID | Title | Severity | Found by | Related IDs | Status | Resolution | Fix |
|---|---|---|---|---|---|---|---|
| DEF-M6-001 | Demand surge could take vehicles from a Hub that is itself a surge target | High | M1 while fixing the merge of PR #30 | FR-12, UC-M6-01 | Closed | See below | PR #39, `45e9781` |
| DEF-M6-002 | Design document showed `export_snapshot()` returning a `dict` | Low | Review of PR #18 (M6-8) | NFR-12, core-api-spec §7 | Closed | Interface changed to `OperationalSnapshot` from `core.services.snapshot` | PR #39, `8f75fab` |
| DEF-M6-003 | Critical-battery metric used 20 % instead of core's 15 % | Low | Review of PR #18 (M6-11) | FR-12, core-api-spec §10 point 3 | Closed | Metric reads `battery_pct(v) ≤ LOW_BATTERY_THRESHOLD` | PR #39, `8f75fab` |
| DEF-M6-004 | Use-case diagram existed only as a Mermaid block, not as `.puml`/`.svg` | Low | Review of PR #18 (M6-14) | UC-M6-01 | Closed | `uc-m6-simulation.puml` and `.svg` added and linked | PR #39, `8f75fab` |
| DEF-M6-005 | Formulas and lists in report section 3.5 did not render | Low | Review of PR #18 (M6-15) | FR-12 | Closed | Formulas written as `$$...$$`, lists split | PR #39, `e048c39` |
| DEF-M6-006 | Unmerged conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`) corrupted `uc-m6-simulation.puml` and `.svg` | Low | Review of PR #47 (M6-1, M6-2) | UC-M6-01 | Closed | Restored clean diagram files directly from `origin/develop` | PR #47, `c77ce32` |
| DEF-M6-007 | `AttributeError: 'dict' object has no attribute 'random_seed'` during NFR test execution | High | Integration testing (M6-3) | NFR-12, NFR-13 | Closed | See below | PR #47, `c77ce32` |
| DEF-M6-008 | Trailing newline missing at the end of `pyproject.toml` | Low | Review of PR #47 (M6-9) | — | Closed | Appended newline to EOF in `pyproject.toml` | PR #47 |

**DEF-M6-001** (High)
- Steps: run the demand-surge scenario with two target Hubs, H01 and H02, and a third Hub H03 with spare vehicles (`src/simulation/engine.py`, `_find_donor_hub`, on `e612961`).
- Expected: every recommendation takes vehicles from H03. Actual: only the Hub being served was excluded, so H02, also short, could be the donor for H01.
- Resolution: the donor search skips every surge target. Retest: new test `test_a_surge_target_is_never_chosen_as_donor` passes.

**DEF-M6-007** (High)
- Steps: run `pytest tests/simulation/test_simulation_engine.py` after adding `test_nfr12_state_isolation` and `test_nfr13_reproducibility`.
- Expected: simulation runs using `SimulationConfig` dataclass and passes isolation checks.
- Actual: passing raw `dict` configs into `SimulationEngine` caused `AttributeError: 'dict' object has no attribute 'random_seed'`.
- Resolution: refactored NFR test cases to instantiate and pass valid `SimulationConfig` objects into `self.service.run_simulation`. Retest: all 5 tests passed in 0.68s.
<!-- END M6: What-if Simulation -->
