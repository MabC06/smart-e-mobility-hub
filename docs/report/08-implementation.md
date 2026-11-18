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
| `ui` | M7 | Operator and student screens | ≈ 760 |
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
<!-- M4 writes here by 17/11. -->
<!-- END M4: Resource Allocation & Dispatching -->

<!-- BEGIN M5: Monitoring & Incident Handling -->
<!-- M5 writes here by 17/11. -->
<!-- END M5: Monitoring & Incident Handling -->

<!-- BEGIN M6: What-if Simulation -->
<!-- M6 writes here by 17/11. -->
<!-- END M6: What-if Simulation -->

## 4.4 Deviations and Implementation Limitations

Write: one table for the whole team. Every row says what the design said, what the code does, why, and the effect. Work not finished at 23:59 on 17/11 goes here and is left out of the demo (`task-assignment-timeline.md`, Phase 3+4 cut-off rule).

| ID | Module | Design or brief said | Implementation does | Reason | Effect / follow-up |
|---|---|---|---|---|---|
| DEV-01 | M1, M8 | NFR-02/03 under 100 concurrent sessions | Measured with sequential requests over DS-STD (D-024) | No load-test tool could be built before the code freeze | No figure for concurrent load; correctness under concurrency is covered by NFR-06 tests |
| DEV-02 | M4 | Task and its vehicles in a separate table | `vehicle_ids` is one comma-separated text column (Section 3.2.2) | — (M4 fills in) | The database cannot check the vehicle IDs |
| DEV-03 | M1 | Brief: a distributed operational environment | One process; Hubs and modules are separated logically (A-08, Section 3.1.7) | Size of the project and the team | Failures of the network between Hubs are not modelled |
| DEV-05 | M3 | FR-06.3: thresholds for modifying and cancelling a reservation | Modify and cancel are allowed at any time before the start; only "new start not in the past" is checked; modify works on `SCHEDULED` requests only | Not done before the code freeze | A user can cancel at the last minute; a notice period can be added as a Core config value |
| DEV-06 | M3 | FR-11.M3.2: prevent overload of the Hub's power supply | `optimize_queue` binds requests to the earliest free slot in priority order; there is no power limit per Hub | Core has no power budget per Hub, only `power_rate_kw` per charging point | Overload of a Hub is not prevented |
| DEV-07 | M3 | A request keeps the start time and length the user asked for | A request that finds no bay, immediate or scheduled, becomes `QUEUED` without a start or end; `optimize_queue` later binds it from the current time for 60 minutes | The queue only stores the request, not the requested window | A queued scheduled request can be bound earlier than asked and for the wrong length |

Rows to check on 17/11 and add if still true: M2 `ReservationDemand` not registered; M3 step 3 of BR-M3-02 (call to M4) missing; M5 `SensorEventRejected` and heartbeat not handled; M6 scenarios SC-02 to SC-05; M7 UI still on `ui.sample_data`.
