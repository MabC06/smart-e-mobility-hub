# 4. Implementation

> **Status:** outline · **Owner:** M1 (4.1, 4.2; consolidates 4.3, 4.4) · **Date:** 2026-11-16
> The rubric asks for "technically meaningful implementation choices rather than repeating the design section". Each point below says what to write and where the facts are; it links to Section 3 instead of copying it. M2–M6 write their own parts of 4.3 and 4.4 inside their blocks by 17/11 (`task-assignment-timeline.md`, Phase 4).

## 4.1 Technology Stack and Development Environment

Write: the table below, one sentence of justification per row, and how the system is run. Source: D-002, `docs/design/architecture/tech-stack-proposal.md`, `requirements.txt`, `requirements-dev.txt`, `README.md` "Getting Started".

| Concern | Choice (pinned version) | Why (one sentence each, from D-002) |
|---|---|---|
| Language | Python 3.12, pip + venv with pinned `requirements*.txt` | One language for every module and the tests; runs from a clean clone (NFR-14). |
| Web API | FastAPI 0.162 with Pydantic 2.14, served by uvicorn 0.54 | Request and response types are checked from the same models as the core interface; OpenAPI pages come for free. |
| Database | SQLite through SQLAlchemy 2.1 Core | No server to install (NFR-14); PostgreSQL stays an upgrade path (Section 3.1.7); foreign keys on, write-ahead log; tests use an in-memory store with the same `Repository` interface. |
| Web UI | Jinja2 3.1 templates and HTMX, rendered by the server | Replaced the React + Vite proposal (D-002): no Node toolchain; M7 agreed. |
| Authentication | PBKDF2-SHA256 hashes and HMAC-signed bearer tokens, inside `core` | Standard library only; no external identity service (D-014, A-06). |
| Quality tools | pytest 9.2, pytest-cov 7.1, ruff 0.17, mypy 2.4 (strict on `core`, `reservation`, `main.py`) | The same commands run on a laptop and in CI (D-019, D-025). |
| CI | GitHub Actions on Ubuntu | Lint, format, types, tests, coverage per module and the import-boundary check on every PR (NFR-22, NFR-24, NFR-27). |

Points to cover after the table:
- Runtime: one process (`python -m uvicorn --app-dir src main:create_app --factory`), settings from `.env` (`APP_ENV`, `DATABASE_URL`, `SECRET_KEY`, `SEED_ON_START`; `.env.example`). Empty `DATABASE_URL` means an in-memory store.
- Time: every timestamp is UTC from an injectable clock (D-005), so tests and simulation runs are repeatable (NFR-13).
- No external services or paid APIs. The IoT layer is the simulator in `src/iot_sim/` (D-004).
- Development process in one or two sentences: work on short branches from `develop`, one PR per change, one approval and a green CI before merge (CONTRIBUTING section 8, D-001).

## 4.2 Implementation Structure

Write: how Section 3.1 maps to code. One figure (folder tree or package diagram) and one table, then one short paragraph per mechanism. Do not list every file. Source: `architecture-diagram.md`, `src/main.py`, `core-api-spec.md`.

### 4.2.1 Packages and owners

| Package (`src/`) | Owner | Realizes (Section 3) | Size (lines of Python, 2026-11-16) |
|---|---|---|---|
| `core` | M1 | Shared state, state machine, claims, events, snapshot, REST API, sign-in | ≈ 5 300 |
| `reservation` | M2 | Rental and parking reservations, trips | ≈ 700 |
| `charging` | M3 | Charging sessions and queue | ≈ 1 300 |
| `allocation` | M4 | Rebalancing plans, arbitration, alternatives | ≈ 1 800 |
| `monitoring` | M5 | Incidents and escalation | ≈ 900 |
| `simulation` | M6 | What-if engine on a snapshot | ≈ 200 (update after SC-02 to SC-05) |
| `ui` | M7 | Operator and student screens | ≈ 1100 |
| `iot_sim` | M8 | Sensor events and seed network (outside the system boundary, D-004) | ≈ 240 |
| `main.py` | M1 | Composition root (D-013) | — |

Refresh the sizes on 18/11; they are only there to show where the logic is.

### 4.2.2 Inside `core`

Short paragraph per layer, mapped to the class diagram (Section 3.2.1):
- `domain/`: entities, enums, the vehicle state machine and the invariant checker (BR-M1-01 to BR-M1-03, NFR-07).
- `services/`: commands, queries, unit of work, sensor intake, snapshot.
- `repository/`: one `Repository` interface with two stores, `memory.py` (tests, What-if runs) and `sql.py` (SQLite).
- `api/`: the core REST router and `security.py`, which the module routers import (D-023).
- `facade.py`: `CoreFacade`, the only object a module receives.

### 4.2.3 How a module plugs in

- `main.py` builds `core` on the database, then calls `install(core, app)` of each module in a fixed order (reservation, charging, allocation, monitoring, simulation, ui), D-013.
- In `install` a module registers its provider ports (§6.1 of the spec, D-020), its own tables (`register_entity`, D-018), its event handlers and its router.
- The direction of dependencies is checked by a test, not by convention: `tests/core/test_import_boundaries.py` (NFR-22). `core` imports no module; modules import only the public surface of `core`.

### 4.2.4 Persistence

- Modules never open the database. Their tables join `core`'s transaction through `uow.repository` (D-018), so "change the vehicle and write the reservation" commits or fails together (NFR-09).
- SQLite details that matter: `BEGIN IMMEDIATE` for writes, optimistic lock on `version`, savepoint per command, IDs resumed from stored IDs after a restart (D-022).

### 4.2.5 APIs and events

- REST: core router plus one router per module, all behind the same token check (NFR-16, D-014, D-023). List only the route prefixes; the full list is the OpenAPI page.
- Events: in-process `EventBus`, published only after a commit; a failing handler is logged and does not undo the commit (`core/events.py`). Name the main events and who listens (table from `core-api-spec.md` §6).
- Provider ports: `core` calls a module only through a port that the module registered (§6.1), so the dependency still points into `core`.

### 4.2.6 Simulation subsystem

- M6 takes an `OperationalSnapshot` (one commit point, copies only, content hash as ID), loads it into an in-memory store and runs the scenario there (NFR-12). The live store is never written.
- One sentence linking to Section 3.5 for the scenarios; details of isolation go in 4.3 (M6).

## 4.3 Important Implementation Decisions

Write: 3 to 5 decisions per module that were hard or not obvious, each as **problem → what the code does → why → where (file, test)**. Skip anything already explained in Section 3. The rubric's examples, with the module that covers each:

| Rubric example | Covered by |
|---|---|
| Maintaining consistent resource state | M1 (claims, unit of work, invariant checker) |
| Resolving reservation conflicts | M2, and M4 for competing requests |
| Processing failures | M3 (charging-point failure), M5 (incidents), M1 (rejected sensor events) |
| Synchronizing state updates | M1 (lock, optimistic version, events after commit) |
| Implementing charging allocation | M3, and M4 for alternatives |
| Isolating simulated state from operational state | M6 |

<!-- BEGIN M1: Core -->
Draft points for M1:
- One owner of shared state: modules hold **claims** on resources and release only their own (D-017); `core` never expires a claim.
- All writes go through one runtime lock and the unit of work; M4 plans on a snapshot and commits with `snapshot_version`, failing with `VERSION_CONFLICT` if the state moved (`services/unit_of_work.py`).
- Events after commit, never inside the transaction, so a handler cannot see uncommitted state.
- Bad sensor events are rejected as a whole and reported as `SensorEventRejected` (NFR-10, `services/sensor_intake.py`).
- No command-result store: idempotency is kept by M2 from its own records (D-015).
<!-- END M1: Core -->

<!-- BEGIN M2: Reservation & Trip -->
<!-- M2 writes here by 17/11. -->
<!-- END M2: Reservation & Trip -->

<!-- BEGIN M3: Charging & Smart Scheduling -->
**M3 Charging & Smart Scheduling**

- **Charging allocation with claims.** Problem: two sessions must never share a bay in the same interval, and a bay must be found even when the requested time is taken. Code: `_earliest_slot` tries start times every 15 minutes for up to 2 hours; `_bind_bay` places a `CHARGING_SESSION` claim on the charging point and one on the vehicle, and finish, interrupt and cancel release them (D-017). Why: Core's claim check rejects overlaps, so the rule is enforced in one place and not by M3's own bookkeeping. Where: `src/charging/service.py`; TC-M3-022 to TC-M3-026.
- **One unit of work per queued request.** Problem: `_bind_bay` commits, and a commit closes the unit of work, so binding a whole queue in one unit of work failed on the second request (DEF-M3-002). Code: `optimize_queue` ranks the queue first, then binds each request in its own `_run`. Why: a failure on one request leaves the others bound, and no half-placed claims remain. Where: `optimize_queue`; TC-M3-024, TC-M3-025.
- **Charging-point failure.** Problem: a failed point must not leave a session running or a future session bound to it. Code: M3 subscribes to `ChargingPointStatusChanged`; for `OUT_OF_SERVICE` or `MAINTENANCE` it interrupts the session on that point and submits a new request `<id>-R<n>` for the same vehicle and owner (because `INTERRUPTED` is a final state), moves the `SCHEDULED` sessions of that point, then runs `optimize_queue`. Why: the event comes from Core, so M3 reacts the same way whether M5 or an operator changed the status. Where: `_on_point_status_changed`, `_resubmit_after_failure`; TC-M3-027 to TC-M3-029.
- **Alternative Hub through M4.** Problem: when the Hub has no slot within 2 hours, the request should go to another Hub (BR-M3-02, step 3). Code: `optimize_queue` calls `ProviderPort.ALTERNATIVE_CHARGING`; M4 only suggests, so M3 checks the suggested Hub's bays again in the same unit of work, prefers M4's bay and binds the request there. If M4 finds nothing or is not installed, the request stays `QUEUED`. Why: M4's answer is read-only and may be out of date by the time M3 binds. Where: `_alternative_hub_bay`; TC-M3-034 to TC-M3-036.
- **Priority with a fallback.** Problem: the booking factor needs M2's data, which may be missing. Code: `compute_priority_queue` ranks by emergency (SoC at or below Core's `low_battery_threshold`), then a booking at that Hub in the next hour (`RESERVATION_DEMAND`), then lowest SoC, then request time; if the port returns an error, it ranks by battery only. Why: charging must keep working when M2 is down. Where: `compute_priority_queue`; TC-M3-001 to TC-M3-005.
<!-- END M3: Charging & Smart Scheduling -->

<!-- BEGIN M4: Resource Allocation & Dispatching -->
Draft points for M4:
- **Consistent resource state across dispatch lifecycle (BR-M4-04, D-017):** Dispatch tasks require atomic co-allocation of suitable fleet vehicles at the source hub and parking spaces at the destination hub. `approve_task()` places `HolderKind.DISPATCH_TASK` claims on both resources inside one atomic unit of work (`src/allocation/service.py`). If any claim fails, placed claims are released and `_mark_task_failed()` runs in a separate external UoW so failure transitions complete cleanly without nested transaction errors (`tests/allocation/test_review.py`). When completing return, `carry_out_return()` passes `parking_space_id` and `claim_id` from the active space claim into `TransitionCtx` for `VehicleEvent.RETURN` and releases remaining active task claims.
- **Resolving competing resource requests under scarcity (BR-M4-01, UC-M4-06):** When multiple concurrent demands compete for the same scarce vehicle or bay space, `ArbitrationService.arbitrate()` sorts requests strictly by priority class tier (`OPERATOR_INCIDENT > RESERVATION_PICKUP > VEHICLE_RETURN > CHARGING > REBALANCE > WALK_IN`), breaking ties deterministically by `requested_at` ascending and request ID (`src/allocation/arbitration.py`, `tests/allocation/test_arbitration.py`). The winning request is granted the resource atomically, while displaced requests receive typed errors with explicit reason codes (`ErrorCode.RESOURCE_UNAVAILABLE`).
- **Decoupled provider port integration without fallback stubs (D-020, NFR-22):** Rather than importing M2/M3 modules directly or falling back to silent empty mocks, `AllocationService._fetch_hub_demand()` queries `ProviderPort.RESERVATION_DEMAND` through Core's registry. A missing or failing port raises `RESOURCE_UNAVAILABLE` immediately (`src/allocation/service.py`). Conversely, M4 implements `AlternativeHubProvider` and `AlternativeChargingProvider` using frozen dataclass contracts (`src/core/providers.py`), verified by 25 import-boundary checks (`tests/test_import_boundaries.py`).
- **Injected clock time and RBAC authorization (D-005, D-023, NFR-16):** All time calculations read `core.queries.get_config().as_of` from Core's injectable clock instead of system wall-clock, ensuring deterministic rebalancing in simulation scenarios (M6). Every REST endpoint in `src/allocation/router.py` is protected by `Depends(require_operator)` and derives domain actors via `acting_as(principal, "allocation")` (`tests/allocation/test_api.py`).
<!-- END M4: Resource Allocation & Dispatching -->

<!-- BEGIN M5: Monitoring & Incident Handling -->
Draft points for M5:
- **Decoupled incident ingestion via Core EventBus**: M5 consumes only Core's domain events (`ChargingPointStatusChanged`, `VehicleBatteryChanged`, `SensorEventRejected`, `SensorHeartbeat`), never importing `iot_sim` directly (NFR-22, D-004). Telemetry liveness is tracked in an internal timestamp map (`_heartbeats`) to detect connection loss (> 30s) deterministically. Unmapped sensors log a warning and skip ticket creation to protect schema integrity.
  *File:* `src/monitoring/service.py`, `tests/monitoring/test_monitoring.py` (`TC-M5-001`, `TC-M5-002`, `TC-M5-006`, `TC-M5-020`).
- **Deterministic escalation timer on injectable clock**: `BR-M5-04` requires unacknowledged `HIGH`/`CRITICAL` tickets to auto-escalate after 5 minutes. Rather than relying on OS daemon threads and wall-clock time, `check_and_escalate_unacknowledged` computes ticket age against `core.queries.get_config().as_of` (`FixedClock`, D-005), preserving deterministic replayability (NFR-13).
  *File:* `src/monitoring/service.py`, `tests/monitoring/test_monitoring.py` (`TC-M5-008`).
- **Concurrency-safe capacity status synchronization**: Evaluates Hub parking occupancy upon `SpaceOccupancyChanged` (`BR-M5-01`, `BR-M5-02`), transitioning Hub status through `core.commands.set_hub_status` using optimistic version checks (`expected_version`) to eliminate race conditions under concurrent returns.
  *File:* `src/monitoring/service.py`, `tests/monitoring/test_monitoring.py` (`TC-M5-003`, `TC-M5-013`, `TC-M5-014`).
- **Event-driven periodic checks via SensorHeartbeat**: Periodic monitoring tasks (`check_heartbeat_timeouts`, `check_overdue_vehicles`, `check_vehicle_deficits`, `check_and_escalate_unacknowledged`) are triggered automatically by incoming `SensorHeartbeat` events via `run_periodic_checks()`. Incidents are deduplicated against all active lifecycle statuses (`OPEN`, `IN_PROGRESS`, `ESCALATED`), ensuring continuous autonomous surveillance without out-of-band threads.
  *File:* `src/monitoring/service.py`, `tests/monitoring/test_monitoring.py` (`TC-M5-006`, `TC-M5-007`, `TC-M5-008`, `TC-M5-009`).
<!-- END M5: Monitoring & Incident Handling -->

<!-- BEGIN M6: What-if Simulation -->
#### Technical Decision 1: Sandbox Isolation via CoreFacade over OperationalSnapshot (NFR-12)
- **Problem:** Executing hypothetical what-if scenarios could accidentally mutate live Core entities or persistent state store.
- **Implementation:** M6 imports `OperationalSnapshot` from `core` and instantiates a standalone sandbox environment via `CoreFacade` backed by an in-memory repository derived from the snapshot (`snapshot.to_repository()`).
- **Rationale:** Ensures strict memory isolation without complex ORM transaction rollbacks, guaranteeing zero state leakage to operational data.
- **Traceability:** `src/simulation/service.py`, verified by `tests/simulation/test_simulation_engine.py::TestSimulationEngineIntegration::test_nfr12_state_isolation`.

#### Technical Decision 2: Deterministic Stochastic Event Generation (NFR-13)
- **Problem:** Stochastic event simulation (e.g., random student rental requests) produced non-repeatable metrics during regression testing and benchmarking.
- **Implementation:** Bound all random state transitions and demand surge generation to an isolated instance of `random.Random(seed)` initialized with `SimulationConfig.random_seed`.
- **Rationale:** Guarantees 100% deterministic outputs for auditability, comparative benchmarking on `DS-STD`, and reproducible recommendations.
- **Traceability:** `src/simulation/engine.py`, verified by `tests/simulation/test_simulation_engine.py::TestSimulationEngineIntegration::test_nfr13_reproducibility`.
<!-- END M6: What-if Simulation -->

## 4.4 Deviations and Implementation Limitations

Write: one table for the whole team. Every row says what the design said, what the code does, why, and the effect. Work not finished at 23:59 on 17/11 goes here and is left out of the demo (`task-assignment-timeline.md`, Phase 3+4 cut-off rule).

| ID | Module | Design or brief said | Implementation does | Reason | Effect / follow-up |
|---|---|---|---|---|---|
| DEV-01 | M1, M8 | NFR-02/03 under 100 concurrent sessions | Measured with sequential requests over DS-STD (D-024) | No load-test tool could be built before the code freeze | No figure for concurrent load; correctness under concurrency is covered by NFR-06 tests |
| DEV-02 | M4 | Task and its vehicles in a separate table | `vehicle_ids` is one comma-separated text column (Section 3.2.2) | `DispatchTask` is a short-lived operational aggregate representing a single batch rebalance; storing `assigned_vehicles` as a delimited string inside the single registered `dispatch_tasks` table eliminated multi-table joins and separate entity registration (`register_entity`), keeping SQLite writes atomic under Core's single-table UoW and matching the lightweight in-memory schema (D-018). | Database-level foreign keys cannot validate individual vehicle IDs in the string; integrity is enforced in application logic by validating vehicle existence and state before task approval (`_validate_approval_resources`). |
| DEV-03 | M1 | Brief: a distributed operational environment | One process; Hubs and modules are separated logically (A-08, Section 3.1.7) | Size of the project and the team | Failures of the network between Hubs are not modelled |
| DEV-04 | M4 | Real-time map-based vehicle routing during dispatch | Pure hub-to-hub relocation without in-transit GPS tracking | Assumptions A-01 and A-02 define trips and relocations as hub-to-hub transitions without spatial routing or traffic simulation. | Dispatch transit duration is modelled as an atomic transition from source pickup to destination return; in-transit intermediate coordinates are not stored. |
| DEV-05 | M3 | FR-06.3: thresholds for modifying and cancelling a reservation | Modify and cancel are allowed at any time before the start; only "new start not in the past" is checked; modify works on `SCHEDULED` requests only | Not done before the code freeze | A user can cancel at the last minute; a notice period can be added as a Core config value |
| DEV-06 | M3 | FR-11.M3.2: prevent overload of the Hub's power supply | `optimize_queue` binds requests to the earliest free slot in priority order; there is no power limit per Hub | Core has no power budget per Hub, only `power_rate_kw` per charging point | Overload of a Hub is not prevented |
| DEV-07 | M3 | A request keeps the start time and length the user asked for | A request that finds no bay, immediate or scheduled, becomes `QUEUED` without a start or end; `optimize_queue` later binds it from the current time for 60 minutes | The queue only stores the request, not the requested window | A queued scheduled request can be bound earlier than asked and for the wrong length |
| DEV-08 | M6 | Execute standard simulation scenarios SC-01 through SC-05 | SimulationEngine only implements demand-surge logic (`run_demand_surge()`); `SimulationConfig.parameters` only accepts `DemandSurgeParams`. Passing SC-02 through SC-05 still executes the demand-surge logic and labels the report with the chosen scenario_id | Time and scope constraints prior to Phase 3-4 code freeze | The UI and demo must offer SC-01 only to avoid misleading users; full dynamic scenario execution is deferred to future release phases |
| DEV-09 | M5 | Automated overdue vehicle incident generation (INC-USR-01) | Calls `ProviderPort.RESERVATION_DEMAND.open_trips()`; returns empty when provider is missing | M2 `ReservationDemand` port not yet registered in develop at code cut-off | INC-USR-01 tickets generated once M2 registers port; verified via mock provider in unit test |
| DEV-10 | M7 | S4 makes the rental; S5 lists the student's bookings and picks up, cancels and returns | S4 shows the real Hub and vehicle, but Reserve leads to S5, which shows sample data | M2 offers a service only: no router and no function that lists a student's bookings | S4 (the reservation step) and S5 are left out of the demo; connect when M2 has a route |
| DEV-11 | M7 | O6 runs the five standard scenarios and sends an approved recommendation to M4 | O6 shows sample data | M6's router was not in `develop` when this row was written (open PR) and only the demand surge exists | O6 is left out of the demo until the route is merged; the other scenarios stay planned |
| DEV-12 | M7 | S8 changes and cancels charging; O3 lets an operator act on the queue; O4 rejects tasks and edits M4's settings; O2 acts on vehicles and points | S8 requests or schedules for a private EV only, with no change or cancel; O3 is read-only; O4 has no Reject and no settings panel; O2 shows state only | M3 gives no time limit for change and cancel and no owner or priority in its queue; M4 has no reject route; the rest was not built before the cut-off | The student cannot change a slot, and the operator cannot change the queue, reject a task or act on a vehicle from the UI |
| DEV-13 | M7 | Lists can be filtered, S3 sorts by battery, O5 shows ticket history, actions ask for confirmation, and each refusal has its own message and alternative | None of these: the action is sent at once, and the error block shows the module's own cause, its code and a link back (`explain` in `src/ui/api.py`) | Not needed for the demo paths; module messages are short developer texts | Users read the full lists; a refusal may read like developer text and offers no other Hub, time or port |

Rows to check on 17/11 and add if still true: M2 `ReservationDemand` not registered; M3 step 3 of BR-M3-02 (call to M4) missing; M6 scenarios SC-02 to SC-05.
