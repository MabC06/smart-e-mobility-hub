# 3.3 Behavioral and Interaction Design

<!-- BEGIN M2: Reservation & Trip -->
## M2 contribution - Reservation & Trip

> Author: 2452620 Đặng Tuấn Kiệt. Date: 2026-11-04. **Proposed for team review**. Core interactions follow the released Core API v1.1 and D-015 through D-020; M2 policy values remain subject to team review.

### Design overview

The Student first searches a Core snapshot, then confirms a vehicle. Confirmation rechecks eligibility, quota and concurrent claims in one Core-coordinated transaction. Success creates a Confirmed ten-minute hold while the vehicle still occupies its origin space. Pickup before the deadline creates one Trip and frees that space atomically. Return requires a receiving space and atomically completes the Trip and booking, records the destination occupancy and leaves the vehicle Returned or Maintenance for Core/M3 readiness processing.

When the destination is full, the Trip remains open. Core may obtain advisory alternatives from M4; displaying an alternative does not reserve it. This makes failed return recoverable without fabricating a successful drop-off. No automatic destination hold is created at rental confirmation; the Student can separately reserve a short immediate return-space hold under FR-05.

Private parking has its own specialization: future claim -> actual occupied stay -> actual departure. A planned end time or charging completion cannot physically remove a vehicle. Joint charging uses one parking bay, with charger and bay claims committed together. Resource failures invalidate only unused claims; an active trip/stay remains accountable until verified return, recovery or departure.

### UML diagram index

| Artifact | IDs and intent | Detailed source and discussion |
|---|---|---|
| Activity | A1 find/confirm with invalid/no-vehicle/conflict branches; A2 cancel/expiry; A3 parking/bay admission and departure | [Activity document](../design/behavioral/reservation-activity-diagram.md) |
| Sequence | S1 reserve; S2 pickup; S3 return and Core-mediated M4 alternatives | [Sequence document](../design/behavioral/reservation-sequence-diagram.md) |
| State machine | R1 rental; R2 private parking and rental-return-hold specialization; complete transition tables | [State document](../design/behavioral/reservation-state-machine.md) |

All ten diagrams in this contribution (eight behavioral and two use-case diagrams) have editable `.puml` sources and generated `.svg` previews. PlantUML is chosen because rubric §3.3 explicitly asks for UML; the repo timeline permits `.puml`. Activity diagrams use UML activity notation, not Mermaid flowcharts labelled as standard UML.

### Atomicity, deadlines and retries

M2 orchestrates `core.unit_of_work()`, checks its own booking/Trip and quota under the Core lock, and writes registered M2 entities through `uow.repository` (D-018). Core commands alone change shared claims, vehicles and spaces. Every `Err` exits without commit; a successful explicit commit persists the complete write set. This is the released Core API v1.1 contract, not a callback from Core into M2 (D-015).

At `t = hold_expires_at`, pickup is expired; it is eligible only while `t < expiry`. Time is read inside the serialization boundary. Cancellation, pickup, expiry and resource failure contend on the same current state/version. Only a valid winner commits; a delayed expiry sweep never grants extra pickup time. Active bookings cannot be ended by pickup-deadline expiry.

A repeated request returns the result already recorded. Pickup and return never create a second Trip or reservation or repeat an occupancy change.

### State and data distinctions

Pending is proposed as transient validation with no persisted booking until confirmation. This retains the six assigned state names without inventing durable stranded Pending records. Reservation Active maps to an open IN_PROGRESS/OVERDUE Trip; Completed can map to a normal completion or a verified incident recovery. Vehicle readiness is decided separately by Core. In private parking, Active means occupied; the rental-return hold instead completes on drop-off while the fleet vehicle remains parked.

The [requirements parameter register and data proposal](../requirements/fr-02-05-07-reservation.md) are the authoritative source for values and schema obligations: parking end/arrival fields, Trip expected_return_at, Core ResourceClaim ownership. Default rental duration is 30 minutes with overdue strictly after due+60 minutes. Private parking defaults to 120 minutes and allows start within 24 hours; those intervals do not imply guaranteed departure. Battery thresholds retain their distinct meanings across modules.

### Trade-offs and cross-module risks

- Immediate-only rental avoids forecasting a vehicle's future return. Future charging/private parking remains supported, with actual admission rechecks and overstay handling.
- No automatic destination hold improves use of scarce parking but permits full-Hub return rejection; show this clearly in UI and offer a separate immediate hold.
- Atomic Core transactions suit the proposed single deployment. They require stronger coordination than independent module API calls; DB version columns alone cannot protect interval predicates or user quotas.
- Existing student claims are protected from rebalancing/charging priority. Operator safety isolation remains a separate incident action with accountable custody/occupancy.
- Snapshot simulation must clone claims/bookings/trips and use the same rules with a separate clock/result namespace. Recommendations never write back directly; application is a newly authorized operational command.

All shared choices are **Proposed for team review**. Core interactions follow the released Core API v1.1 and D-015 through D-020; M2 policy values remain subject to team review. Core API/state validation, M3 bundle semantics, M4 dispatch claims/priority, M5 due-time/incident recovery and M7 schema/UI remain explicit handoffs.

### Verification evidence and reproducibility

Design-only review on 2026-10-11 covers the 13 V-M2 scenario groups in the requirements baseline. It checks happy/empty/invalid flows, simultaneous claims and quotas, cancellation/expiry boundaries, repeated pickup/return, full Hubs, faults, bay sharing, redistribution priority and isolated simulation. These are document walkthroughs and future test obligations; **no application tests were run or claimed**.

Render using Java 17 and PlantUML **1.2026.2** (Graphviz 2.44.1 reported by the tool). Set `$plantUmlJar` to the local PlantUML JAR path; the JAR is a tool, not a repository artifact:

```powershell
$plantUmlJar = Join-Path $env:TEMP 'plantuml-m2.jar'
java -jar $plantUmlJar -charset UTF-8 -checkonly 'docs/design/behavioral/reservation-diagrams/*.puml' 'docs/requirements/use-case-diagrams/*.puml'
java -jar $plantUmlJar -charset UTF-8 -tsvg 'docs/design/behavioral/reservation-diagrams/*.puml' 'docs/requirements/use-case-diagrams/*.puml'
java -jar $plantUmlJar -charset UTF-8 -tpng -o "$env:TEMP/m2-diagram-preview" 'docs/design/behavioral/reservation-diagrams/*.puml' 'docs/requirements/use-case-diagrams/*.puml'
git diff --check
```

The initial syntax check and rendering succeeded for all ten sources. PNG previews were inspected for labels, arrows, guard clarity and clipping. Review caught overlapping self-transition labels in R1 and an A3 ordering that could imply waiting until planned end before departure; the source was revised to use internal event text in R1 and explicitly allow earlier departure in A3. Images are regenerated from source, never hand-edited.

Limitations: the Core contract has not been exercised, browser-specific SVG display has not been tested, and system-wide use-case consolidation remains separate. Human review/approval and M8's future implementation tests are still required.

<!-- END M2: Reservation & Trip -->

<!-- BEGIN M3: Charging & Smart Scheduling -->

## M3 contribution - Charging & Smart Scheduling

> Author: Võ Thanh An. Date: 2026-11-06. **Proposed for team review**.

### Design overview

The behavioral design of Module M3 models the complete lifecycle of electric vehicle charging operations, real-time load balancing, and dynamic queue management across Mobility Hubs. The interaction logic operates on a strict **Interlock and State-Driven Architecture**:

1. **Session Lifecycle Execution:** Every session transitions through formal charging states centered around the baseline `AVAILABLE` state. Physical cable connection, parameter validation (`FR-07.M3.1`), and hardware interlocks (`BR-M3-01`) must be satisfied before power relays close and transition the session to `CHARGING`.
2. **Dynamic Priority & Smart Load Balancing:** The background scheduler continuously re-ranks waiting vehicles based on battery depletion urgency (% SoC) and imminent trip schedule proximity (`BR-M3-03`). Vehicles reaching $\text{SoC} \le 15\%$ trigger an immediate `LOW_BATTERY_THRESHOLD` override flag, elevating them to the head of the active queue.
3. **3-Tier Conflict & Fault Resolution:** Hardware point failures or capacity contention (`UC-M3-08`) trigger an automated 3-tier fallback cascade (`BR-M3-02`): (1) local bay swap at zero operational cost, (2) time-slot shift, or (3) escalation to Module M4 (`UC-M4-07`) for cross-Hub alternative routing.

### UML diagram index

| Artifact              | IDs and Intent                                                                                                                              | Detailed Source and Discussion                                                                                                                                                                                   |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Activity Diagram      | Activity workflow covering request validation, dynamic priority queue sorting, load balancing, and 3-tier fault resolution                  | [`charging-activity-diagram.puml`](../design/behavioral/charging-diagrams/charging-activity-diagram.puml) / [Activity Preview](../design/behavioral/charging-diagrams/charging-activity-diagram.svg)             |
| State Machine Diagram | Session lifecycle state transitions enforcing `AVAILABLE` baseline, `PREPARING`, `CHARGING`, `SUSPENDED`, `FAULTED`, and `COMPLETED` states | [`charging-session-state-machine.puml`](../design/behavioral/charging-diagrams/charging-session-state-machine.puml) / [State Preview](../design/behavioral/charging-diagrams/charging-session-state-machine.svg) |

All behavioral diagrams for M3 are maintained as editable `.puml` PlantUML sources with generated `.svg` visual assets in `docs/design/behavioral/charging-diagrams/`.

### Key design decisions

- **OCPP State Alignment & Port Isolation:** The charging state machine strictly adheres to standard EV charging infrastructure protocols (OCPP-compliant states). Ports marked as `OUT_OF_SERVICE` or `FAULTED` are isolated at the database query level, preventing the allocation algorithm from double-booking damaged hardware (NFR-06).
- **Decoupled Grid Load Smoothing:** Power delivery regulation (`SUSPENDED_EVSE`) operates independently from user session state. When peak grid loads occur, energy transfer is temporarily throttled without aborting the underlying user reservation or locking state.
- **Emergency Relay Interlocking:** High-voltage relay disconnects are decoupled from software response loops, triggering hardware-level power isolation within $<100\text{ ms}$ upon fault detection (NFR-08/09).

### Interface alignment and integration

1. **Module M1 (Telemetry Interlock):** M3 listens to M1 telemetry streams for connector latch verification, voltage stability, and thermal alerts before authorizing state transitions (`AVAILABLE` $\rightarrow$ `PREPARING` $\rightarrow$ `CHARGING`).
2. **Module M4 (Cross-Hub Overflow Delegation):** When local Hub capacity is fully saturated or a hardware fault cannot be resolved locally, M3 invokes M4's `AlternativeChargingProvider` port (`UC-M4-07`) to route displaced vehicles to optimal adjacent Hubs.
3. **State Auditability:** All session state changes, priority recalculation events, and fault redirections are written to an immutable event audit log in compliance with NFR-25.
<!-- END M3: Charging & Smart Scheduling -->

<!-- BEGIN M4: Resource Allocation & Dispatching -->
## M4 contribution - Resource Allocation & Dispatching

> Author: 2412466 Huỳnh Minh Nhật. Date: 2026-10-22. **Proposed for team review**.

### Design overview

The allocation module works in two steps. First it **plans** on a read-only view of the network: it finds Hubs that will run short of vehicles and Hubs with surplus, and proposes dispatch tasks. Planning is a pure function, so M6 can reuse it on a copy of the state. Then, after the operator approves a task, it **commits** through Core in one atomic unit of work: M4 places `HolderKind.DISPATCH_TASK` claims on the vehicles and destination spaces directly via Core (D-017), or nothing is claimed. Pick-up transitions the vehicles using those claims; return, cancel and failure each release active `DISPATCH_TASK` claims through Core.

Two further flows are read-only lookups called through Core: alternative Hubs for a reservation request (M2) and an alternative charging point for requests displaced when a Hub has no free port (M3, UC-M3-08, D-012). Competing requests are ordered by class level, then time, then ID (BR-M4-01), and the winner claims the resource atomically.

### UML diagram index

| Artifact | IDs and intent | Detailed source and discussion |
|---|---|---|
| Sequence | S1 plan; S2 approve or reject; S3 carry out or cancel; S4 alternative Hubs for M2; S5 alternative charging for M3 | [Sequence document](../design/behavioral/allocation-sequence-diagram.md) |
| Activity | A1 plan redistribution; A2 approve and execute; A3 settle competing requests | [Activity document](../design/behavioral/allocation-activity-diagram.md) |
| State machine | T1 DispatchTask life cycle with a complete transition table | [State document](../design/behavioral/allocation-state-machine.md) |

All eleven diagrams of this contribution (nine behavioral and two use-case diagrams) have editable `.puml` sources and generated `.svg` previews.

### Key design decisions

The algorithm was chosen among four approaches (threshold rules with greedy matching, min-cost flow, integer programming, reactive only). Threshold rules with greedy matching were chosen because they are fast, repeatable and explainable to an operator; the price is a plan that may not be globally optimal. The comparison, the formulas and a worked example on DS-STD Hubs are in the [algorithm design](../design/architecture/allocation-algorithm-design.md).

Allocation never writes state directly and never calls another module directly; every write and every read of another module's data goes through Core (D-003, NFR-22).

### Interface alignment and integration

1. **Core & Provider Ports:** Settled by Core API spec v1.0 and D-020. M4 calls `ProviderPort.RESERVATION_DEMAND` and `ProviderPort.CHARGING_DEMAND` for planning inputs, and implements `ProviderPort.ALTERNATIVE_HUB` and `ProviderPort.ALTERNATIVE_CHARGING` for M2 and M3.
2. **Dispatch Lifecycle:** Settled by D-016 and D-017. Tasks place `HolderKind.DISPATCH_TASK` claims atomically; vehicles transition through `pickup`, `return`, and `mark_ready`.
3. **Simulation:** The pure planning function `plan(snapshot, demand, tasks, config)` operates on state snapshots and can be run by M6 on isolated simulation state without side effects.
<!-- END M4: Resource Allocation & Dispatching -->
