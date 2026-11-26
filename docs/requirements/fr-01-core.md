# Core — Requirements and Business Rules (FR-01)

**Owner:** M1 — Đoàn Nhật Minh (2452738)
**Status:** Final v1.1 · 2026-10-28

## 1. Functional requirement

- **FR-01 — View Mobility Hubs and their current resource status.** `core` is the only owner of Hub, vehicle, parking-space and charging-point state (D-003). Other modules read and change that state only through the `core` interface.

## 2. Business rules (core-wide)

These rules apply to every module. Other modules cite them instead of restating them (`CONTRIBUTING.md` §5).

| ID | Rule | Trace |
|---|---|---|
| BR-M1-01 | A vehicle, a parking space or a charging point cannot be held by two claims (reservation, charging session, dispatch task) whose time intervals overlap. A request that would overlap is rejected with a conflict error and changes nothing. | FR-01, FR-03, FR-05, FR-06, FR-10, NFR-06 |
| BR-M1-02 | For every Hub: occupied parking spaces ≤ parking capacity; charging points ≤ parking spaces; a vehicle that is being charged occupies exactly one parking space (its charging bay, D-007); a charging point serves at most one vehicle at a time (A-04). | FR-01, FR-05, FR-06, FR-10, NFR-07 |
| BR-M1-03 | Each vehicle is in exactly one state (Available, Reserved, InUse, Returned, Charging, Maintenance). The state changes only through a transition allowed by the Vehicle state machine; any other change is rejected with an error code and the state stays the same. | FR-01, NFR-08 |

## 3. Notes

- Atomic multi-entity operations and the log of state changes are quality requirements, not business rules: see NFR-09 and NFR-25.
- The state names in `BR-M1-03` must match the Vehicle state machine document.
- The measurable targets for these rules (concurrency test, invariant check, state-transition tests) are in NFR-06, NFR-07 and NFR-08.
