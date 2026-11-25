# M3 Test Cases - Charging & Smart Scheduling

> **Owner:** Võ Thanh An (M3)  
> **Format:** Test Plan §13 (`docs/testing/test-plan-skeleton.md`)  
> **Automated in:** `tests/charging/test_charging.py` (pytest)  
> **Status:** All cases below are automated and passed in M3's local pytest run; the final run for the execution report is repeated before submission.

## 1. Common fixture F1

Every case uses fixture **F1** unless the Preconditions column says otherwise (`_build_core()` in the test file):

- Clock fixed at `T0 = 2026-11-08 08:00 UTC`.
- Hub `H1` with two charging points: `H1-CP01` on space `H1-S001` (occupied by `V-DOCKED`) and `H1-CP02` on space `H1-S002` (free). Both `AVAILABLE`.
- Fleet e-bikes: `V-DOCKED` 50 % (parked at `H1-S001`), `V-149` 14.9 %, `V-150` 15.0 %, `V-151` 15.1 %, `V-400` 40 %.
- Users: `STU1` (student, code `2452030`), `STU2` (student, code `2452031`), `OP1` (operator, code `OP-01`).
- Low-battery threshold 15 % (Core default) unless a case changes it.

In the Evidence column, `test_*` is a function in `tests/charging/test_charging.py`.

## 2. Test cases

### 2.1 Priority queue and low-battery override (UC-M3-06)

| TC ID | Verifies | Technique | Preconditions | Input / Event | Expected Result | Status | Evidence |
|---|---|---|---|---|---|---|---|
| TC-M3-001 | FR-11.M3.1, UC-M3-06, BR-M3-03 | BVA | F1; no free bay for the vehicle (all submissions queue) | Immediate request for each of `V-149` (14.9 %), `V-150` (15.0 %), `V-151` (15.1 %), `V-400` (40 %) | Request is `QUEUED`; `is_emergency` is true for 14.9 % and 15.0 %, false for 15.1 % and 40 % | Pass | `test_battery_threshold_bva` (4 parameters) |
| TC-M3-002 | FR-11.M3.1, UC-M3-06, BR-M3-03 | EP | F1; four requests queued one minute apart in the order `V-151`, `V-400`, `V-150`, `V-149` | `compute_priority_queue("H1")` | Order is `V-149`, `V-150`, `V-151`, `V-400` (emergency first, then lowest SoC) | Pass | `test_priority_queue_ordering` |
| TC-M3-003 | BR-M3-03, D-005 | EP | F1 with `CoreConfig(low_battery_threshold=20.0)` | Immediate request for `V-151` (15.1 %) | `is_emergency` is true: threshold is read from Core config | Pass | `test_threshold_reads_from_core_config` |
| TC-M3-004 | FR-11.M3.1, BR-M3-03, UC-M3-06 | Decision table | F1; `V-400`, `V-151`, `V-149` queued; stub `RESERVATION_DEMAND` provider reports a booking for `V-400` | `compute_priority_queue("H1")` before and after registering the stub | Before: `V-149`, `V-151`, `V-400`. After: `V-149`, `V-400`, `V-151` (booked vehicle ranks right after the emergency) | Pass | `test_stub_reservation_demand_provider_prioritizes_booked` |
| TC-M3-005 | BR-M3-03, NFR-10 | Failure injection | F1; `V-400`, `V-151` queued; `RESERVATION_DEMAND` provider returns `Err(RESOURCE_UNAVAILABLE)` | `compute_priority_queue("H1")` | No failure; order falls back to battery only: `V-151`, `V-400` | Pass | `test_reservation_demand_error_falls_back_to_battery_only` |

### 2.2 Immediate and scheduled charging (UC-M3-01, UC-M3-02)

| TC ID | Verifies | Technique | Preconditions | Input / Event | Expected Result | Status | Evidence |
|---|---|---|---|---|---|---|---|
| TC-M3-006 | FR-06.1, FR-06.2, UC-M3-01, UC-M3-02, BR-M3-01, D-020 | State transition | F1 | Immediate request for `V-DOCKED`, then finish; schedule a second request for `V-149` at T0 + 30 min; call `CHARGING_DEMAND` provider | First session `CHARGING`, then `COMPLETED`; second `SCHEDULED`; provider returns only the scheduled session | Pass | `test_charging_lifecycle_and_d020_provider` |
| TC-M3-007 | FR-06.2, UC-M3-02, NFR-08, NFR-16 | State transition | F1 on the real Core app; student, other student and operator tokens | Schedule for T0 + 30 min via API; start at T0 (owner), advance 30 min, start as other student, start as owner; finish | 409 before due time; 404 for other student; 200 for owner; Core shows vehicle and point `CHARGING`; finish gives `COMPLETED`; each role sees the right `/sessions` rows | Pass | `test_schedule_start_finish_lifecycle_through_app` |
| TC-M3-008 | UC-M3-02, NFR-08 | State transition (invalid event) | F1; `V-DOCKED` scheduled at T0 + 30 min | `start_scheduled_session` before the start time | `INVALID_STATE`; session still `SCHEDULED`; vehicle and point unchanged in Core | Pass | `test_start_scheduled_session_before_start_time_changes_nothing` |
| TC-M3-009 | UC-M3-02, NFR-16 | EP (authorization) | F1; session due | `start_scheduled_session` as `STU2` | `NOT_FOUND`; session still `SCHEDULED`; Core unchanged | Pass | `test_start_scheduled_session_by_other_student_changes_nothing` |
| TC-M3-010 | UC-M3-02, NFR-08, NFR-09 | State transition | F1; session due | Start as owner, start again, then finish | First start: session, vehicle and point all `CHARGING`; second start `INVALID_STATE`; finish gives `COMPLETED` and point `AVAILABLE` | Pass | `test_start_scheduled_session_after_start_time_updates_core_then_finish` |
| TC-M3-011 | UC-M3-02, NFR-16 | EP (authorization) | F1; session due | `start_scheduled_session` as operator | Succeeds: session and vehicle `CHARGING` | Pass | `test_start_scheduled_session_operator_allowed` |
| TC-M3-012 | UC-M3-02, NFR-18 | EP (invalid input) | F1; session due | `start_scheduled_session("NON-EXISTENT")` | `NOT_FOUND` | Pass | `test_start_scheduled_session_unknown_id_is_not_found` |
| TC-M3-013 | UC-M3-02, NFR-08, NFR-16 | State transition | F1; `V-DOCKED` scheduled; owner and other-student clients | `POST /sessions/{id}/start` before due, as other student after due, unknown id, owner after due | 409, 404, 404, 200 (status `CHARGING`, Core `CHARGING`); finish returns 200 | Pass | `test_start_endpoint_before_and_after_start_time` |
| TC-M3-014 | FR-06.1, BR-M3-01, NFR-21 | Conflict | F1; `V-DOCKED` not used; both bays busy for the request | `POST /requests/immediate` with `queue_if_full=false` for a vehicle that has no free bay | 409; no request record is stored | Pass | `test_immediate_endpoint_conflict_when_no_bay_and_no_queue` |

### 2.3 Modify, cancel and interrupt (UC-M3-03, UC-M3-08)

| TC ID | Verifies | Technique | Preconditions | Input / Event | Expected Result | Status | Evidence |
|---|---|---|---|---|---|---|---|
| TC-M3-015 | FR-06.3, UC-M3-03 | State transition | F1 | Schedule `V-149` at T0 + 1 h, modify to T0 + 2 h for 45 min, then cancel | Modify: `start_time` is the new time; cancel: status `CANCELLED` | Pass | `test_modify_and_cancel_schedule` |
| TC-M3-016 | FR-06.1, FR-06.3, UC-M3-01, UC-M3-03, UC-M3-08, NFR-09 | State transition | F1; student client | Immediate request, interrupt with 60 % SoC; schedule `V-149`, patch to T0 + 2 h / 45 min, delete | Interrupt: `INTERRUPTED`, SoC 60 %, vehicle no longer `CHARGING`; modify: new window and a claim on the point; cancel: `CANCELLED` and the claim is gone from Core | Pass | `test_request_endpoints_immediate_interrupt_and_schedule_lifecycle` |
| TC-M3-017 | UC-M3-03, NFR-16 | EP (authorization) | F1; `R-OWN` scheduled by `STU1` | `PATCH` and `DELETE /requests/R-OWN` as `STU2` | Both 404; request still `SCHEDULED` | Pass | `test_other_student_cannot_modify_or_cancel_via_api` |
| TC-M3-018 | UC-M3-08, NFR-08 | State transition | F1; `V-DOCKED` charging (`CHARGING`) | `interrupt_charging` with `current_soc=60` | Status `INTERRUPTED`; `current_soc` is 60 | Pass | `test_interrupt_charging_session` |

### 2.4 Private EV (UC-M3-04, UC-M3-05)

| TC ID | Verifies | Technique | Preconditions | Input / Event | Expected Result | Status | Evidence |
|---|---|---|---|---|---|---|---|
| TC-M3-019 | FR-07.M3.1, UC-M3-04 | EP | F1; student `STU1` | `POST /private/vehicles` (E-bike, 2.5 kWh, 30 %, Type2) | 200; Core has a `PRIVATE` vehicle `V-PRIV-PRIV123` owned by `STU1` with 30 % battery | Pass | `test_private_vehicle_creation_and_ownership` |
| TC-M3-020 | FR-07.M3.1, UC-M3-04, NFR-16 | EP (authorization) | F1; student `STU2` | `POST /private/vehicles` | Owner in Core is `STU2` (taken from the token, not the body) | Pass | `test_private_vehicle_owner_comes_from_principal_not_body` |
| TC-M3-021 | FR-07.M3.2, UC-M3-04, UC-M3-05 | State transition | F1; student `STU1` | Register a private EV, then `POST /private/slots` for T0 + 1 h, 30 min | Slot request `SCHEDULED`; stored request belongs to `STU1` and the new vehicle | Pass | `test_private_vehicle_can_reserve_slot` |

### 2.5 Queue optimization (UC-M3-07)

| TC ID | Verifies | Technique | Preconditions | Input / Event | Expected Result | Status | Evidence |
|---|---|---|---|---|---|---|---|
| TC-M3-022 | FR-11.M3.2, UC-M3-07, BR-M3-01, BR-M3-02 | State transition | F1; `V-DOCKED` charging on `CP01`; `V-149` queued | `optimize_queue("H1")` as operator | `REQ-Q` becomes `SCHEDULED` on `H1-CP02`, 60 min from T0; claim exists in Core; vehicle stays `AVAILABLE` and the point stays `AVAILABLE` (not started) | Pass | `test_optimize_queue_turns_queued_into_scheduled` |
| TC-M3-023 | FR-11.M3.2, UC-M3-07, NFR-18 | EP (invalid input) | As TC-M3-022; operator client | `POST /schedule/optimize` without `hub_id`, then with `hub_id=H1` | 422, then 200 with `[REQ-Q: SCHEDULED]` | Pass | `test_optimize_endpoint_requires_hub_id_and_returns_sessions` |
| TC-M3-024 | FR-11.M3.2, UC-M3-07, NFR-06, NFR-09 | Conflict | F1; three `QUEUED` requests (`V-149`, `V-150`, `V-151`), two bays | `optimize_queue("H1")` | All three `SCHEDULED` in priority order; both bays used; each has a claim; no two sessions overlap on one point | Pass | `test_optimize_queue_binds_three_requests_on_two_bays_without_overlap` |
| TC-M3-025 | FR-11.M3.2, UC-M3-07 | Conflict | As TC-M3-024; operator client | `POST /schedule/optimize?hub_id=H1` | 200; all three returned as `SCHEDULED`; Core agrees | Pass | `test_optimize_endpoint_binds_three_queued_requests` |
| TC-M3-026 | BR-M3-02, UC-M3-07 | BVA (window exhausted) | F1; both bays blocked for 240 min from T0; `V-149` queued | `optimize_queue("H1")` | Returns `[]` without error; request stays `QUEUED` | Pass | `test_optimize_queue_leaves_requests_queued_when_no_slot` |
| TC-M3-034 | FR-11.M3.3, BR-M3-02, UC-M3-07, UC-M4-07 | Integration (stub M4 port) | F1 plus Hub `H2` with one free bay `H2-CP01`; both H1 bays blocked for 240 min; `V-149` queued at H1; stub `ALTERNATIVE_CHARGING` returns `FOUND` at `H2` / `H2-CP01` | `optimize_queue("H1")` | M4 is called once for the request with hub `H1`; request moves to `H2`, `SCHEDULED` on `H2-CP01` from T0 for 60 min with a claim in Core; H1 queue is empty | Pass | `test_optimize_queue_moves_request_to_m4_hub_when_hub_is_full` |
| TC-M3-035 | BR-M3-02, UC-M4-07 | Integration (stub M4 port) | As TC-M3-034; stub returns `NO_CHARGER` | `optimize_queue("H1")` | Returns `[]`; request stays `QUEUED` at `H1`; no claim on `H2-CP01` | Pass | `test_optimize_queue_keeps_request_queued_when_m4_finds_no_charger` |
| TC-M3-036 | BR-M3-02, BR-M3-01, NFR-06 | Failure injection | As TC-M3-034; stub suggests a bay at an unknown Hub `H9` | `optimize_queue("H1")` | M3 checks the suggestion again in Core, finds no free bay, request stays `QUEUED` at `H1` | Pass | `test_optimize_queue_rechecks_m4_suggestion` |

### 2.6 Charging-point failure and events (UC-M3-08)

| TC ID | Verifies | Technique | Preconditions | Input / Event | Expected Result | Status | Evidence |
|---|---|---|---|---|---|---|---|
| TC-M3-027 | FR-11.M3.3, UC-M3-08, BR-M3-02, NFR-10 | Failure injection | F1; `V-DOCKED` charging on `CP01` (`REQ-S1`) | `CP01` set `OUT_OF_SERVICE` in Core and `ChargingPointStatusChanged` delivered | `REQ-S1` `INTERRUPTED`; new request `REQ-S1-R1` for the same user and vehicle is `SCHEDULED` on `CP02` with a claim; no claim left on `CP01`; `CP01` is `OUT_OF_SERVICE` in Core | Pass | `test_point_failure_moves_session_to_other_bay` |
| TC-M3-028 | UC-M3-07, UC-M3-08 | State transition | F1; `V-DOCKED` charging, `V-149` queued | `ChargingPointStatusChanged` with `CP02` `AVAILABLE` | `REQ-Q` becomes `SCHEDULED` on `CP02` | Pass | `test_point_available_event_schedules_queued_request` |
| TC-M3-029 | UC-M3-08, NFR-10, NFR-18 | EP (invalid input) | F1; `REQ-S1` charging | Status-change event with an empty payload | Ignored; `REQ-S1` still `CHARGING` | Pass | `test_point_status_event_without_data_is_ignored` |

### 2.7 Security and visibility (NFR-16)

| TC ID | Verifies | Technique | Preconditions | Input / Event | Expected Result | Status | Evidence |
|---|---|---|---|---|---|---|---|
| TC-M3-030 | NFR-16 | EP | F1 on the real Core app | Every `/charging` endpoint with no token and with a garbage token | 401 on all 13 endpoints (also proves `install()` mounts the router) | Pass | `test_install_mounts_router_and_every_endpoint_needs_a_token`, `test_charging_router_security_401_403` |
| TC-M3-031 | NFR-16, NFR-21 | EP | F1 on the real Core app; student token | `GET /queue`, `GET /demand`, `POST /schedule/optimize` | 403 with error code `FORBIDDEN` on each | Pass | `test_student_gets_403_on_operator_endpoints_through_app` |
| TC-M3-032 | NFR-16 | EP | F1; operator token | `GET /queue`, `GET /demand`, `POST /schedule/optimize`; `GET /sessions` | 200 on each; lists returned | Pass | `test_operator_token_reaches_operator_endpoints_through_app`, `test_operator_allowed_on_operator_endpoints`, `test_charging_router_private_endpoints`, `test_charging_router_demand_endpoint`, `test_charging_router_endpoints_success` |
| TC-M3-033 | NFR-16 | EP | F1; `STU1` and `STU2` each have a session | `GET /sessions` as `STU1`, `STU2`, operator | Student sees only own session; operator sees both | Pass | `test_student_sees_only_own_sessions` |
| TC-M3-037 | FR-06, FR-11, BR-M3-03, UC-M7-03 | Decision table | F1 on the real Core app; three queued requests | `GET /queue` as operator | Rank 1..3 in BR-M3-03 order; EMERGENCY_LOW_BATTERY at 14.9%, LOWEST_BATTERY_FIRST otherwise; owner STU1, ownership FLEET | Pass | `test_queue_route_gives_rank_reason_and_owner` |
| TC-M3-038 | FR-06, UC-M3-08, UC-M7-03, NFR-16 | Failure injection | F1 on the real Core app; REQ-S1 charging on CP01 | CP01 goes OUT_OF_SERVICE; `GET /moved` as operator, as student, and for H2 | REQ-S1 from CP01 to REQ-S1-R1 on CP02 (SCHEDULED); 403 for a student; empty for H2 | Pass | `test_moved_route_lists_sessions_moved_after_a_failure` |
| TC-M3-039 | FR-06, BR-M3-03, UC-M3-01, UC-M3-07 | State transition | F1 on the real Core app; two vehicles not in a bay | `POST /requests/immediate` for each as a student | Both are SCHEDULED at once on two different points with a start time; none stays QUEUED while a slot is free | Pass | `test_a_request_waits_only_while_no_slot_is_free` |

## 3. Not covered (known gaps)

| Gap | Reason | Where recorded |
|---|---|---|
| FR-06.3 minimum notice period for modify/cancel | Not implemented; only "new start not in the past" is checked | Implementation report §4.4 |
| FR-11.M3.2 grid-load limit | Not implemented; `optimize_queue` only binds requests to the earliest free slot | Implementation report §4.4 |


## 4. Rows for the traceability sheet (§5, to be copied by M8)

| TC ID | Test Case | Technique | Linked IDs | Status |
|---|---|---|---|---|
| TC-M3-001 to TC-M3-005 | Priority queue and low-battery override | BVA / EP / decision table / failure injection | FR-11.M3.1, UC-M3-06, BR-M3-03 | Pass |
| TC-M3-006 to TC-M3-014 | Immediate and scheduled charging | State transition / conflict / EP | FR-06.1, FR-06.2, UC-M3-01, UC-M3-02, BR-M3-01 | Pass |
| TC-M3-015 to TC-M3-018 | Modify, cancel, interrupt | State transition / EP | FR-06.3, UC-M3-03, UC-M3-08 | Pass |
| TC-M3-019 to TC-M3-021 | Private EV | EP / state transition | FR-07.M3.1, FR-07.M3.2, UC-M3-04, UC-M3-05 | Pass |
| TC-M3-022 to TC-M3-026 | Queue optimization | State transition / conflict / BVA | FR-11.M3.2, UC-M3-07, BR-M3-02, NFR-06 | Pass |
| TC-M3-034 to TC-M3-036 | Move to another Hub through M4 | Integration (stub M4 port) / failure injection | FR-11.M3.3, BR-M3-02, UC-M4-07 | Pass |
| TC-M3-027 to TC-M3-029 | Charging-point failure and events | Failure injection / state transition | FR-11.M3.3, UC-M3-08, BR-M3-02, NFR-10 | Pass |
| TC-M3-030 to TC-M3-033 | Security and visibility | EP | NFR-16 | Pass |
| TC-M3-037 to TC-M3-038 | Queue rank, reason, owner and moved sessions | Decision table / failure injection | FR-06, FR-11, BR-M3-03, UC-M3-08, UC-M7-03 | Pass |
| TC-M3-039 | A request waits only while no slot is free | State transition | FR-06, BR-M3-03, UC-M3-01, UC-M3-07 | Pass |