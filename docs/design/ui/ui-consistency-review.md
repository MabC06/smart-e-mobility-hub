# Consistency Review: UI, Class Diagram, ERD, Code and Other Modules

> Owner: M7 (Nguyễn Trung Kiên) · Date: 2026-11-07
> I compared the screens with `class-diagram-core.md`, `erd.md`, the code, and the Phase 1 documents of the other modules.
> Read on 2026-11-07: `core` on `develop`; `architecture-diagram.md`; M2's code (`origin/feat/reservation-booking-flow`) and documents (`origin/docs/reservation-phase1-design`); M4's code (`origin/feat/allocation-phase2`); M5 (`origin/docs/monitoring-phase1`); M6 (`origin/docs/simulation-design`, `origin/feat/m6-simulation-impl`); M3 (`origin/docs/charging-scheduling-requirements`).

## 1. Class diagram, ERD and code

- The eight entities in Section 2 of `class-diagram-core.md` have the same attributes in `entities.py`, the same columns in `schema.py`, and the same names in `erd.md`.
- `DomainEvent`: the class exists and the table `domain_events` is created, but no code writes to it. M1 decided that events are not stored. The ERD does not draw the table.
- `parking_spaces.occupant_vehicle_id` has no foreign key; the foreign key is `vehicles.parking_space_id`.
- The operations in Section 3 of the class diagram exist in `src/core` under the same names.
- M2 and M4 tables follow their code. M5 tables follow its document (no code).

## 2. Fields on the screens

Every field on the screens was traced to a `core` query (and the REST route that returns the same data), an ERD table, a function of M2 or M4, or a requirement or data model of M3, M5 or M6. Results:

- The REST output `VehicleOut` leaves out `owner_user_id` and `connector_type`. The screens do not need them.
- `ChargingPointView` has no label, so O2 shows `charging_point_id`.
- The screens for M3, for M5's code, for M6 beyond demand surge, and for M2's cancel, parking and return-space hold follow requirements only. They must be checked again when those modules publish code.

## 3. What the screens need and the backend lacks

The `ui` module may call `core` directly (`architecture-diagram.md`, Section 11, point 2), so these REST gaps do not block a page. They matter only for a client that uses REST alone.

| # | Need | Screen | Direct call available |
|---|---|---|---|
| G1 | Near-capacity limit | O1 alert strip | `core.queries.get_config()` |
| G2 | Next claim on a space or point | O2 | `core.queries.get_claims()` |
| G3 | Current `version` of one vehicle, also one in use | S5 (return) | `core.queries.get_vehicle()` |
| G4 | Operator actions on a vehicle, point or Hub | O2 | `core.commands.*` through a `ui` route (to be written by M7) |

These depend on another module:

| # | Need | Owner |
|---|---|---|
| G5 | A list of the student's bookings and trips (S2, S5). M2's service has only `reserve`, `pickup`, `return_trip` | M2 |
| G6 | Charging data for students and a route to register a private EV (S7, S8). Only the charging module, an operator or `iot_sim` may call `register_vehicle` | M3 |
| G7 | Incident routes, alerts, the stale-data flag, the remote reset (O1, O5). M5 has documents and a data model, no code | M5 |
| G8 | Simulation routes, input ranges, how an approved recommendation is sent, export format (O6) | M6, M4 |
| G9 | A reject action; the router uses a fixed operator `OP01`; `BATTERY_TOO_LOW` and `CLAIM_CONFLICT` return HTTP 500 (O4) | M4 |

## 4. Where other members' documents disagree

| # | Disagreement | Owner |
|---|---|---|
| D1 | `architecture-diagram.md` says `ui` "talks HTTP" (Section 4) and also "may call `core` in-process" (Section 11, point 2). The import test forbids importing another module's package. How a page reaches M2 to M6 is undecided | M1 |
| D2 | M1 decided events are not stored, but `schema.py` creates `domain_events` | M1 |
| D3 | `architecture-diagram.md` (Section 6) lists the Phase 0 table names of M4, M5 and M6 | M1 |
| D4 | M5's model calls the Hub table `core_hubs` (it is `hubs`), uses old column names in `HubMetricsSnapshot`, and does not say whether `assigned_operator_id` is a foreign key | M5 |
| D5 | M5's sequence polls `GET /api/v1/hubs/overview`, which does not exist | M5, M7 |
| D6 | M3's state machine, M3's report and the timeline list different session states | M3 |
| D7 | On M3's branch `fr-06-07-11-charging.md` holds report text and has no `FR-06` or `UC-M3` definitions. The branch also lacked 63 commits of `develop` when I checked | M3 |
| D8 | M6's design and code differ on input ranges and on one field name (`destination_bias` and `destination_distribution`) | M6 |
| D9 | M4's design says `REBALANCE`, its code uses `DISPATCH_TASK` claims | M4 |
| D10 | M5's final version escalates `HIGH` and `CRITICAL` tickets and uses 30 seconds for stale data; its earlier text said `HIGH` and 60 seconds. The screens use the final version | M5 |

## 5. Requirements and screens

| Capability (guideline Section 2.2) | FR | Screens |
|---|---|---|
| View Hubs and resource status | FR-01 | S2, O1, O2 |
| Find suitable rental vehicles | FR-02 | S3 |
| Reserve rental vehicles | FR-03 | S4, S5 |
| Pick up and return | FR-04 | S5 |
| Reserve parking spaces | FR-05 | S6, S5 |
| Request or schedule charging | FR-06 | S8 |
| Private EV parking and charging | FR-07 | S6, S7, S8 |
| Monitor vehicles, parking, charging points, Hubs | FR-08 | O1, O2 |
| Handle incidents | FR-09 | O5, O2 |
| Redistribute vehicles | FR-10 | O4 |
| Charging priorities and schedules | FR-11 | O3, O4 |
| What-if simulation and recommendations | FR-12 | O6 |

NFR-20 is met by the alert strip and the order of O1. NFR-21 is met by the error block (cause, alternative, code). NFR-01 is met by polling every 3 seconds. M8 will test empty, loading and error states, forms, refresh and role access.

## 6. Result

1. The `core` entities agree across the class diagram, the code and the ERD.
2. Every field the screens read from `core`, M2 and M4 exists. The gaps in Section 3 are not blocking, except that a list of the student's bookings (G5) is needed from M2.
3. The tables of M2 and M4 follow open branches and may change before the code freeze on 12 November.
4. Section 4 lists disagreements between other members' documents. This review does not decide them.
