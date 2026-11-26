# 4. Implementation

> **Status:** Final v1.0 · **Owner:** M1 (4.1, 4.2, 4.3.1; consolidates 4.3 and 4.4) · **Date:** 2026-11-26
> This section explains how the design of Section 3 became code and which choices were not obvious; it links to Section 3 instead of repeating it. Each module owner wrote their part of 4.3 and 4.4.

## 4.1 Technology Stack and Development Environment

| Concern | Choice (pinned version) | Why |
|---|---|---|
| Language | Python 3.12, pip + venv with pinned `requirements*.txt` | One language for every module and the tests; runs from a clean clone (NFR-14). |
| Web API | FastAPI 0.162 with Pydantic 2.14, served by uvicorn 0.54 | Request and response types are checked from the same models as the core interface; OpenAPI pages come for free. |
| Database | SQLite through SQLAlchemy 2.1 Core | No server to install (NFR-14); PostgreSQL stays an upgrade path (Section 3.1.7); foreign keys on, write-ahead log; tests use an in-memory store with the same `Repository` interface. |
| Web UI | Jinja2 3.1 templates and HTMX, rendered by the server | Replaced the React + Vite proposal (D-002): no Node toolchain; M7 agreed. |
| Authentication | PBKDF2-SHA256 hashes and HMAC-signed bearer tokens, inside `core` | Standard library only; no external identity service (D-014, A-06). |
| Quality tools | pytest 9.2, pytest-cov 7.1, ruff 0.17, mypy 2.4 (strict on `core`, `reservation`, `main.py`) | The same commands run on a laptop and in CI (D-019, D-025). |
| CI | GitHub Actions on Ubuntu | Lint, format, types, tests, coverage per module and the import-boundary check on every PR (NFR-22, NFR-24, NFR-27). |

The whole system runs as one process: `python -m uvicorn --app-dir src main:create_app --factory`. Settings come from `.env` (`APP_ENV`, `DATABASE_URL`, `SECRET_KEY`, `SEED_ON_START`, `DEMO_PASSWORD`; see `.env.example`); an empty `DATABASE_URL` gives an in-memory store. With `SEED_ON_START=true` an empty database is loaded with the DS-STD network of the simulator, and the seeded accounts can sign in with the demo password (D-028). Five documented commands take a fresh clone to a running, tested system (NFR-14).

Every timestamp is UTC and comes from an injectable clock (D-005), so tests and What-if runs are repeatable (NFR-13); the screens show times in ICT. The system uses no external service or paid API: the IoT layer is the simulator in `src/iot_sim/` (D-004).

Work was done on short branches from `develop`, one pull request per change, merged after one approval and a green CI run (CONTRIBUTING section 8, D-001); `main` receives `develop` at each release.

## 4.2 Implementation Structure

Section 3.1 maps to code as one Python package per component under `src/`, wired together by `main.py`.

### 4.2.1 Packages and owners

| Package (`src/`) | Owner | Realizes (Section 3) | Lines of Python (2026-11-26) |
|---|---|---|---|
| `core` | M1 | Shared state, state machine, claims, events, snapshot, REST API, sign-in | 5,288 |
| `reservation` | M2 | Rental and parking reservations, trips, return-space holds | 1,726 |
| `charging` | M3 | Charging requests, queue and schedule, point failures | 1,403 |
| `allocation` | M4 | Dispatch plans, arbitration, alternative Hubs | 1,945 |
| `monitoring` | M5 | Hub status, incidents and escalation | 1,196 |
| `simulation` | M6 | What-if engine on a snapshot, SC-01 to SC-05 | 670 |
| `ui` | M7 | Operator and student screens (plus Jinja2 templates and one stylesheet) | 1,393 |
| `iot_sim` | M8 | Sensor events and seed network (outside the system boundary, D-004) | 236 |
| `main.py` | M1 | Composition root (D-013), settings, seeding | 316 |

The sizes only show where the logic is; the tests (about 1,560) are in `tests/`, one folder per package.

### 4.2.2 Inside `core`

The layers of `core` follow the class diagram (Section 3.2.1):
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

- REST: the core router (`/auth/login`, `/me`, `/hubs`, `/config`) and one router per module (`/reservations`, `/charging`, `/allocation`, `/api/v1/monitoring`, `/simulation`), all behind the same token check (NFR-16, D-014, D-023). The pages of `ui` are under `/ui` and call these routes (D-026). The full list is the OpenAPI page at `/docs`.
- Events: in-process `EventBus`, published only after a commit; a failing handler is logged and does not undo the commit (`core/events.py`). The main events are `SpaceOccupancyChanged` and `VehicleBatteryChanged` (M5), `ChargingPointStatusChanged` (M3 and M5), `SensorEventRejected` and `SensorHeartbeat` (M5, which runs its periodic checks on the heartbeat).
- Provider ports: `core` calls a module only through a port that the module registered (§6.1), so the dependency still points into `core`.

### 4.2.6 Simulation subsystem

- M6 takes an `OperationalSnapshot` (one commit point, copies only, content hash as ID), loads it into an in-memory store and runs the scenario there (NFR-12). The live store is never written.
- The five scenarios, their metrics and the recommendation rules are designed in Section 3.5; the isolation and determinism choices are in 4.3.6.

## 4.3 Important Implementation Decisions

Each module owner describes the decisions that were hard or not obvious: the problem, what the code does, why, and where (file, test). The rubric's examples are covered as follows:

| Rubric example | Covered by |
|---|---|
| Maintaining consistent resource state | M1 (claims, unit of work, invariant checker) |
| Resolving reservation conflicts | M2, and M4 for competing requests |
| Processing failures | M3 (charging-point failure), M5 (incidents), M1 (rejected sensor events) |
| Synchronizing state updates | M1 (lock, optimistic version, events after commit) |
| Implementing charging allocation | M3, and M4 for alternatives |
| Isolating simulated state from operational state | M6 |

<!-- BEGIN M1: Core -->
### 4.3.1 M1 — Core

1. **One owner of shared state, with claims.** Problem: reservation, charging and dispatch all want the same vehicle, space or charging point, sometimes for overlapping times. Code: a module asks `core` for an interval claim on a resource (`domain/claims.py`); `core` refuses any overlap (BR-M1-01), and only the module that placed a claim releases or consumes it. `core` never expires a claim itself: the owner does, because only the owner knows its deadlines (D-017). Where: `services/commands.py`, `tests/core/test_claims.py`, `test_commands_claims.py`.
2. **One lock, a unit of work and an optimistic version.** Problem: a pick-up changes the vehicle, the space and the reservation together, and two students can try the same vehicle at once (NFR-06, NFR-09). Code: every write runs inside a unit of work under one runtime lock (`services/runtime.py`); on SQLite the transaction starts with `BEGIN IMMEDIATE`, each command runs in a savepoint, and each entity carries a `version` that a command must match or it fails with `VERSION_CONFLICT`. M4 plans on a snapshot and commits with its `snapshot_version`, so a plan made on old data is refused. Where: `services/unit_of_work.py`, `repository/sql.py`, `tests/core/test_concurrency.py` (42 tests), `test_unit_of_work.py`.
3. **Events only after commit.** Problem: a subscriber that reacts to a change must never see a change that is later rolled back. Code: the unit of work collects events and publishes them only after the commit; a failing handler is logged and does not undo the commit (`events.py`). Where: `tests/core/test_queries_events.py`.
4. **Faulty sensor input is refused as a whole.** Problem: the simulator can send malformed or impossible events (NFR-10). Code: `SensorIntake` checks an event completely before applying it; a bad event changes nothing and is published as `SensorEventRejected`, which M5 turns into an incident. Where: `services/sensor_intake.py`, `tests/core/test_sensor_events.py`.
5. **IDs that survive a restart, and no command-result store.** Problem: after a restart on SQLite, new IDs collided with stored ones, and a retried request must not create a second record. Code: the ID generator resumes above the highest stored suffix (D-022); idempotency is kept by each module from its own records (M2 looks up its reservation, D-015), so `core` stores no command results. Where: `ids.py`, `tests/core/test_id_recovery.py`.
<!-- END M1: Core -->

<!-- BEGIN M2: Reservation & Trip -->
### 4.3.2 M2 — Reservation and Trip

1. **Serializing admission across different resources.** A vehicle version
   detects a stale update to one vehicle, while a student can attempt to reserve
   two different vehicles at once. `BookingService._reserve` checks the
   student's live rental quota and the resource claim under the same Core
   unit-of-work lock before writing. The lock serializes admission in the
   single-process deployment. Core's expected vehicle version still protects
   a mutation based on a prior read. See
   [service.py](../../src/reservation/service.py) and TC-M2-006/014/015/019.
2. **Making retries safe after commit or restart.** M2 looks up the reservation
   resource ID and verifies the owner and original booking fields before
   issuing commands (D-015). Pickup has a stable Trip ID for each reservation.
   Return retries for the completed trip and same destination read the stored
   receipt. The records and uniqueness constraints keep retries from creating a
   second Trip. SQLite restart testing also exposed reuse of persisted Core
   identifiers, addressed by restoring the default ID counters under D-022.
   See [service.py](../../src/reservation/service.py),
   [storage.py](../../src/reservation/storage.py),
   [ids.py](../../src/core/ids.py) and TC-M2-008/009/013/021.
3. **Keeping reservation, trip and shared resources consistent.** Reserve,
   pickup, return and unused-booking release write M2 records and request
   Core commands in a single unit of work (D-018). Pickup releases actual
   origin occupancy as the vehicle departs. If the destination is full or
   a live or future claim excludes the available space, return leaves the
   trip open. Claim or storage failures roll back the whole operation and
   successful events are published only after commit. See
   [service.py](../../src/reservation/service.py),
   [lifecycle.py](../../src/reservation/lifecycle.py) and
   TC-M2-001/010/011/012/023.
4. **Settling unused holds at an exact deadline.** Core time determines
   whether an unused booking can be picked up or cancelled (D-005/D-017).
   Pickup requires `now < hold_expires_at`. Cancellation at or after
   that boundary settles expiry. An explicit maintenance sweep can settle
   due confirmed bookings even when an owner is disabled, with a separate
   transaction and result for each booking. Release preserves physical
   occupancy and an already-faulty vehicle's Maintenance state. The same
   lock orders a racing pickup and cancel. See
   [lifecycle.py](../../src/reservation/lifecycle.py) and TC-M2-007/023.
5. **Keeping authentication and ownership checks consistent at the API.**
   [PR #54](https://github.com/MabC06/smart-e-mobility-hub/pull/54) mounts the
   reserve, pickup, cancel, return and list routes under `/reservations`.
   Each route uses Core's `require_student` and derives its actor from the
   authenticated principal (D-023). `GET /reservations/mine` reads the
   student's bookings, open trips and observed vehicle versions in one unit of
   work. The router gives foreign and missing records the same 404 response.
   State or version conflicts return 409, internal operation failures return
   500 and repository failures while listing bookings return 503. TC-M2-024
   and TC-M2-025 exercise the routes with Core-issued tokens and SQLite.
6. **Expiring bookings without a scheduler.** The application runs no
   background job, so a booking nobody picked up stayed Confirmed and blocked
   its student with LIMIT_REACHED. Each route now checks the student and then
   runs `RentalLifecycle.sweep()`: due bookings expire (D-017) and open Trips
   past due + 60 min become `OVERDUE` (BR-M2-15), each in its own unit of work.
   `GET /reservations/vehicles` searches the rentable vehicles of a Hub with the
   same eligibility rule as reserve (FR-02, BR-M2-02). TC-M2-027 to TC-M2-029.
7. **Parking through Core claims.** `ParkingService` (`parking.py`) keeps one
   `ParkingBooking` per held space. A return hold or a private stay places a
   Core claim on an empty space with no other commitment in its interval; the
   return or the arrival passes that claim to `transition_vehicle`, which
   consumes it while parking the vehicle, so a held space can never be given
   to someone else. Cancel and expiry release only the claim; departure frees
   the space through Core (BR-M2-05, BR-M2-11). TC-M2-030 to TC-M2-032.

<!-- END M2: Reservation & Trip -->

<!-- BEGIN M3: Charging & Smart Scheduling -->
### 4.3.3 M3 — Charging and Smart Scheduling

- **Charging allocation with claims.** Problem: two sessions must never share a bay in the same interval, and a bay must be found even when the requested time is taken. Code: `_earliest_slot` tries start times every 15 minutes for up to 2 hours; `_bind_bay` places a `CHARGING_SESSION` claim on the charging point and one on the vehicle, and finish, interrupt and cancel release them (D-017). Why: Core's claim check rejects overlaps, so the rule is enforced in one place and not by M3's own bookkeeping. Where: `src/charging/service.py`; TC-M3-022 to TC-M3-026.
- **One unit of work per queued request.** Problem: `_bind_bay` commits, and a commit closes the unit of work, so binding a whole queue in one unit of work failed on the second request (DEF-M3-002). Code: `optimize_queue` ranks the queue first, then binds each request in its own `_run`. Why: a failure on one request leaves the others bound, and no half-placed claims remain. Where: `optimize_queue`; TC-M3-024, TC-M3-025.
- **Charging-point failure.** Problem: a failed point must not leave a session running or a future session bound to it. Code: M3 subscribes to `ChargingPointStatusChanged`; for `OUT_OF_SERVICE` or `MAINTENANCE` it interrupts the session on that point and submits a new request `<id>-R<n>` for the same vehicle and owner (because `INTERRUPTED` is a final state), moves the `SCHEDULED` sessions of that point, then runs `optimize_queue`. Why: the event comes from Core, so M3 reacts the same way whether M5 or an operator changed the status. Where: `_on_point_status_changed`, `_resubmit_after_failure`; TC-M3-027 to TC-M3-029.
- **Alternative Hub through M4.** Problem: when the Hub has no slot within 2 hours, the request should go to another Hub (BR-M3-02, step 3). Code: `optimize_queue` calls `ProviderPort.ALTERNATIVE_CHARGING`; M4 only suggests, so M3 checks the suggested Hub's bays again in the same unit of work, prefers M4's bay and binds the request there. If M4 finds nothing or is not installed, the request stays `QUEUED`. Why: M4's answer is read-only and may be out of date by the time M3 binds. Where: `_alternative_hub_bay`; TC-M3-034 to TC-M3-036.
- **Priority with a fallback.** Problem: the booking factor needs M2's data, which may be missing. Code: `compute_priority_queue` ranks by emergency (SoC at or below Core's `low_battery_threshold`), then a booking at that Hub in the next hour (`RESERVATION_DEMAND`), then lowest SoC, then request time; if the port returns an error, it ranks by battery only. Why: charging must keep working when M2 is down. Where: `compute_priority_queue`; TC-M3-001 to TC-M3-005.
<!-- END M3: Charging & Smart Scheduling -->

<!-- BEGIN M4: Resource Allocation & Dispatching -->
### 4.3.4 M4 — Resource Allocation and Dispatching

- **Consistent resource state across dispatch lifecycle (BR-M4-04, D-017):** Dispatch tasks require atomic co-allocation of suitable fleet vehicles at the source hub and parking spaces at the destination hub. `approve_task()` places `HolderKind.DISPATCH_TASK` claims on both resources inside one atomic unit of work (`src/allocation/service.py`). If any claim fails, placed claims are released and `_mark_task_failed()` runs in a separate external UoW so failure transitions complete cleanly without nested transaction errors (`tests/allocation/test_review.py`). When completing return, `carry_out_return()` passes `parking_space_id` and `claim_id` from the active space claim into `TransitionCtx` for `VehicleEvent.RETURN` and releases remaining active task claims.
- **Resolving competing resource requests under scarcity (BR-M4-01, UC-M4-06):** When multiple concurrent demands compete for the same scarce vehicle or bay space, `ArbitrationService.arbitrate()` sorts requests strictly by priority class tier (`OPERATOR_INCIDENT > RESERVATION_PICKUP > VEHICLE_RETURN > CHARGING > REBALANCE > WALK_IN`), breaking ties deterministically by `requested_at` ascending and request ID (`src/allocation/arbitration.py`, `tests/allocation/test_arbitration.py`). The winning request is granted the resource atomically, while displaced requests receive typed errors with explicit reason codes (`ErrorCode.RESOURCE_UNAVAILABLE`).
- **Decoupled provider port integration without fallback stubs (D-020, NFR-22):** Rather than importing M2/M3 modules directly or falling back to silent empty mocks, `AllocationService._fetch_hub_demand()` queries `ProviderPort.RESERVATION_DEMAND` through Core's registry. A missing or failing port raises `RESOURCE_UNAVAILABLE` immediately (`src/allocation/service.py`). Conversely, M4 implements `AlternativeHubProvider` and `AlternativeChargingProvider` using frozen dataclass contracts (`src/core/providers.py`), verified by 25 import-boundary checks (`tests/test_import_boundaries.py`).
- **Injected clock time and RBAC authorization (D-005, D-023, NFR-16):** All time calculations read `core.queries.get_config().as_of` from Core's injectable clock instead of system wall-clock, ensuring deterministic rebalancing in simulation scenarios (M6). Every REST endpoint in `src/allocation/router.py` is protected by `Depends(require_operator)` and derives domain actors via `acting_as(principal, "allocation")` (`tests/allocation/test_api.py`).
<!-- END M4: Resource Allocation & Dispatching -->

<!-- BEGIN M5: Monitoring & Incident Handling -->
### 4.3.5 M5 — Monitoring and Incident Handling

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
### 4.3.6 M6 — What-if Simulation

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

Each row says what the design or the brief said, what the code does, why, and the effect. None of them blocks a workflow of the demo; the measured effects are in Section 5.

| ID | Module | Design or brief said | Implementation does | Reason | Effect / follow-up |
|---|---|---|---|---|---|
| DEV-01 | M1, M8 | NFR-02/03 under 100 concurrent sessions | Measured with sequential requests over DS-STD (D-024) | No load-test tool could be built before the code freeze | No figure for concurrent load; correctness under concurrency is covered by NFR-06 tests |
| DEV-02 | M4 | Task and its vehicles in a separate table | `vehicle_ids` is one comma-separated text column (Section 3.2.2) | `DispatchTask` is a short-lived operational aggregate representing a single batch rebalance; storing `assigned_vehicles` as a delimited string inside the single registered `dispatch_tasks` table eliminated multi-table joins and separate entity registration (`register_entity`), keeping SQLite writes atomic under Core's single-table UoW and matching the lightweight in-memory schema (D-018). | Database-level foreign keys cannot validate individual vehicle IDs in the string; integrity is enforced in application logic by validating vehicle existence and state before task approval (`_validate_approval_resources`). |
| DEV-03 | M1 | Brief: a distributed operational environment | One process; Hubs and modules are separated logically (A-08, Section 3.1.7) | Size of the project and the team | Failures of the network between Hubs are not modelled |
| DEV-04 | M4 | Real-time map-based vehicle routing during dispatch | Pure hub-to-hub relocation without in-transit GPS tracking | Assumptions A-01 and A-02 define trips and relocations as hub-to-hub transitions without spatial routing or traffic simulation. | Dispatch transit duration is modelled as an atomic transition from source pickup to destination return; in-transit intermediate coordinates are not stored. |
| DEV-05 | M3 | FR-06.3: thresholds for modifying and cancelling a reservation | Modify and cancel are allowed at any time before the start; only "new start not in the past" is checked; modify works on `SCHEDULED` requests only | Not done before the code freeze | A user can cancel at the last minute; a notice period can be added as a Core config value |
| DEV-06 | M3 | FR-11.M3.2: prevent overload of the Hub's power supply | `optimize_queue` binds requests to the earliest free slot in priority order; there is no power limit per Hub | Core has no power budget per Hub, only `power_rate_kw` per charging point | Overload of a Hub is not prevented |
| DEV-07 | M3 | A request keeps the start time and length the user asked for | A request that finds no bay, immediate or scheduled, becomes `QUEUED` without a start or end. Since 25/11 the route then runs `optimize_queue` for the Hub at once, and again after a cancel, finish or stop, so a request stays `QUEUED` only while no slot is free in the next 2 hours (TC-M3-039); `optimize_queue` binds it from the current time for 60 minutes | The queue only stores the request, not the requested window | A queued scheduled request can be bound earlier than asked and for the wrong length |
| DEV-08 | M6 | Execute standard simulation scenarios SC-01 through SC-05 with discrete time steps | All five scenarios run (TC-M6-006 to 010), each as a count over the whole horizon per Hub, not step by step; the report gives the baseline and the mitigated rate after applying every recommendation (FR-12.6) | A count model was enough to compare plans before the code freeze | `time_step_minutes` is checked but not used to evolve the state; battery drain and charging progress during the horizon are not modelled |
| DEV-09 | M5 | Automated overdue vehicle incident generation (INC-USR-01) | The periodic checks, run on each `SensorHeartbeat`, read open Trips through `ProviderPort.RESERVATION_DEMAND.open_trips()` and open one LOW ticket per overdue Trip; if the port is missing the check returns nothing | The port was not registered at the code cut-off; M2 registered it in PR #54 | Works with M2's real provider; the unit test uses a mock provider (TC-M5-007) |
| DEV-10 | M7 | S4 makes the rental; S5 lists the student's bookings and picks up, cancels and returns, holds a return space and shows a return receipt | S3 to S6 call M2's routes: search, reserve, pick up, cancel, return, return-space hold and private parking. After a return S5 lists the booking as `COMPLETED`; there is no separate receipt screen | The return result is shown in the list | The student sees the Hub of a return in the booking, not a receipt with the space |
| DEV-11 | M7 | O6 runs the five standard scenarios and sends an approved recommendation to M4 | O6 runs SC-01 to SC-05 and shows the rate with and without the plan. A vehicle redistribution can be approved (M4 makes a RECOMMENDED task for O4) or rejected; a charging shift or return redirection links to O3 or O2 instead | M3 and M2 have no route that takes such a recommendation | The operator acts on a charging or return recommendation by hand |
| DEV-12 | M7 | S8 changes and cancels charging; O3 lets an operator act on the queue; O4 rejects tasks and edits M4's settings; O2 acts on vehicles and points | All of these are connected. O3 can optimize the queue and start, finish or stop sessions, but cannot move one request up the queue by hand | M3 orders the queue by BR-M3-03 only; a manual override was left to be confirmed with M3 (UC-M7-04) | An urgent vehicle is put first only by the rule, not by the operator |
| DEV-13 | M7 | Lists can be filtered, S3 sorts by battery, O5 shows ticket history, actions ask for confirmation, and each refusal has its own message and alternative | Filters on S3, O1 to O5; S3 sorted by battery; O5 history. Actions are sent at once, and the error block shows the module's own cause and code | Module messages are short developer texts | A click sends the action without a confirmation step; a refusal may read like developer text |
| DEV-14 | M2 | Students search for eligible fleet vehicles and complete the rental journey (UC-M2-01 to UC-M2-05) | PR #54 exposes the rental operations and the student's bookings and open trips. `GET /reservations/vehicles` (FR-02) lists the rentable fleet vehicles of one Hub, filtered by type and minimum battery and sorted by battery. An empty result is an empty list: there is no NO_VEHICLE code and no alternative Hub | Alternatives come from M4, and M2 does not call M4 (DEV-16) | When a Hub has no rentable vehicle the student chooses another Hub in S2. Search and rental are covered by TC-M2-024, 025 and 027 |
| DEV-15 | M2 | FR-05 and the parking part of FR-07 include parking holds, private arrival/departure and coordination with charging | An open Trip can hold an empty space of its destination for 10 min and the return uses it; a private EV can book a space up to 24 h ahead for 30 to 240 min, arrive in its 10-min window, depart, cancel, and expire (TC-M2-030 to 032). There is no parking/charging bundle (BR-M2-12), no move to another space when the held one is taken, and no overstay notice to M5 | The bundle needs one joint M2/M3 command and the move needs a claim transfer in Core | A private EV books parking and charging separately; a parked EV past its planned end stays ACTIVE and S6 shows the overstay |
| DEV-16 | M2 | M2 provides demand and hold data through the D-020 ports and can use M4 for alternatives | PR #54 registers the read-only `ReservationDemand` provider for live pickup holds and open trips. `HoldConsumer` is unregistered and M2 makes no call to M4 for an alternative Hub | Rental demand can be read from M2 tables. Coordinated hold consumption and alternative selection remain separate integration work | Consumers can read real rental demand. They cannot consume an M2 hold through that port, and an unsuccessful rental does not produce an M4 Hub suggestion |
| DEV-17 | M2 | Due uncollected rentals are processed; pre-pickup faults and overdue trips are handled across modules (BR-M2-04/14/15) | There is no scheduler: every M2 route first runs `RentalLifecycle.sweep()`, which expires due bookings and marks open Trips past due + 60 min as `OVERDUE` (TC-M2-028, 029). Pickup refuses expired/ineligible vehicles. An owner cancellation or expiry can settle an unused faulty vehicle while retaining Maintenance and its bay. Faulty in-use return is implemented | The application has no background job; running the sweep on each request needs none | A due booking stays Confirmed until any student calls M2, and the providers read by M4 and M5 see it until then. There is no automatic pre-pickup fault settlement |
