# M4 - Allocation algorithm design

> Owner: M4 - 2412466 Huỳnh Minh Nhật. Date: 2026-10-22. **Proposed for team review**.
> Requirements: [`fr-10-11-allocation.md`](../../requirements/fr-10-11-allocation.md). Interaction and flow: [sequence](../behavioral/allocation-sequence-diagram.md), [activity](../behavioral/allocation-activity-diagram.md), [task state machine](../behavioral/allocation-state-machine.md).

## 1. What the algorithms must do

| Problem | Requirement | Section |
|---|---|---|
| Move rental vehicles from Hubs with surplus to Hubs that will run short, without breaking capacity | FR-10.1 to FR-10.5, FR-10.7 | 4 |
| Decide who gets a contested resource | FR-11.M4.1, BR-M4-01 | 5 |
| Suggest other Hubs when a request cannot be served | FR-10.6, FR-11.M4.2 | 6 |

Constraints: the plan for the whole network within 5 s on DS-STD (NFR-04); no double allocation (NFR-06); capacity invariants (NFR-07); same input gives the same output (NFR-13); every decision can be explained (NFR-21, NFR-25); no route planning (A-01, A-02). Scale: DS-STD has 10 Hubs and 3 vehicle types (A-03); DS-STRESS has 20 Hubs, i.e. 190 Hub pairs (D-010).

## 2. Inputs and outputs of the planner

| Input | Source | Note |
|---|---|---|
| Hub snapshot: vehicles with state and battery, free spaces, free charging bays, `as_of` | Core (read-only) | One consistent version |
| Upcoming pickups and returns per Hub for the horizon | Reservation (M2) through Core | Confirmed bookings and trips due |
| Scheduled charging sessions per Hub | Charging (M3) through Core | Bays that will be busy |
| Typical demand per Hub, period and type | Demand profile (D-008) | From configuration |
| Closeness between Hubs | Configuration table | Relative, not a route (A-02) |
| Active dispatch tasks | Allocation (own data) | Inbound and outbound |
| Parameters | Configuration (section 7) | Never hard-coded |

Output: a sorted list of dispatch tasks `(task key, source, destination, vehicle type, quantity, vehicles, priority, reason)`.

The planner is a **pure function**: `plan(snapshot, demand, tasks, params) -> tasks`. It reads no clock and writes no state, so M6 can run it on a copy of the state and the result is repeatable (NFR-13, D-003).

## 3. Approaches compared

| Criterion | A. Threshold rules + greedy matching | B. Min-cost flow (transportation problem) | C. Integer programming (solver) | D. Reactive only (move when a Hub is empty or full) |
|---|---|---|---|---|
| Quality of the plan | Good, not globally optimal | Optimal for the chosen linear cost | Optimal, can model many constraints | Poor: acts after students are affected |
| Run time on 10 to 20 Hubs | Negligible | Small | Depends on the solver | Negligible |
| Deterministic (NFR-13) | Yes, by fixed tie-breaks | Yes if the solver is deterministic | Solver dependent | Yes |
| Explainable to an operator (NFR-21, NFR-25) | High: each task has a stated reason | Medium: result is not obvious | Low | High |
| Effort in about 3 weeks | Low | Medium | High | Very low |
| Extra dependencies (NFR-14) | None | Library or own code | External solver | None |
| Needs real travel costs | Only a ranking of closeness | Yes, to be meaningful | Yes | No |

**Chosen: A.** It meets the 5 s target with a large margin, gives repeatable results, and every task can be explained in one sentence ("Hub H08 expects 14 pickups in 30 minutes, has 12 vehicles; H05 has 15 more than it needs"). B is the natural improvement if real costs become available, and the planner keeps the same inputs and outputs, so B could replace A without changing the other modules. D is rejected because FR-10 asks to find Hubs *at risk*, not Hubs already in trouble. C is rejected for effort and dependency reasons.

**Trade-off accepted:** the plan can be slightly worse than the optimum, because each destination is served independently in order of urgency. In exchange it is simple to test, explain and reproduce.

## 4. Redistribution of rental vehicles

### 4.1 Quantities per Hub `h` (per vehicle type; horizon `H`)

| Symbol | Meaning |
|---|---|
| `A(h)` | Available vehicles: state `Available`, battery at or above the dispatch minimum, no reservation soon, not in another task |
| `A_eff(h)` | `A(h)` minus vehicles leaving by active tasks plus vehicles arriving by active tasks |
| `F_out(h)` | Expected pickups in `H` = max(confirmed bookings starting in `H`, profile estimate) |
| `F_in(h)` | Expected returns in `H` = max(trips due to arrive in `H`, profile estimate) |
| `P_free(h)` | Free parking spaces |
| `S`, `B` | Safety stock and parking buffer (parameters) |

```
need(h)     = max(0, F_out(h) + S - A_eff(h))
surplus_v   = max(0, A_eff(h) - F_out(h) - S)
pressure(h) = max(0, F_in(h) + B - P_free(h))      # space is about to run out
surplus(h)  = min(A_eff(h), max(surplus_v, pressure(h)))
urgency(h)  = need(h) / (F_out(h) + S)             # share of expected demand not covered
```

Taking the larger of the reservation count and the profile estimate avoids counting a reservation twice and never forecasts less than what is already booked.

### 4.2 Steps

1. Compute the quantities above for every Hub.
2. If no Hub has `need > 0`, return "no task needed".
3. Sort destinations by `urgency` (highest first), then by Hub ID.
4. For each destination `d`, while `need(d) > 0`:
   1. Take the source `s` with `surplus(s) > 0` that is nearest to `d`; ties: larger surplus, then Hub ID.
   2. `q = min(need(d), surplus(s), P_free(d) - B, max per task)`.
   3. If `q <= 0`, if `s` would fall below its safety stock, or the per-Hub task limit is reached: remove `s` from the candidates of `d` and continue.
   4. Select `q` vehicles at `s`: only those allowed by BR-M4-03, ordered by battery (highest first), then vehicle ID. If fewer are found, reduce `q`.
   5. Create a `Recommended` task with its reason; update `need(d)`, `surplus(s)`, `A_eff(s)`, `P_free(d)` and `P_free(s)`.
5. Sort the tasks (priority, then task key) and return them.

Each pass removes a candidate or reduces a need, so the loops end. With `H` Hubs and `T` vehicle types the work is `O(T * H^2 log H)`. The types are planned one after the other and share the parking budget `P_free`. Measured time against NFR-04 is checked in Phase 4 on DS-STD and DS-STRESS; this document does not claim a measured value.

### 4.3 Worked example

The Hubs and their sizes are taken from DS-STD. The forecast numbers and the closeness values are **invented for the example** only. `S = 3`, `B = 3`, at most 10 vehicles per task, horizon 30 minutes, morning period.

| Hub | Spaces / vehicles (DS-STD) | `A` | `F_out` | `F_in` | `P_free` | need | surplus | urgency |
|---|---|---|---|---|---|---|---|---|
| H01 Metro | 70 / 50 | 44 | 47 | 6 | 20 | 6 | 0 | 0.12 |
| H05 Campus A | 50 / 30 | 26 | 8 | 20 | 20 | 0 | 15 | 0 |
| H08 Library A | 25 / 14 | 12 | 14 | 2 | 11 | 5 | 0 | 0.29 |
| H03 Dorm B | 50 / 30 | 27 | 20 | 3 | 20 | 0 | 4 | 0 |

Closeness (lower is nearer): H05-H08 = 1, H03-H01 = 1, H05-H01 = 2, H03-H08 = 3.

1. Destinations in order: H08 (0.29), then H01 (0.12).
2. H08: nearest source H05. `q = min(5, 15, 11 - 3, 10) = 5`. Task 1: **H05 to H08, 5 vehicles**.
3. H01: nearest source H03. `q = min(6, 4, 20 - 3, 10) = 4`. Task 2: **H03 to H01, 4 vehicles**. Remaining need 2.
4. H01: next source H05 (10 surplus left). Task 3: **H05 to H01, 2 vehicles**.

Checks: H05 keeps `26 - 7 = 19 >= 8 + 3 = 11` (BR-M4-05). H03 keeps `27 - 4 = 23 >= 20 + 3 = 23`, exactly at the boundary, which is a good boundary test. Destination spaces after the move stay at or above the buffer (BR-M4-04).

### 4.4 Approval and commit

The plan can be minutes old, so approval repeats the checks on a fresh snapshot and then holds the vehicles (as a system reservation with purpose `REBALANCE`) and one destination space in one atomic unit of work (NFR-09, BR-M4-04, BR-M4-07). If a competing claim was committed first, nothing is held and the task becomes `Failed` (NFR-06). Timeouts use the injectable clock (D-005).

### 4.5 Re-planning without duplicates (UC-M4-08, FR-10.7)

A task key is derived from the cause (event ID or plan time slot), source, destination and vehicle type. The same event gives the same key, so no duplicate task is created. On a new event, `Recommended` tasks that no longer match the state are withdrawn (`Cancelled`, reason `SUPERSEDED`).

## 5. Arbitration of competing requests (BR-M4-01)

Each request gets a class level 1 to 8 from BR-M4-01. The sort key is `(class level, request time, request ID)`. The first request tries to claim the resource in one atomic step; the others receive a conflict answer with the reason and an alternative if one exists. Inside the charging class the order is set by M3's BR-M3-03 (D-012).

| Alternative considered | Why not chosen |
|---|---|
| First come, first served only | Ignores that a booked reservation must beat a walk-in |
| Weighted score across all classes | Harder to explain; small weight changes can reverse results |
| **Strict class order, then time, then ID (chosen)** | Predictable and explainable; ties never depend on chance |

Limitation: a request of a low class can wait while higher classes keep arriving. No ageing is implemented; resources are released continuously, and this is reported in the limitations of the report.

## 6. Alternative Hubs (UC-M4-05) and alternative charging (UC-M4-07)

- **Hubs for a vehicle or a parking space:** keep Hubs that still have the needed resource; sort by closeness, then larger remaining amount, then better battery (vehicles only), then Hub ID; return the top N.
- **Charging:** keep other Hubs with at least one free, working charging bay; sort by closeness, then more free bays, then Hub ID. When several requests are displaced together they are served in the order of section 5, and each free bay is offered to at most one request.
- Both are read-only and return `as_of`. If nothing qualifies the reason code is `NO_VEHICLE`, `NO_PARKING`, `NO_CHARGER` or `ALL_HUBS_FULL` (BR-M4-10).

## 7. Parameters

All are configuration values (CONTRIBUTING 9.3). The values are not set in this document (see "Not decided yet").

| Parameter | Meaning | Used by |
|---|---|---|
| Forecast horizon `H` | Look-ahead window for demand | 4.1 |
| Reservation look-ahead window | A vehicle with a reservation in this window is not moved | BR-M4-03 |
| Safety stock `S` | Minimum available vehicles kept at a Hub | BR-M4-05 |
| Parking buffer `B` | Free spaces always kept at the destination | BR-M4-04 |
| Minimum dispatch battery | Lowest battery of a vehicle that may be moved | BR-M4-03 |
| Maximum tasks per Hub | Concurrent tasks in or out of one Hub | BR-M4-06 |
| Maximum vehicles per task | Upper limit of `q` | 4.2 |
| Task timeout | Time after which a task fails | BR-M4-08 |
| Staleness limit | Age of a snapshot after which the screen shows a warning | UC-M4-01 |
| Closeness table | Relative closeness of Hub pairs | 4.2, 6 |

## 8. Limitations

- Greedy matching can be worse than the optimum (accepted in section 3).
- The forecast is simple: the larger of known bookings and the typical profile. It does not learn from history.
- Closeness is a ranking, not a travel time. Staff capacity for moving vehicles is not modelled.

## 9. Test implications (for Phase 2 and 4)

- Boundary values: safety stock exactly reached and one above and below; destination free spaces exactly at the buffer; battery one below, at and one above the minimum.
- Equivalence classes: balanced network; one short Hub; several short Hubs competing for one surplus; no surplus anywhere.
- Decision table: arbitration by class level and time; alternative Hub ranking.
- State transitions: every valid transition and every invalid pair of the task state machine.
- Conflict and exhaustion: 20 to 50 simultaneous claims on one vehicle or space (NFR-06); all Hubs full (BR-M4-10).
- Determinism and performance: two runs with the same seed give the same plan; timed run on DS-STD and DS-STRESS (NFR-04, NFR-13, NFR-15).
- The worked example in 4.3 is a ready test case with known results.

## 10. Not decided yet

Sections 1 to 9 are designed. The items below are **not decided**.

| # | Item | Waiting for |
|---|---|---|
| 1 | Values of all parameters in section 7 (horizon, safety stock, buffer, minimum dispatch battery, limits, timeout, staleness limit). | M3, M5, M6 |
| 2 | The closeness table between Hubs: its content and where it is stored. | M1, M6 |
| 3 | The public interface to read the snapshot and the demand of M2 and M3 (the planner needs the inputs of section 2). | M1 (Core API spec v1) |
| 4 | Whether a rebalance move is a system reservation with purpose `REBALANCE`, so the Vehicle state machine needs no new state. | M1, M2 |
| 5 | Whether the operator approves every task or an automatic mode exists for demos. | M5, M7 |
| 6 | Entries for `DECISIONS.md`: the algorithm (approach A), the system reservation for a rebalance move, and the planner as a pure function. They are written when the team agrees; the next free ID is used at that time. | Team |
