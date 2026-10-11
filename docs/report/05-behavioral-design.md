# 3.3 Behavioral and Interaction Design

<!-- BEGIN M2: Reservation & Trip -->
## M2 contribution - Reservation & Trip

> Author: 2452620 Đặng Tuấn Kiệt. Date: 2026-10-11. **Proposed for team review**.

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

Core serializes the reservation/resource and per-user admission guards and coordinates M2's persistence through public ports. The unit of work includes the booking, Trip, claim/occupancy, Vehicle, command result and audit/event record as appropriate. A series of separately committed entity updates would violate NFR-09. The concrete unit-of-work API is still proposed and requires M1's Core v1 review.

At `t = hold_expires_at`, pickup is expired; it is eligible only while `t < expiry`. Time is read inside the serialization boundary. Cancellation, pickup, expiry and resource failure contend on the same current state/version. Only a valid winner commits; a delayed expiry sweep never grants extra pickup time. Active bookings cannot be ended by pickup-deadline expiry.

Command keys with payload hashes make exact retries return the original outcome. A unique Trip per rental reservation and guarded completion also prevent new-key retries from creating duplicate trips or returns. A missing response is an unknown outcome, not proof of failure. The UI refreshes current state after replaying an older receipt.

### State and data distinctions

Pending is proposed as transient validation with no persisted booking until confirmation. This retains the six assigned state names without inventing durable stranded Pending records. Reservation Active maps to an open IN_PROGRESS/OVERDUE Trip; Completed can map to a normal completion or a verified incident recovery. Vehicle readiness is decided separately by Core. In private parking, Active means occupied; the rental-return hold instead completes on drop-off while the fleet vehicle remains parked.

The [requirements parameter register and data proposal](../requirements/fr-02-05-07-reservation.md) are the authoritative source for values and schema obligations: parking end/arrival fields, Trip expected_return_at, command-result persistence and Core ResourceClaim ownership. Default rental duration is 30 minutes with overdue strictly after due+60 minutes. Private parking defaults to 120 minutes and allows start within 24 hours; those intervals do not imply guaranteed departure. Battery thresholds retain their distinct meanings across modules.

### Trade-offs and cross-module risks

- Immediate-only rental avoids forecasting a vehicle's future return. Future charging/private parking remains supported, with actual admission rechecks and overstay handling.
- No automatic destination hold improves use of scarce parking but permits full-Hub return rejection; show this clearly in UI and offer a separate immediate hold.
- Atomic Core transactions suit the proposed single deployment. They require stronger coordination than independent module API calls; DB version columns alone cannot protect interval predicates or user quotas.
- Existing student claims are protected from rebalancing/charging priority. Operator safety isolation remains a separate incident action with accountable custody/occupancy.
- Snapshot simulation must clone claims/bookings/trips and use the same rules with a separate clock/result namespace. Recommendations never write back directly; application is a newly authorized operational command.

All shared choices are **Proposed for team review**. Core API/state validation, M3 bundle semantics, M4 dispatch claims/priority, M5 due-time/incident recovery and M7 schema/UI remain explicit handoffs. Source branches are recorded in the baseline, not merged into this contribution.

### Verification evidence and reproducibility

Design-only review on 2026-10-11 covers the 13 V-M2 scenario groups in the requirements baseline. It checks happy/empty/invalid flows, simultaneous claims and quotas, cancellation/expiry boundaries, repeated pickup/return, full Hubs, faults, bay sharing, redistribution priority and isolated simulation. These are document walkthroughs and future test obligations; **no application tests were run or claimed**.

Render using Java 17 and PlantUML **1.2026.2** (Graphviz 2.44.1 reported by the tool). Set `$plantUmlJar` to the local PlantUML JAR path; the JAR is a tool, not a repository artifact:

```powershell
$plantUmlJar = Join-Path $env:TEMP 'plantuml-m2.jar'
java -jar $plantUmlJar -charset UTF-8 -checkonly 'docs/design/behavioral/reservation-diagrams/*.puml' 'docs/requirements/use-case-diagrams/uc-m2-*.puml'
java -jar $plantUmlJar -charset UTF-8 -tsvg 'docs/design/behavioral/reservation-diagrams/*.puml' 'docs/requirements/use-case-diagrams/uc-m2-*.puml'
java -jar $plantUmlJar -charset UTF-8 -tpng -o "$env:TEMP/m2-diagram-preview" 'docs/design/behavioral/reservation-diagrams/*.puml' 'docs/requirements/use-case-diagrams/uc-m2-*.puml'
git diff --check
```

The initial syntax check and rendering succeeded for all ten sources. PNG previews were inspected for labels, arrows, guard clarity and clipping. Review caught overlapping self-transition labels in R1 and an A3 ordering that could imply waiting until planned end before departure; the source was revised to use internal event text in R1 and explicitly allow earlier departure in A3. Final verification results are recorded in the [review handoff](../reviews/m2-phase1-review.md). Images are regenerated from source, never hand-edited.

Limitations: the Core contract has not been exercised, browser-specific SVG display has not been tested, and system-wide use-case consolidation remains separate. Human review/approval and M8's future implementation tests are still required.

### Proposed M2 review schedule

Repository commitments: M2 Phase 1 due **2026-10-23**, team design review **2026-10-25**; M1 Core API v1 due **2026-10-19**. The following intermediate dates are proposed, not changes to the shared timeline. All dates use ICT.

| Date | Proposed action / exit condition |
|---|---|
| Oct 11 | Draft package produced; identify missing M2 Phase 0 and inspect all six dependency PR heads |
| Oct 12-13 | M2/M8 reconcile UC/BR IDs; M1/M3/M4/M5 discuss parameters and dependency table |
| Oct 14-16 | Review A1-A3, S1-S3 and R1-R2 against M1 architecture/class draft; agree bay/claim and Trip due-time data with M7 |
| Oct 19-20 | Compare every proposed interaction with Core API v1; resolve unit-of-work, Vehicle transition and event/retry gaps |
| Oct 21 | Refresh requirements/behavioral report sections and traceability; regenerate diagrams after agreed changes |
| Oct 22 | Submit review-ready M2 branch/PR to M7; request targeted input from M1/M3/M4/M5 through the team process |
| Oct 23 | Address M7 feedback; freeze M2 deliverables for the repository deadline |
| Oct 24 | Buffer for interface reconciliation and M8 report consistency checks |
| Oct 25 | Attend mandatory team design review; record accepted decisions through owners, not retroactively in this draft |
<!-- END M2: Reservation & Trip -->
