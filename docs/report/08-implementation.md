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
<!-- M3 writes here by 17/11. -->
<!-- END M3: Charging & Smart Scheduling -->

<!-- BEGIN M4: Resource Allocation & Dispatching -->
<!-- M4 writes here by 17/11. -->
<!-- END M4: Resource Allocation & Dispatching -->

<!-- BEGIN M5: Monitoring & Incident Handling -->
Draft points for M5:
- **Decoupled incident ingestion via Core EventBus**: M5 consumes only Core's domain events (`ChargingPointStatusChanged`, `VehicleBatteryChanged`, `SensorEventRejected`, `SensorHeartbeat`), never importing `iot_sim` directly (NFR-22, D-004). Telemetry liveness is tracked in an internal timestamp map (`_heartbeats`) to detect connection loss (> 30s) deterministically.
  *File:* `src/monitoring/service.py:193-338`, `tests/monitoring/test_monitoring.py` (`TC-M5-001`, `TC-M5-002`, `TC-M5-006`).
- **Deterministic escalation timer on injectable clock**: `BR-M5-04` requires unacknowledged `HIGH`/`CRITICAL` tickets to auto-escalate after 5 minutes. Rather than relying on OS daemon threads and wall-clock time, `check_and_escalate_unacknowledged` computes ticket age against `core.queries.get_config().as_of` (`FixedClock`, D-005), preserving deterministic replayability (NFR-13).
  *File:* `src/monitoring/service.py:403-421`, `tests/monitoring/test_monitoring.py` (`TC-M5-008`).
- **Concurrency-safe capacity status synchronization**: Evaluates Hub parking occupancy upon `SpaceOccupancyChanged` (`BR-M5-01`, `BR-M5-02`), transitioning Hub status through `core.commands.set_hub_status` using optimistic version checks (`expected_version`) to eliminate race conditions under concurrent returns.
  *File:* `src/monitoring/service.py:118-176`, `tests/monitoring/test_monitoring.py` (`TC-M5-003`, `TC-M5-013`, `TC-M5-014`).
- **Relational schema integrity fallback for sensor rejections**: Sensor intake rejections (`SensorEventRejected`) may carry unrecognized entity IDs; `_default_hub_id()` maps unresolvable sensors to the primary active Hub, preventing foreign key constraint violations in SQLite (`hubs.hub_id`, D-018, D-022) while guaranteeing complete fault audit trails.
  *File:* `src/monitoring/service.py:74-76, 269-278`, `tests/monitoring/test_monitoring.py` (`TC-M5-002`).
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

Rows to check on 17/11 and add if still true: M2 `ReservationDemand` not registered; M3 step 3 of BR-M3-02 (call to M4) missing; M6 scenarios SC-02 to SC-05; M7 UI still on `ui.sample_data`.
