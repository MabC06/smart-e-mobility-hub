# IoT Simulator Review

> Owner: M7 (Nguyễn Trung Kiên) · Date: 2026-11-10 · Reviewer: M5 (Đỗ Hoàng Việt)
> Reviewed: `src/iot_sim/` on `origin/feat/iot-sim-minimal` at `e12c896` (M8, PR #26, not merged), against M8's design and checklist on `origin/docs/m8-phase1-testing-design` at `28489de` (PR #25, not merged).

## 1. Scope

M7 reviews the data that `iot_sim` generates (`CONTRIBUTING.md` Section 6: "Checks generated data against the ERD and class diagram"; Phase 2 in `task-assignment-timeline.md`). This is the review item "IoT simulator data / ERD alignment" of M8's `design-review-checklist.md` Section F.

| Source | What is checked |
|---|---|
| `docs/design/structural/erd.md`, `db-schema.md` | The generated rows fit the columns, enumerated values, keys and CHECK constraints |
| `docs/requirements/reference-dataset.md` Sections 2 to 4 and 7 | Totals, the Hub table, distributions and sanity checks |
| `docs/design/iot-simulator-design.md` (M8) | Dataset mapping (Section 3), minimal feed (Section 4), full feed (Section 5), determinism (Section 8) |
| `docs/testing/design-review-checklist.md` (M8) | Section C, Section D, and the first two items of Section E (seed and clock, reproducibility) |

Checklist items are numbered in their order within each section: C1 is the first item of Section C. Sections A, B and the rest of E are reviewed by M4, M1 and M8 (`design-review-checklist.md:4`).

## 2. Method

1. Read the five files of `src/iot_sim/`.
2. `core` on M8's branch is the same as on `develop` (`git diff origin/develop origin/feat/iot-sim-minimal -- src/core` is empty), so M8's code was run against `develop`'s `core`.
3. Ran M8's tests in `tests/iot_sim/`: 13 passed (local Python 3.14; CI uses 3.12).
4. Loaded the network with `seed_core(core, 20261106)` on `SqlRepository.open("sqlite://")`, so the foreign keys and CHECK constraints of `db-schema.md` apply. Then ran `run_minimal_feed(core, 20261106, datetime(2026, 11, 6, 8, 0, tzinfo=UTC), SimulatorConfig(seed=20261106))`. After each step: counted the rows and called `core.check_invariants()`.
5. Built the network spec and the event feed twice with the same seed and compared them.

The seed 20261106 is the one in the design's example (`iot-simulator-design.md` Section 9).

## 3. Results

### 3.1 ERD and schema

| Item | Expected | Actual | Result | Evidence |
|---|---|---|---|---|
| The seed loads into the SQLite schema | Every row passes the foreign keys, UNIQUE and CHECK constraints (`db-schema.md` Section 4) | `load_network` returns `Ok`: 10 Hubs, 400 spaces, 61 charging points, 350 vehicles, 1,005 accounts | Pass | `service.py:21-23` |
| Vehicle location and owner | Both location columns null exactly while `IN_USE`; `PRIVATE` with an owner, `FLEET` without (`erd.md` Sections 3 and 7) | 250 fleet vehicles `AVAILABLE` at a Hub; 100 private EVs `IN_USE`, no Hub, owner set | Pass | `dataset.py:55-64, 75-86` |
| Charging bays | Each charging point has its own bay in the same Hub (D-007) | 61 charging points, each bay in its own Hub | Pass | `core.check_invariants()` returns `[]` |
| Accounts | `role` is `STUDENT` or `OPERATOR`; `password_hash` may be null | 1,000 `STUDENT`, 5 `OPERATOR`; every `password_hash` is null | Pass (see F1) | `dataset.py:68-70` |
| Module tables | Not written by the simulator (`iot-simulator-design.md` Section 5) | Only `core`'s tables are written | Pass | `service.py:23, 28` |

### 3.2 Reference dataset (DS-STD)

| Item | Expected | Actual | Result | Evidence |
|---|---|---|---|---|
| Totals (Section 2) | 10 Hubs, 400 spaces, 61 charging points, 250 rental vehicles, 1,000 students, 5 operators, 100 private EVs | The same | Pass | Seed run |
| Hub table (Section 3) | Spaces, charging points and rental vehicles of H01 to H10 | Equal for every Hub | Pass | `dataset.py:10-21` |
| Battery shares (Section 4) | 60% above 70, 25% from 30 to 70, 15% below 30 | 150 / 62 / 38 | Pass | `dataset.py:24-35` |
| Vehicle-type shares (Section 4) | 50% e-bike, 30% e-scooter, 20% electric motorcycle | 125 / 75 / 50 | Pass | `dataset.py:46-49` |
| Same seed, same dataset (Section 7, check 4) | Identical result (NFR-13) | `build_network_spec(20261106)` built twice is equal | Pass | Seed run |

### 3.3 M8's checklist

| Item | Actual | Result | Evidence |
|---|---|---|---|
| C1, C2: DS-STD totals | See 3.2 | Pass | |
| C3: battery and type distributions | See 3.2 | Pass | |
| C4: each charging point maps to its bay | See 3.1 | Pass | |
| C5: fleet vehicles in non-charging spaces first | No fleet vehicle is in a charging bay | Pass | Seed run |
| C6: private EVs have an owner and a connector type | Owners `U-0001` to `U-0100` exist; connector `TYPE2` | Pass | `dataset.py:82-83` |
| C7: IDs unique, stable, deterministic | `F-0001`, `P-001`, `U-0001`, `OP-01`; same seed gives the same spec | Pass | `dataset.py:57, 69-70, 77` |
| C8: no real passwords, tokens or personal data | No password hash; codes such as `STU-0001` | Pass | `dataset.py:68-70` |
| D1: event type is one of the six types | Only `BATTERY_LEVEL`, `SPACE_OCCUPIED`, `SPACE_FREED` are emitted | Partly met (F2) | `events.py:31-70` |
| D2: `event_id`, `source`, `entity_id` and an aware `at` are set | `IOT-20261106-000001` onwards, `iot_sim:battery` or `iot_sim:parking`, UTC times | Pass | `events.py:24-25, 35-42` |
| D3: `BATTERY_LEVEL` within 0 to 100 | Values from 4.1 to 99.4 | Pass | `events.py:33` |
| D4: `SPACE_OCCUPIED` names a private EV and a free space | 5 events, all accepted by `core` | Pass | `events.py:44-62` |
| D5: `SPACE_FREED` does not move a fleet or charging vehicle | Frees only the space of the private EV that arrived | Pass | `events.py:63-70` |
| D6: charger failure and recovery go through sensor intake | No `CHARGER_FAULT` event | Not met (F2) | |
| D7: failed events are kept, not ignored | `apply_events` returns every result; 260 of 260 are `Ok` | Pass | `service.py:26-28` |
| D8: no repository, SQL or database write | Imports only the public surface of `core`; writes through `load_network` and `apply_sensor_event` | Pass | `service.py:23, 28` |
| E1: seed and clock are explicit inputs | The seed is explicit; the clock is not when `start_at` is left out | Fail (F3) | `service.py:39` |
| E2: same seed and order give the same output | The feed built twice is equal; occupied spaces return to 250; `core.check_invariants()` returns `[]` after the feed | Pass | `events.py:26` |

## 4. Findings

Severity: **Blocking** stops PR #26; **Should fix** before the Phase 3 code freeze (2026-11-12); **Note** needs no change now.

| # | Finding | Evidence | Severity | Proposed action |
|---|---|---|---|---|
| F1 | Every seeded account has `password_hash=None`, so nobody can log in. This is the design's intent and meets C8, but the login screen and the demo need accounts that can log in (NFR-16). | `dataset.py:68-70`; `iot-simulator-design.md:60`; `src/core/auth.py:161` | Should fix | The team decides how demo accounts get a password, read from an environment variable and never committed (NFR-17). |
| F2 | The full feed is not implemented: no `CHARGER_FAULT`, `VEHICLE_FAULT` or `HEARTBEAT`. The simulator never puts a charging point `OUT_OF_SERVICE` or sets `fault_flag`, so M5's incidents for a failed charging point (`INC-HW-01`) and lost telemetry (`INC-COMM-01`) cannot be shown with simulator data. | `iot-simulator-design.md` Section 5 (due 2026-11-08); checklist D1, D6; `task-assignment-timeline.md:158` (M5 needs the full feed) | Should fix | M8 adds the full feed and its tests. M7 then re-checks D1 and D6. |
| F3 | `run_minimal_feed` uses `datetime.now(UTC)` when `start_at` is not given, so the same seed can give different event times. | `service.py:39`; `iot-simulator-design.md:102` ("No ... hidden clock"); checklist E1; D-005 | Should fix | M8 makes `start_at` required. |
| F4 | The DS-STD numbers are written in the code (Hub table, type counts), while `reference-dataset.md` says they are not duplicated in code. They are named constants, which `CONTRIBUTING.md` 9.3 allows. | `dataset.py:10-21, 47, 72`; `reference-dataset.md:13, 18` | Note | M8 and M1 agree whether the named constant is enough. |
| F5 | Every vehicle has `battery_capacity_kwh=0.5`, also electric motorcycles, and every charging point has 11 kW. DS-STD gives no value; the ERD only needs values above 0. | `dataset.py:61, 66, 81` | Note | M3 checks whether these values give sensible charging times. |
| F6 | Private EVs reuse the battery and type shares of the fleet. DS-STD Section 4 defines them for rental vehicles only. | `dataset.py:45, 71-74` | Note | None. |

No finding is Blocking.

## 5. Sign-off

Result for M8's `design-review-checklist.md` Section F:

| Review item | Reviewer | Result | Evidence / comment |
|---|---|---|---|
| IoT simulator data / ERD alignment | M7 | Pass with findings | `docs/testing/iot-sim-review.md`: the seeded data fits the ERD and DS-STD; F2 and F3 for M8, F1 for the team |

The checklist is M8's file, so M7 posts this result as a comment on PR #25 and PR #26, and M8 updates the row.
