# Test Technique Assignment by Module

> **Owner:** M8 · **Baseline:** Core API v1.1 / develop `6777736`  
> **Purpose:** Assign concrete test-design techniques to each module. Module owners implement unit/component tests; M8 owns cross-module integration/system tests.

## Technique key

| Technique | Use it when | Typical design |
|---|---|---|
| EP — Equivalence Partitioning | Inputs form valid/invalid classes | One representative from each class |
| BVA — Boundary Value Analysis | Numeric/time/capacity thresholds matter | min−1, min, min+1; max−1, max, max+1 |
| DT — Decision Table | Several conditions jointly determine an outcome | Enumerate condition/action combinations |
| ST — State-Transition | Behavior depends on current state and event | Valid transitions + invalid pairs |
| CT — Conflict / Concurrency | Multiple actors compete for shared resources | Same resource, overlapping interval, simultaneous requests |
| FI — Failure Injection | A dependency or operation fails mid-flow | Inject failure and assert rollback/recovery |
| PERF — Performance / Load | NFR gives latency or throughput target | Timed run with defined dataset/concurrency |
| DET — Determinism / Metamorphic | Repeated inputs should produce stable output | Same seed/input twice; compare normalized output |
| SEC — Security / Authorization | Role, token, or input trust boundary | Role × endpoint matrix; malformed/tampered credentials |
| INT — Integration / Contract | Modules communicate through public interfaces | Provider/API contract and end-to-end flow |
| STATIC — Static architecture | Import/dependency boundaries must hold | Automated import scan in CI |
| UX — Usability review | Human-facing visibility and clarity | Task walkthrough against wireframes |

## Assignment matrix

| Module / area | Primary techniques | Concrete test families | Key linked requirements |
|---|---|---|---|
| **M1 Core** | ST, BVA, CT, FI, EP, STATIC | Every Vehicle state/event pair; battery 0/15/20/100; Hub and bay capacity; duplicate/overlapping claims; optimistic version conflicts; transaction rollback; invalid sensor payload; repository contract; module import boundaries | FR-01; BR-M1-01..03; NFR-06..10, 18, 22, 25 |
| **M2 Reservation** | EP, BVA, DT, ST, CT, FI | Student/operator/unknown actor; vehicle eligibility and battery floor; reservation interval boundaries; quota limit; Hub status ACTIVE/WARNING/CRITICAL; double booking; cancel/expire; pickup and return; private EV parking; atomic Trip/Reservation/Core update | FR-02..05, FR-07; UC-M2-*; NFR-03, 06, 09, 18, 21 |
| **M3 Charging** | EP, BVA, DT, ST, CT, FI | Battery threshold at 14/15/16%; private EV registration; connector/type validation; available/busy/faulty charging point; queue ordering and priority ties; one active session per point; start/finish/interruption; charger failure and recovery | FR-06, FR-07, FR-11; UC-M3-*; NFR-03, 06..10, 18, 21 |
| **M4 Allocation** | EP, BVA, DT, CT, FI, PERF | No source vehicles; no destination capacity; batch-size limits; transit-time feasibility; alternative Hub/bay candidates; provider unavailable; claim conflict; stale snapshot/version; dispatch execution rollback; network-wide runtime | FR-10, FR-11; UC-M4-*; BR-M4-*; NFR-04, 06, 09, 18 |
| **M5 Monitoring** | EP, BVA, DT, ST, FI, INT | Occupancy around 90%; battery at/below 15%; repeated vs new incidents; charger/vehicle fault; heartbeat timeout; incident escalation; duplicate event handling; event subscriber failure | FR-08, FR-09; BR-M5-*; NFR-01, 10, 20, 21, 25 |
| **M6 Simulation** | EP, BVA, DT, DET, FI, PERF, INT | Five standard scenarios; duration and multiplier bounds; missing Hub IDs; compound scenario; same-seed repeat; baseline vs mitigated comparison; snapshot isolation/write guard; timeout; recommendation feasibility | FR-12; UC-M6-01; BR-M6-*; NFR-05, 12, 13 |
| **M7 UI** | EP, DT, SEC, UX, INT | Role-based page/endpoint access; empty/loading/error states; filter combinations; form validation; operator near-capacity and incident visibility; rejection text and alternative guidance; UI refresh after Core update | FR-01..12 as surfaced; NFR-01, 16, 18, 20, 21 |
| **M8 IoT simulator** | EP, BVA, DET, FI, INT | DS-STD totals/distributions; invalid seed/config; same-seed dataset and event stream; battery 0..100; event ordering/unique IDs; private parking arrival/departure; malformed event rejection; Core invariant check after feed | FR-01, FR-09 cross-cutting; NFR-07, 10, 13, 18 |
| **M8 integration/system** | INT, DT, ST, CT, FI, PERF, SEC | Student reserve→pickup→return; private EV arrive→charge→depart; charger fault→session interruption→incident; dispatch; simulation isolation; authorization; load and NFR evidence | All active FR/BR/UC; NFR-01..10, 12..18, 20..22, 24..26 |

## Priority guidance

1. **P0:** state integrity, authorization, resource conflicts, atomicity, invalid input, and cross-module happy paths.
2. **P1:** boundary cases, equipment failure, provider unavailability, deterministic simulation, and performance targets.
3. **P2:** UX polish, broad pairwise combinations, and exploratory edge cases not tied to a safety or grading-critical rule.

Every test case must identify its own `TC-M<n>-###` ID, `Verifies:` IDs, technique, and expected observable result. Do not invent BR/UC IDs before the owning module commits them; use the FR/NFR links until then.
