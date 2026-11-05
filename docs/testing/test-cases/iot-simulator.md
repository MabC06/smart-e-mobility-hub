# IoT Simulator Test Cases

> **Owner:** M8 · **Status:** Planned until executed in the repository environment  
> **Test folder:** `tests/iot_sim/`

| TC ID | Test case | Verifies | Technique | Expected result |
|---|---|---|---|---|
| TC-M8-001 | Build DS-STD totals | FR-01, NFR-07 | BVA / data sanity | 10 Hubs, 400 spaces, 61 charging points, 250 fleet vehicles, 1,005 accounts, 100 private EVs |
| TC-M8-002 | Verify rental battery bands | NFR-13 | EP / data sanity | 150 vehicles >70%, 62 vehicles 30–70%, 38 vehicles <30% |
| TC-M8-003 | Verify rental vehicle types | NFR-13 | EP / data sanity | 125 e-bikes, 75 e-scooters, 50 electric motorcycles |
| TC-M8-004 | Repeat dataset generation with same seed | NFR-13 | Determinism | Equal `NetworkSpec` values |
| TC-M8-005 | Different seed preserves shape but changes generated values | NFR-13 | Metamorphic | Hub/entity counts remain fixed; seeded battery values differ |
| TC-M8-006 | Reject negative seed | NFR-18 | EP | `ValueError` before Core is called |
| TC-M8-007 | Repeat event generation with same inputs | NFR-13 | Determinism | Identical ordered `SensorEvent` list |
| TC-M8-008 | Ensure event IDs are unique and timestamps ordered | NFR-13 | Boundary / structural | No duplicate IDs; monotonic timestamps |
| TC-M8-009 | Generate battery drain for every fleet vehicle | FR-01, NFR-07 | EP | Exactly 250 battery events, each in 0–100 |
| TC-M8-010 | Generate paired private-EV occupancy events | FR-01, NFR-07 | State-transition | Each selected private EV has occupied then freed event on a free non-charging space |
| TC-M8-011 | Reject naive event start time | NFR-18 | EP | `ValueError`; no event emitted |
| TC-M8-012 | Seed Core from DS-STD | FR-01, NFR-07 | Integration | Core reports expected entity totals |
| TC-M8-013 | Apply minimal feed | FR-01, FR-09, NFR-10 | Integration / ST | Battery values change; paired private occupancy returns to initial occupancy; all results succeed |
| TC-M8-014 | Check Core invariants after feed | NFR-07 | Invariant check | `core.check_invariants()` returns no violations |
| TC-M8-015 | Refuse to seed a non-empty store | NFR-10, NFR-18 | Negative / boundary | Core returns `Err`; existing state is not overwritten |

## Execution record

Fill this table when running the tests in the target `.venv`; do not infer a pass from test implementation.

| Run date | Commit | Command | Result | Evidence |
|---|---|---|---|---|
| Pending | Pending | `python -m pytest tests/iot_sim -q` | Not run in this artifact build | |
