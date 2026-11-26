# M4 Allocation & Dispatching Test Cases

> **Owner:** M4 — 2412466 Huỳnh Minh Nhật · **Updated:** 2026-11-17  
> **Test folder:** `tests/allocation/` · **Requirements:** `docs/requirements/fr-10-11-allocation.md`

The allocation test suite exercises the pure redistribution planner (`allocation.planner`),
competing-request arbitrator (`allocation.arbitration`), alternative hub and charging providers
(`allocation.alternatives`), dispatch lifecycle service (`allocation.service`), and operator-only
REST API (`allocation.router`) against the real `CoreFacade` and `InMemoryRepository`. External
`ReservationDemand` inputs are registered cleanly via `core.register_provider` on a fresh core per
test without mutating private Core fields.

## Execution

From the repository root, install `requirements-dev.txt`, then run:

```text
python -m pytest tests/allocation -q
python -m pytest tests/allocation -q --cov=allocation --cov-fail-under=60
ruff check .
ruff format --check .
mypy
```

Every test case maps directly to a registered pytest marker in `pyproject.toml`; for example:

```text
python -m pytest -m tc_m4_018 -q
```

Parametrized test instances retain the same `TC-M4-###` ID and expose the input partition or
endpoint in their pytest node IDs.

## Traceability

Technique abbreviations follow `docs/testing/test-technique-assignment.md`:
`EP` (Equivalence Partitioning), `BVA` (Boundary Value Analysis), `DT` (Decision Table),
`ST` (State-Transition), `CT` (Conflict / Concurrency), `FI` (Failure Injection),
`DET` (Determinism), `SEC` (Security / Authorization), `INT` (Integration / Contract),
`STATIC` (Static architecture check).

| TC ID / marker | Test file(s) | Verifies | Technique | Expected result |
|---|---|---|---|---|
| TC-M4-001 / `tc_m4_001` | `test_planner.py` | FR-10.1, FR-10.2, FR-10.3, UC-M4-01, BR-M4-03, BR-M4-05, BR-M4-06 | EP / DT | Worked 4-hub example produces the 3 expected tasks (`H05->H08` qty 5, `H03->H01` qty 4, `H05->H01` qty 2). |
| TC-M4-002 / `tc_m4_002` | `test_planner.py` | FR-10.1, FR-10.2, UC-M4-01 | EP | Balanced network with zero deficit yields an empty task list. |
| TC-M4-003 / `tc_m4_003` | `test_planner.py` | FR-10.2, UC-M4-01, BR-M4-05 | BVA | Source hub retains at least safety stock `S` available vehicles after proposed dispatch. |
| TC-M4-004 / `tc_m4_004` | `test_planner.py` | FR-10.3, FR-11.M4.3, UC-M4-01, BR-M4-04 | BVA | Destination hub retains at least parking buffer `B` free spaces after proposed dispatch. |
| TC-M4-005 / `tc_m4_005` | `test_planner.py` | FR-10.1, FR-10.3, UC-M4-01, BR-M4-03 | BVA | Vehicles below `min_dispatch_battery` are excluded; only eligible fleet vehicles are assigned. |
| TC-M4-006 / `tc_m4_006` | `test_planner.py` | FR-10.3, UC-M4-01, NFR-13 | DET | Repeated planning runs on identical state produce identical task IDs, quantities, and vehicle lists. |
| TC-M4-007 / `tc_m4_007` | `test_arbitration.py` | FR-11.M4.1, UC-M4-06, BR-M4-01, BR-M4-02 | DT / CT | Higher priority request class always beats lower priority regardless of arrival order. |
| TC-M4-008 / `tc_m4_008` | `test_arbitration.py` | FR-11.M4.1, UC-M4-06, BR-M4-01 | CT | Competing requests in the same class resolve first-come, first-served by `requested_at`. |
| TC-M4-009 / `tc_m4_009` | `test_arbitration.py` | FR-11.M4.1, UC-M4-06, BR-M4-01, NFR-13 | DET / CT | Identical class and timestamp break ties deterministically by lexicographically smaller `request_id`. |
| TC-M4-010 / `tc_m4_010` | `test_arbitration.py` | FR-11.M4.1, UC-M4-06, NFR-18 | BVA | Empty contender list returns `None` cleanly. |
| TC-M4-011 / `tc_m4_011` | `test_alternatives.py`, `test_review.py` | FR-10.6, FR-11.M4.2, UC-M4-05, UC-M4-07, D-020, NFR-22 | INT / STATIC | Alternative services implement Core provider Protocols with frozen, strictly typed DTOs exported from `core.providers` and register on `ProviderRegistry`. |
| TC-M4-012 / `tc_m4_012` | `test_alternatives.py` | FR-10.6, UC-M4-05, BR-M4-10, NFR-13 | DT / DET | Alternative hubs are ranked by closeness, available count, and battery with `reason_code="OK"` and `as_of` matching Core config. |
| TC-M4-013 / `tc_m4_013` | `test_alternatives.py` | FR-10.6, UC-M4-05, BR-M4-10, NFR-21 | EP | Missing requested vehicle type across all hubs returns empty candidates and `reason_code="NO_VEHICLE"`. |
| TC-M4-014 / `tc_m4_014` | `test_alternatives.py`, `test_review.py` | FR-10.1, FR-10.6, UC-M4-01, UC-M4-05, BR-M4-03, D-017 | DT / BVA | Private EVs (`Ownership.PRIVATE`) are excluded from fleet allocation and hub alternatives; expired `ACTIVE` claims (`end_at <= now`) do not block resources. |
| TC-M4-015 / `tc_m4_015` | `test_alternatives.py`, `test_review.py` | FR-10.3, FR-10.6, FR-11.M4.2, NFR-18 | EP / BVA | Blank IDs (`slot_id`, `requested_hub_id`, `hub_id`, `request_id`) and non-positive `limit` return `Err(ErrorCode.INVALID_INPUT)`. |
| TC-M4-016 / `tc_m4_016` | `test_alternatives.py` | FR-11.M4.2, UC-M4-07, BR-M3-02, BR-M4-10 | EP / CT | Displaced charging requests receive distinct free chargers at nearest hubs (`FOUND`), then `NO_CHARGER` once capacity is exhausted. |
| TC-M4-017 / `tc_m4_017` | `test_alternatives.py`, `test_review.py` | FR-11.M4.2, FR-11.M4.3, UC-M4-07, BR-M1-02, D-007 | DT / CT | Charging points whose bay space is occupied or actively claimed are skipped; invalid hub ID returns `INVALID_INPUT`. |
| TC-M4-018 / `tc_m4_018` | `test_service.py`, `test_review.py` | FR-10.4, FR-10.5, FR-11.M4.3, UC-M4-02, UC-M4-03, BR-M4-04, BR-M4-08, BR-M1-02, D-016, D-017, NFR-07, NFR-09 | ST / INT | Full lifecycle `RECOMMENDED -> APPROVED -> IN_PROGRESS -> COMPLETED`: atomic vehicle+space claims without manual version increment, `carry_out_return()` supplies space/claim ID via `TransitionCtx`, all claims released, zero invariant violations. |
| TC-M4-019 / `tc_m4_019` | `test_service.py` | FR-10.5, FR-11.M4.3, UC-M4-03, BR-M4-04, D-017, NFR-07 | CT / BVA | Return succeeds into the task's held destination space even when all other spaces at the destination hub are claimed externally. |
| TC-M4-020 / `tc_m4_020` | `test_service.py` | FR-10.5, UC-M4-04, BR-M4-04, BR-M4-08, D-017, NFR-07 | ST | Cancelling an approved task transitions status to `CANCELLED` and releases every held `DISPATCH_TASK` claim. |
| TC-M4-021 / `tc_m4_021` | `test_service.py` | FR-10.1, FR-10.3, FR-10.7, UC-M4-01, UC-M4-08, BR-M4-06 | EP / ST | `plan()` persists queryable recommended tasks; re-planning supersedes obsolete `RECOMMENDED` tasks without duplicates and caps tasks at `max_tasks_per_hub`. |
| TC-M4-022 / `tc_m4_022` | `test_service.py`, `test_review.py` | FR-10.1, UC-M4-01, D-020, NFR-10 | FI / INT | Missing, incomplete, failing, or exception-raising `ReservationDemand` provider makes `plan()` return `Err(ErrorCode.RESOURCE_UNAVAILABLE)` with no fallback. |
| TC-M4-023 / `tc_m4_023` | `test_service.py`, `test_review.py` | FR-10.1, FR-10.2, UC-M4-01, D-020, D-017 | DT / INT | `plan()` counts only `RENTAL_PICKUP` bookings, filters `open_trips` by `destination_hub_id == hub_id` and `expected_return_at <= horizon_end`, ignores `None` destinations, and deduplicates by `trip_id`. |
| TC-M4-024 / `tc_m4_024` | `test_service.py`, `test_review.py` | FR-10.4, UC-M4-02, BR-M4-02, BR-M4-03, BR-M4-08, BR-M1-01, NFR-06, NFR-09 | CT / FI | Claim conflict or low-battery/invalid-state precondition failure rolls back partial claims, marks task `FAILED` cleanly without nested UoW errors, and leaks zero claims. |
| TC-M4-025 / `tc_m4_025` | `test_service.py`, `test_review.py` | FR-10.4, UC-M4-02, BR-M4-04, NFR-06, NFR-18 | BVA / CT | Approval rejects missing/empty tasks and out-of-range `adjusted_quantity` (`<= 0` or `> len`), limits vehicle/space claims on valid adjustment, and skips already-claimed destination spaces. |
| TC-M4-026 / `tc_m4_026` | `test_service.py` | FR-10.4, FR-10.5, UC-M4-03, BR-M4-08, NFR-08 | ST | Invalid task state transitions (`pickup`/`return` from `RECOMMENDED`) and pickup when vehicle moved away from `source_hub_id` return `Err`. |
| TC-M4-027 / `tc_m4_027` | `test_review.py` | D-005, NFR-13, NFR-22 | STATIC / DET | Allocation modules never access private `core._clock` and reflect injected clock updates via `core.queries.get_config().as_of`. |
| TC-M4-028 / `tc_m4_028` | `test_api.py` | FR-10.1, FR-10.3, FR-10.4, FR-10.5, UC-M4-01, UC-M4-02, UC-M4-03, UC-M4-04, BR-M4-08 | INT / ST | REST endpoints execute plan/list/get/approve/pickup/return/cancel flows; missing `ReservationDemand` returns HTTP 503 `RESOURCE_UNAVAILABLE`. |
| TC-M4-029 / `tc_m4_029` | `test_api.py` | FR-10.6, FR-11.M4.1, FR-11.M4.2, UC-M4-05, UC-M4-06, UC-M4-07, NFR-18 | INT / EP | REST endpoints for alternative hubs (including 400 on `limit=0`), request arbitration, and alternative charging return expected JSON payloads. |
| TC-M4-030 / `tc_m4_030` | `test_api.py` | UC-M4-09, BR-M4-03, BR-M4-05, BR-M4-06 | EP / INT | `GET /allocation/config` and `PUT /allocation/config` read and persist updated allocation thresholds. |
| TC-M4-031 / `tc_m4_031` | `test_api.py`, `test_review.py` | NFR-16, D-014, D-023 | SEC | Every allocation endpoint returns HTTP 401 `UNAUTHENTICATED` with `WWW-Authenticate: Bearer` when called without a bearer token. |
| TC-M4-032 / `tc_m4_032` | `test_api.py`, `test_review.py` | NFR-16, D-023 | SEC | Every allocation endpoint returns HTTP 403 `FORBIDDEN` for student bearer tokens and allows authenticated operator tokens via `acting_as(principal, "allocation")`. |
| TC-M4-033 / `tc_m4_033` | `test_api.py` | FR-10, UC-M4-02, BR-M4-08 | ST | `POST /allocation/tasks/{id}/reject` turns a RECOMMENDED task into REJECTED with the reason; a repeat returns it; an APPROVED task is 409 and an unknown task 404. |
| TC-M4-034 / `tc_m4_034` | `test_api.py` | FR-10, FR-12, UC-M7-10, BR-M4-08 | INT | `POST /allocation/tasks/from-recommendation` makes a RECOMMENDED `TASK-SIM-` task with the best-battery vehicles of the source (at most the quantity); the same ID returns it; a new plan keeps it; a bad ID or equal Hubs are refused and a source with nothing to dispatch is 503. |
| TC-M4-035 / `tc_m4_035` | `test_planner.py` | FR-10.2, FR-10.3, FR-10.7, BR-M4-04, BR-M4-05, BR-M5-01 | DT | No Hub is short; H01 holds 19 of 20 spaces (95 %): one task H01 → H02 of 5 vehicles, priority 2, reason "Relieve parking at H01: 1 free of 20…". At 85 % nothing is planned. |
| TC-M4-036 / `tc_m4_036` | `test_planner.py` | FR-10.2, FR-10.7, BR-M4-04, BR-M1-02 | DT | A full H01 (CRITICAL) sends vehicles; a full and short H03 receives none; each destination keeps its buffer and stays below 90 %. |
| TC-M4-037 / `tc_m4_037` | `test_api.py` | FR-10.4, UC-M4-02, BR-M4-08 | INT | `POST /allocation/tasks/manual` makes a RECOMMENDED `TASK-OPS-` task with the default reason; a new plan keeps it; Approve succeeds; a `TASK-SIM-` ID, equal Hubs or quantity 0 are refused. |

## Execution record

| Run date | Command | Result | Coverage (`src/allocation`) |
|---|---|---|---|
| 2026-11-17 | `python -m pytest --strict-markers -q tests/allocation/ --cov=allocation --cov-report=term-missing` | 93 passed (32/32 `TC-M4-###` markers verified, 0 untagged) | 92% (779 stmts, 66 missed; NFR-24 minimum 60%) |
| 2026-11-25 (M1, branch `feat/backend-planned-gaps`) | `python -m pytest -q tests/allocation --cov=allocation` | 95 passed (TC-M4-033, TC-M4-034 added) | 91.72% (845 stmts, 70 missed) |
| 2026-11-26 (M1, branch `fix/ui-simulation-decide`) | `python -m pytest -q tests/allocation --cov=allocation` | 98 passed (TC-M4-035 to TC-M4-037 added) | 92% (901 stmts, 72 missed) |
