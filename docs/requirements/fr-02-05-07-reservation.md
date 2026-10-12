# M2 - Reservation & Trip: requirements and design baseline

> Owner: M2 - 2452620 Đặng Tuấn Kiệt. Date: 2026-10-11 (ICT).
> Status: **Proposed for team review**. Phase 1 design with the missing M2 Phase 0 FR/UC/BR foundation supplied here. This is not approval of shared interfaces, parameters or other modules' drafts.

## 1. Scope and evidence

M2 owns FR-02, FR-03, FR-04, FR-05 and the parking part of FR-07. Trips are Hub-to-Hub. Payment, penalties, GPS, route planning, physical unlocking and hardware control are excluded. Student actions and simulated events represent pickup/return/occupancy. M3 owns charging and private-vehicle charging-profile registration; M2 consumes registered ownership data. M1 owns authentication and resource state; M7 owns UI and schema integration. M2 does not write another module's tables directly.

The following sources were read on 2026-10-11, after `git fetch origin`. Working tree and index were initially clean on `main`. `main`, `origin/main` and `origin/develop` pointed to `46811d57f5f99cd026b29ddae42503d9744084ab`. No AGENTS.md was found in the repository or its inspected parents. No dependency branch was merged or checked out.

| Source | Exact revision / status at inspection | Material used |
|---|---|---|
| README.md; CONTRIBUTING.md; .github/pull_request_template.md; .github/CODEOWNERS; docs/task-assignment-timeline.md | Base `46811d5` | Scope, IDs, module boundaries, paths, reviewer and deadlines |
| docs/DECISIONS.md; docs/requirements/nfr.md; docs/requirements/reference-dataset.md; docs/design/architecture/tech-stack-proposal.md; docs/report/01-introduction.md | Base `46811d5` | D-002/003/005/007 remain Proposed; A-01 to A-11 are assumptions; NFRs are draft targets |
| [Assignment](assignment-spec.pdf), pp. 1-4; [rubric](guideline-rubric.pdf), pp. 1-7 | Base `46811d5`; text extracted from all pages | UML behavioral diagrams (§3.3), use-case diagrams (§2.5), traceability and truthful AI declaration |
| [M3 PR #7](https://github.com/MabC06/smart-e-mobility-hub/pull/7), `docs/requirements/FR-06-07-11.md` | `docs/charging-scheduling-requirements` @ `82279820bf702ba52fd6b7af60adad2471064c66`; open, no submitted human approval | Future charging, registration, BR-08/09/10 |
| [M4 PR #1](https://github.com/MabC06/smart-e-mobility-hub/pull/1), `docs/requirements/fr-10-11-allocation.md` | `docs/allocation-requirements` @ `169cf41158e76ce66bd75174f35bd41a4e5c5d03`; open, latest M1 review APPROVED on this head | BR-A01 to BR-A12; UC-A01 to UC-A09 |
| [M5 PR #10](https://github.com/MabC06/smart-e-mobility-hub/pull/10), `docs/requirements/fr-08-09-monitoring-incident.md` | `docs/monitoring-incident-requirements` @ `814502625c4ff402c409cfd0d4a3ffcaca125022`; open, no submitted human approval | Rental lockout, critical battery, overdue and capacity incidents |
| [M6 PR #9](https://github.com/MabC06/smart-e-mobility-hub/pull/9), `docs/requirements/FR-12.md` | `docs/simulation-fr12-requirements` @ `f72aced42357a459885e748be424d4e5c77234bf`; open, no submitted human approval | Isolated snapshot, low-battery metric, recommendations |
| [M7 PR #8](https://github.com/MabC06/smart-e-mobility-hub/pull/8), `docs/design/structural/erd-entities-draft.md`; `docs/requirements/use-case-operator-support.md` | `docs/ui-phase0-operator-erd` @ `c3dae2835086076e495d63e105c67f5359f044b4`; open; bot COMMENTED that review quota was exhausted, not an approval | Reservation/Trip entities, nullable charging-bay association, operator UC mappings |
| [M8 PR #5](https://github.com/MabC06/smart-e-mobility-hub/pull/5), `docs/testing/test-plan-skeleton.md`; `docs/testing/traceability-sheet.md`; `docs/ai-usage/_template.md` | `docs/test-m8-phase0` @ `f8b687aeac81c483c0350197b1dec6c3006a940a`; open, M1 APPROVED on this head | Test techniques, unassigned BR/UC/TC register, AI log structure |

PR approval does not make every cross-module assumption Accepted. No Core API spec, Core class diagram or Vehicle state-machine document exists in the fetched branch trees. The timeline's list of Vehicle states and M7's enum are provisional inputs, not a validated M1 transition contract. M2's former Phase 0 file, consolidated actor analysis and five system-wide use-case diagrams are absent. This change supplies only M2's foundation and two scoped use-case diagrams, not all of Phase 0.

## 2. Dependency reconciliation before design

| Source | Relevant rule/data | Effect on M2 | Unresolved mismatch | Proposed resolution | Confirm with |
|---|---|---|---|---|---|
| M1 D-007, dataset §2; M3 BR-08/09; M7 ChargingPoint | Charging occupies one bay | Parking and charging need one capacity claim | D-007 is 1:1; M7 FK nullable | A schedulable charger must reference one unique same-Hub space. An unbound charger cannot be scheduled. Joint confirmation commits the bay interval and charger interval together; one vehicle counts once. | M1/M3/M7 |
| M3 future charging; M7 ParkingSpace.status | Future booking differs from present occupancy | A status enum alone cannot represent a calendar | No full parking end-time model | Separate current occupancy, immediate hold and future interval claims; add scheduled_end_time and claim linkage (§7). Never free occupancy on cancellation of a booking/session. | M1/M3/M7 |
| M3 UC-07.1/07.2; M1 A-03 | Connector validation vs universal compatibility | Private EV booking prerequisites | M3 profiles require connector type; baseline has universal chargers | Keep A-03 for the baseline fixture; compatibility predicate returns true for supported types. Profile fields can be stored by M3; unsupported type fails validation, no new hardware scope. | M1/M3 |
| M4 BR-A01/A02; M3 BR-10 | Priority, low-battery override | Competing resource admission | Override scope is unspecified | Apply M4 class priority to uncommitted requests; M3 override only reorders eligible waiting requests within its allocated charging class, using the next unclaimed bay. No preemption of Confirmed/Active claims for charging or rebalancing. Safety isolation is a separate incident, not priority stealing. | M1/M3/M4 |
| M4 open point 2; M7 Reservation and RedistributionTask | Proposed REBALANCE reservation | Allocation ownership and user limits | Required user_id; no REBALANCE enum; task enums also differ | Keep student Reservation separate. Propose a Core ResourceClaim with exactly one owner: student reservation or RedistributionTask. Reuse claim invariants, not a fake student. M4 owns dispatch lifecycle; do not silently add REBALANCE to M2. | M1/M4/M7 |
| M4 UC-A05/BR-A10 | Alternative-Hub query | Search and full-Hub return | Public interface absent | M2 calls Core facade; Core delegates ranking to M4. Results are advisory, timestamped and hold no resource. Revalidate only when user confirms. | M1/M4/M7 |
| M5 BR-09-03/INC-BAT-01; M3 BR-10; M6 FR-12.4 | <=15%, <=10%, <15%, <20% | Admission, incident and analytics differ | Same word “low” for different purposes | Preserve distinct names and comparisons (§3). Propose rental minimum 20%, which is stricter than safety lockout; 15% is blocked, 20% is eligible absent other faults. | M1/M3/M4/M5/M6 |
| M5 INC-USR-01; M7 Trip | More than 60 min after expected return | Overdue cannot be calculated without a due time | No expected_return_at in Trip | Add planned_duration_minutes and immutable expected_return_at calculated at actual pickup. No extension or fine in M2 baseline; overdue does not auto-complete the trip. | M2/M5/M7 |
| M5 incidents; M7 UC-OP-02/08 | Failure before/during use | Reservation cannot force Vehicle Available | M7 repair flow broadly restores Available | Before pickup, cancel affected booking with reason and keep parked occupancy; in use, keep Active until verified return/custody recovery, never expire it. Core decides vehicle readiness after repair/return. M5 hardware commands mean simulated state changes here. | M1/M5/M7 |
| M7 status enums | Six reservation states, separate Trip | Lifecycle mapping | Persistent Pending semantics unspecified | Pending is transient validation with no durable reservation/claim; failed submission produces an error, not a seventh persisted state. Retain all six names in design (§6). | M1/M7 |
| M3/M4/M5/M6/M7/M8 ID catalogs | UC-Axx, UC-OP-xx, UC-06.x, UC-08, UC-12 | Cross-module traceability | CONTRIBUTING requests UC-xx/BR-xx; M8 has placeholders | Use visibly provisional UC-M2/BR-M2 IDs here; propose numeric mapping (§8), no renumbering of other work and no official TC allocation. | M2/M8/team |
| M6 BR-SIM-01/02; M7 UC-OP-10 | Snapshot execution and later application | Same rules with isolated clock/store | “Incentives” might imply billing | Use informational redirection only. Snapshot includes reservations/trips/claims, not just resources. Applying a recommendation is a separately confirmed operational command with fresh checks. | M1/M4/M6/M7 |
| Timeline vs old architecture/NFR/M8 text | Core API due 19/10; M2 due 23/10; review 25/10 | Handoff dates | Stack proposal says 20/10 API and 26/10 architecture; A-10 says Nov 25 vs timeline Nov 24; NFR Sprint 2 dates and M8 early Test Plan date are stale | Use current task timeline for planning. Keep source files unchanged. M1/M8 reconcile their dates. M6's 15 s timeout vs NFR-05's 30 s remains M1/M6/M8 scope, not a reservation hold time. | M1/M8 |

## 3. Canonical parameter register

**This table is the single source of M2 parameter values. All rows are Proposed for team review, including values carried from unmerged PRs.** No Accepted numeric reservation policy was found. Names below are design names, not existing environment variables or API fields. Changing a value requires revising its BR, diagram guards and report references together.

| Parameter | Proposed value | Unit | Meaning | Rationale | Boundary behavior | Affected modules | Approval status |
|---|---|---|---|---|---|---|---|
| RENTAL_HOLD | 10 | minutes | hold_expires_at = confirmed_at + 10 min | Short campus walk to pickup | pickup only while t < expiry; t >= expiry is expired | M1/M2/M7 | Proposed; M1/M2/M7 |
| RENTAL_ADVANCE | 0 | minutes | Immediate rental only; scheduled_start_time = confirmed_at | Avoid promising a vehicle whose return is unknown | Future rental start rejected; M3 may still schedule charging | M2/M3/M4/M7 | Proposed; M2/M3/M4 |
| PICKUP_GRACE | 0 | minutes | No grace after the hold | One unambiguous deadline | Exactly expiry is too late | M1/M2/M7 | Proposed; M1/M2 |
| CANCELLATION | Before activation and expiry | condition | Owner cancels Confirmed | Prevent cancelling an actual trip/parked vehicle | t < expiry and state Confirmed; otherwise invalid or expired | M1/M2/M7 | Proposed; M2 |
| EXPIRY_SWEEP | 30 | seconds | Background cleanup interval | Bounded stale UI/holds | Correctness never waits for sweep: touched expired claims are settled atomically before admission; expired claim unusable at t >= expiry | M1/M2/M7 | Proposed; M1 |
| PARKING_ADVANCE | 24 | hours | Private parking start in [t, t+24 h] | One campus day | Exactly +24 h allowed; earlier than now or later rejected | M2/M3/M7 | Proposed; M2/M3 |
| PARKING_DURATION | 120 default; 30 to 240 inclusive | minutes | Private planned interval [start,end) | Class-length stay with bounded planning | end = start + duration; end is not proof of departure | M2/M3/M5/M7 | Proposed; M2/M3/M5 |
| PARKING_ARRIVAL | [start, start+10 min) | window | No early entry; arrival deadline is hold_expires_at | Simple check-in rule, less than minimum stay | At start allowed; at start+10 expired; late arrival needs a new booking | M2/M3/M7 | Proposed; M2/M3 |
| PARKING_OVERSTAY | t >= scheduled_end_time | condition | Keep occupancy; notify M5 for review | A clock cannot remove a vehicle | No automatic release, fine or automatic extension; next arrival may need reassignment | M1/M2/M5 | Proposed; M1/M5 |
| RENTAL_PLANNED_DURATION | 30 default; 5 to 120 inclusive | minutes | expected_return_at = pickup_time + chosen duration | Supplies M5's overdue baseline | Early/late return allowed subject to capacity; no automatic expiry of Active | M2/M5/M7 | Proposed; M2/M5 |
| RENTAL_OVERDUE_GRACE | 60 | minutes | M5 INC-USR-01 trigger | Preserve M5 proposal | t > expected_return_at+60 min; equality is not overdue | M2/M5/M7 | Proposed; M5 |
| RENTAL_MIN_SOC | 20 | percent | Search/confirmation/pickup minimum | Usable campus buffer, distinct from safety floor | soc >= max(20, requested minimum); range 0..100; unknown battery ineligible | M1/M2/M3/M4 | Proposed; M1/M3/M4 |
| RENTAL_POOL_LOCKOUT | 15 | percent | M5 BR-09-03 | Safety exclusion | soc <=15 is blocked independently of search filter | M1/M2/M5 | Proposed; M5 |
| BATTERY_CRITICAL_INCIDENT | 10 | percent | M5 INC-BAT-01 | Incident severity | soc <=10 triggers incident | M1/M5 | Proposed; M5 |
| CHARGING_URGENT_SOC | 15 | percent | M3 BR-10 example adopted for review | Queue urgency, not rental eligibility | soc <15; at 15 no special override; only next unclaimed bay | M3/M4 | Proposed; M3/M4 |
| SIMULATION_LOW_SOC | 20 | percent | M6 depletion metric | Analytics only | soc <20; at 20 not depleted for this metric | M6 | Proposed; M6 |
| UPCOMING_WINDOW | 30 | minutes | 0 <= scheduled_start_time-t <=30 min, plus all unexpired immediate rental holds | Common view for M3/M4 | Expired claims excluded; all Confirmed/Active claims protected even outside window | M1/M2/M3/M4 | Proposed; M1/M3/M4 |
| STUDENT_LIMITS | 1 rental and 1 parking | live reservation per category | Count Confirmed + Active, including future parking | Prevent hoarding; parking+charging bundle counts once | Check per-user counters atomically across different resources; terminal records excluded | M1/M2/M7 | Proposed; M1/M2 |
| DESTINATION_AUTO_HOLD | No | boolean | Rental booking does not reserve return capacity | Destination and arrival can change | Show “return space not reserved”; optional separate FR-05 hold below | M2/M4/M7 | Proposed; M2/M4 |
| RENTAL_RETURN_PARKING_HOLD | 10 | minutes | Active trip may reserve an empty destination space now | Useful FR-05 support without predicting rental dwell | No advance start; arrival before expiry; on successful return booking Completed, physical occupancy remains until vehicle leaves | M1/M2/M4/M7 | Proposed; M1/M2/M4 |
| TIME_BASIS | UTC storage; Asia/Ho_Chi_Minh display | zone | Follow proposed D-005; injectable authoritative clock | Reproducible events/simulations | Time read inside serialized command, not from client clock; compare instants at stored precision | M1-M8 | Proposed D-005; M1 |

Interval overlap is `a.start < b.end AND b.start < a.end`; equal endpoints do not overlap. There is no early-arrival buffer. A return-parking hold blocks its space from confirmation until arrival/expiry; after return, real occupancy has no assumed end. Therefore, confirm a rental return-space hold only on a space with no other future commitment, and do not place a future booking behind that live return hold. If it expires unused, the space can be offered again; if consumed, verified departure is required. An occupied space with no verified departure is not offered for a new future booking. Multiple non-overlapping private-stay claims on an empty space may be planned, but admission always checks actual occupancy; an overstay triggers reassignment or explicit failure, never overcapacity. This is a capacity plan, not a guarantee against incidents or overstays.

Processing timeouts are separate from all business deadlines. Propose a 5-second UI wait before displaying “outcome unknown; checking status”, not “booking failed”. Retrying uses the same command key. No timeout frees a hold or completes a trip. The transaction/deduplication result, not the HTTP response, determines success. This operational proposal requires M1/M7 review and does not replace NFR-03's 1-second p95 target.

## 4. Functional requirements and acceptance criteria

All operations require an authenticated active Student account (NFR-16); derive user identity from the trusted session. Unknown/foreign reservation IDs yield NOT_FOUND_OR_NOT_OWNED without revealing another student's data. IDs below keep README numbering; FR-07 here is explicitly only its parking slice.

| FR | Input and required behavior/output | Acceptance criteria (design obligations, not executed tests) |
|---|---|---|
| FR-02 | Origin Hub, optional destination Hub, supported vehicle type and minimum battery. Return fleet candidates with ID/type, Hub, battery, availability, version and as_of time; show destination free-capacity snapshot, never a guarantee. Filter by Core eligibility and BR-M2-02; sort battery descending then vehicle ID. | Invalid Hub/type or minimum outside 0..100 gives field error and no mutation. Empty results give NO_VEHICLE and advisory alternatives. Private, reserved, charging, faulty or low-battery vehicles are excluded. Stale search result may lose at confirmation. |
| FR-03 | Chosen vehicle/origin, optional destination, planned duration, requested minimum, observed version and command key. Confirm a ten-minute hold or return a reason. Owner may cancel before pickup. | Exactly one concurrent contender acquires a vehicle; user limit checked even for different vehicles. Successful response includes reservation ID, Confirmed, expiry and server time. Cancel/expiry releases the vehicle claim, never its occupied origin space. Duplicate commands do not create another reservation. |
| FR-04 | Reservation ID and pickup Hub for pickup; trip ID, destination Hub and optional parking booking ID for return; command keys and versions. Create one Trip at pickup and record actual return. | Wrong owner, expiry, changed vehicle eligibility or wrong Hub prevents pickup. Pickup atomically makes reservation Active, Trip IN_PROGRESS, vehicle IN_USE and frees origin occupancy. Return atomically occupies an admissible destination space, completes trip/booking and records vehicle RETURNED or MAINTENANCE; full Hub leaves trip Active and offers advisory alternatives. |
| FR-05 | Hub plus arrival interval/private vehicle, or an owned Active trip for immediate return-space hold. Return parking reservation ID, assigned space, arrival deadline and planned end when applicable. Support cancellation, arrival and departure. | No two overlapping claims for one space and no two actual occupants. At expiry no admission. Cancel releases only the claim. Private departure releases actual occupancy after confirmation through Core. Rental return consumes its hold once but does not free the returned vehicle's space. |
| FR-07 (parking) | An owned registered PRIVATE vehicle, Hub/start/duration, optional M3 charging request correlation. Confirm private parking or return validation/conflict reason. | Another owner's/unregistered vehicle is rejected; private vehicles never appear in FR-02 fleet results. Charging bundle confirms the bay and charger jointly, counting one parking space, or neither. Charging cancellation alone leaves active parking intact. No rental Trip is created for private parking. |

## 5. Business rules (provisional M2 IDs)

| ID | Rule |
|---|---|
| BR-M2-01 | Validate role, ownership, entity existence, type/range, Hub association and reservation type for each command; never trust client user_id, time or battery. |
| BR-M2-02 | Search/confirmation eligibility requires FLEET, Core Available, current origin occupancy, no incident/dispatch/charging/other claim, known battery meeting RENTAL_MIN_SOC and requested minimum, and no M5 lockout. At pickup require Core Reserved with this booking's own claim instead of Available; recheck all other eligibility conditions. |
| BR-M2-03 | Enforce STUDENT_LIMITS atomically for all live bookings. Joint parking/charging counts once; dispatch claims do not consume student quota. |
| BR-M2-04 | Use canonical hold/arrival windows (§3). Rental is immediate only. At t >= hold_expires_at a Confirmed reservation is unusable. Process expiry as a distinct valid transition; Active never expires from a pickup deadline. |
| BR-M2-05 | Owner cancellation is allowed only in Confirmed and before expiry. Cancel/expire removes unconsumed claims, not occupied spaces. Core re-evaluates readiness before making a formerly reserved vehicle Available. |
| BR-M2-06 | Core serializes competing commands and checks resource versions, per-user limits, vehicle uniqueness and interval exclusion in the same transaction. No read-then-write gap. First admissible serialized command wins among same-class requests; M4's earlier accepted request time then lower ID is the proposed tie-break if requests are queued together. No retrospective preemption after commit. |
| BR-M2-07 | Each mutation carries a key unique per (actor, operation, key), with a canonical payload hash. Exact retry returns recorded outcome and entity IDs; changed payload under the same key returns KEY_REUSE. Retain successful keys for the entity's retained lifetime; retain rejected outcomes for 24 h. A new attempt after changed conditions uses a new key. Natural constraints (one Trip per rental Reservation, one completion per Trip) also prevent duplicates after key loss. |
| BR-M2-08 | Each reserve/pickup/return/cancel/expire/joint-bay operation commits every affected reservation, trip, resource claim, occupancy and audit/result record or rolls back all. Core coordinates the transaction through public interfaces; M2 never independently commits a vehicle update. Notification failure after commit does not roll back business success. |
| BR-M2-09 | Pickup requires owner, Confirmed, correct origin and t < expiry, plus current eligibility with this reservation's own claim permitted. It creates one IN_PROGRESS Trip with expected_return_at from actual pickup and releases precisely the occupied origin space. |
| BR-M2-10 | Return requires owned Active rental and open Trip, a valid receiving Hub, and an available space or the student's valid matching hold. Capacity check and occupancy commit are one operation. Full/failed destination leaves trip, vehicle location and reservation unchanged. Consume only a matching hold; an unrelated destination hold remains until explicit cancellation/expiry, with a UI reminder. Return completion is not vehicle rental readiness. |
| BR-M2-11 | Parking uses interval exclusion plus actual occupancy checks (§3). On private arrival consume claim into one occupancy; on departure close booking and release that occupancy. End time/charging completion alone never frees parking. Rental return parking completes upon successful rental return while the space remains occupied by the fleet vehicle. |
| BR-M2-12 | A charging bundle reserves one same-Hub bay and charger for compatible intervals in one Core transaction. Charger interval must lie within parking interval. Reuse the vehicle's matching occupancy/claim instead of adding a second space. No connector-only allocation without parking. Cancel before arrival can cancel the whole bundle through coordinated M2/M3 commands; reject parking-only cancellation while a linked charging commitment exists. |
| BR-M2-13 | Preserve Confirmed/Active claims against charging/rebalancing priority. Upcoming means §3; all unexpired immediate holds qualify. ResourceClaim owner is either Reservation or RedistributionTask. M4 alternatives are read-only and never silently change the chosen Hub or hold resources. |
| BR-M2-14 | Core-accepted failure before pickup cancels the booking with RESOURCE_UNAVAILABLE, releases the exclusive claim and keeps vehicle/space physically occupied and unavailable. During a trip record the incident but keep Reservation Active and Trip open until verified return or operator-confirmed custody recovery. Only then finish with Trip INCIDENT_ABORTED and Reservation Completed; no fabricated arrival/space release. |
| BR-M2-15 | At t > expected_return_at +60 min the open Trip becomes OVERDUE through M5/Core; reservation stays Active. At private parking end, mark overstay for M5 while keeping Active and occupied. No fines, auto-extension or forced completion. |
| BR-M2-16 | Evaluate identical admission and lifecycle rules with explicit state/clock context in simulation. Clone bookings, trips, claims and command-result namespace too. Simulation writes/events stay in its namespace; only a separately confirmed fresh operational command can apply a recommendation. |

Replay lookup follows authentication and precedes version checks; a replay returns the original operation outcome, not a new state transition. UI refreshes current state separately so an old confirmation receipt is not mistaken for a still-live hold. A new-key pickup of an already Active booking returns the existing Trip as ALREADY_ACTIVE; a new-key return of a Completed trip returns ALREADY_COMPLETED without modifying destination or timestamps. Conflicting destination/payload is rejected. A reservation already Cancelled/Expired cannot be revived.

For deadlines, Core checks time **after acquiring the serialization boundary**. Pickup and cancel/expire race on the same reservation version. Exactly one valid transition commits. A sweep delay cannot extend eligibility. An expired-reservation maintenance transition may commit before a rejected pickup; it is separately logged, not a partial pickup. Safety-event ordering also uses Core's accepted sequence, not client event timestamps.

## 6. Use-case specifications

The system boundary is the whole Smart E-Mobility Hub. Student is the primary actor; Private EV Owner is a Student role. Operator is external for incident recovery; the simulated sensor/event source is external per D-004. UI, Core, Reservation and the internal expiry scheduler are **not** external use-case actors. Timer expiry is an internal event, not a human goal.

All UC-M2 IDs are provisional (§8). Shared preconditions: authenticated active Student, reachable Core; failures return a reason and no command side effects except separately identified expiry/incident transitions. All mutations follow BR-M2-06/07/08. UML sources/previews: [rental](use-case-diagrams/uc-m2-rental.svg) ([source](use-case-diagrams/uc-m2-rental.puml)) and [parking](use-case-diagrams/uc-m2-parking.svg) ([source](use-case-diagrams/uc-m2-parking.puml)). These are scoped additions, not replacements for the missing consolidated Phase 0 diagrams.

### UC-M2-01 - Find suitable rental vehicles

- **Actor / goal:** Student; find a usable fleet vehicle and inspect destination capacity.
- **Trigger:** Student submits Hub and filter choices.
- **Preconditions:** Shared preconditions; no booking required.
- **Main flow:** 1. Select origin, optional destination, type and minimum battery. 2. Validate fields. 3. Read Core snapshot and apply eligibility filter. 4. Sort and show candidates, battery, as_of and destination capacity. 5. Student selects a candidate for UC-M2-02.
- **Alternatives/exceptions:** Invalid field gives a field error; no match gives NO_VEHICLE and Core/M4 advisory Hub alternatives; Core unavailable gives retry feedback, not an empty-success list. Selecting an alternative reruns the search and makes no hold.
- **Postconditions:** No resources changed; results may change before confirmation.
- **Trace:** FR-02; BR-M2-01/02/13/16.

### UC-M2-02 - Reserve a rental vehicle

- **Actor / goal:** Student; secure immediate pickup.
- **Trigger:** Confirm selected vehicle, planned duration and optional destination.
- **Preconditions:** Shared preconditions; valid selected fleet vehicle; no live rental for the student.
- **Main flow:** 1. UI sends key, vehicle/origin, filters, duration and observed version. 2. Validate and check replay. 3. At Core serialization boundary read fresh eligibility/time/quota. 4. Atomically create Confirmed reservation and claim, set Vehicle Reserved and retain origin occupancy. 5. Show ten-minute deadline, ID and explicit absence of an automatic return-space hold.
- **Alternatives/exceptions:** Stale version/concurrent booking yields CONFLICT; low battery, fault, dispatch or charging yields RESOURCE_UNAVAILABLE; quota yields LIMIT_REACHED; future rental start rejected. Failed attempt holds nothing. Exact retry returns its original result; timeout triggers status lookup using the same key.
- **Postconditions:** One exclusive vehicle hold or none; no Trip yet; no destination claim.
- **Trace:** FR-03; BR-M2-01/02/03/04/06/07/08/13.

### UC-M2-03 - Cancel a rental reservation

- **Actor / goal:** Student; release an unused rental hold.
- **Trigger:** Select Cancel on own reservation.
- **Preconditions:** Shared preconditions; owned Confirmed booking and t < expiry.
- **Main flow:** 1. Send ID/key. 2. Validate owner/time/state at Core boundary. 3. Commit Cancelled and release vehicle claim. 4. Core chooses eligible Available or unavailable state; leave origin occupancy unchanged. 5. Show cancellation receipt.
- **Alternatives/exceptions:** At expiry, process expiry instead and report EXPIRED. Concurrent pickup winner makes cancellation invalid; do not undo the Trip. Exact retry returns original result; already Cancelled returns ALREADY_CANCELLED. Active/Completed rejected.
- **Postconditions:** Cancelled hold no longer blocks resource; parked vehicle remains parked.
- **Trace:** FR-03; BR-M2-01/04/05/06/07/08.

### UC-M2-04 - Pick up a rental vehicle

- **Actor / goal:** Student; start the reserved trip.
- **Trigger:** Student confirms pickup at origin Hub in UI.
- **Preconditions:** Shared preconditions; own Confirmed rental, correct origin, t < expiry, vehicle still eligible except for own reservation claim.
- **Main flow:** 1. Submit booking/origin/key/version. 2. Core checks owner, deadline, resource and competing events. 3. Commit Active reservation, unique IN_PROGRESS Trip and expected_return_at; set Vehicle InUse, clear current Hub/space and free the source occupancy. 4. Return trip ID, pickup time and expected return time.
- **Alternatives/exceptions:** t = expiry is expired; wrong owner/Hub fails; current fault cancels via separate incident transition, not pickup; low battery makes vehicle ineligible and cancels with reason. Cancel/expiry winning the race prevents Trip creation. Retry returns existing Trip once.
- **Postconditions:** One open trip and no source occupancy, or no pickup effects.
- **Trace:** FR-04; BR-M2-01/02/04/06/07/08/09/14/15.

### UC-M2-05 - Return a rental vehicle

- **Actor / goal:** Student; finish trip at an accepting Hub.
- **Trigger:** Student selects destination and confirms return.
- **Preconditions:** Shared preconditions; own Active rental and IN_PROGRESS/OVERDUE Trip (including incident flag); vehicle is in student's custody.
- **Main flow:** 1. Send trip/destination, optional matching parking hold and key. 2. Core checks owner/open trip and destination serviceability. 3. Select own valid held space or an unclaimed available space with no future commitment that indefinite fleet occupancy would violate. 4. Atomically occupy destination, record actual Hub/time/battery, complete Trip/reservation, consume matching parking hold and set Vehicle Returned (Maintenance if fault). 5. Show receipt; Core/M3 separately determine charging/readiness.
- **Alternatives/exceptions:** Full/blocked Hub returns NO_PARKING and advisory alternatives through Core/M4; choosing one requires a new confirmation. Expired destination hold offers a new unheld capacity check without reviving the hold. Changed resources cause CONFLICT and rollback. Fault does not invent physical recovery: normal return can still park safely if Hub accepts it; operator recovery is separately authorized under BR-M2-14. Duplicate return never moves a completed vehicle again.
- **Postconditions:** Trip ends once with one destination occupancy; or rental remains Active and current in-trip location unchanged.
- **Trace:** FR-04/05; BR-M2-01/06/07/08/10/11/13/14/15.

### UC-M2-06 - Reserve parking

- **Actor / goal:** Student (private EV owner or active renter); obtain an arrival space.
- **Trigger:** Confirm Hub and parking request.
- **Preconditions:** Shared preconditions; no live parking booking; owned registered private EV, or owned Active rental Trip.
- **Main flow:** 1. For private EV choose start within 24 h and duration 30..240 min (default 120); for rental return use immediate ten-minute hold. 2. Validate vehicle association, quota and times. 3. Through Core select a usable space, check interval exclusion/occupancy and commit Confirmed booking/claim. 4. Show space, arrival window/deadline and planned end when private.
- **Alternatives/exceptions:** Full Hub, overlapping claim, different owner, invalid duration or concurrent request rejects without claim. Charging option delegates charging validation to M3 through Core; commit linked bay+charger together or neither. Already parked same vehicle reuses its occupancy only through coordinated validation; it must not create duplicate occupancy. No early admission or automatic extension.
- **Postconditions:** One exclusive claim (one bay for a bundle), no occupancy created before actual arrival.
- **Trace:** FR-05/07 parking; BR-M2-01/03/06/07/08/11/12/13.

### UC-M2-07 - Cancel parking

- **Actor / goal:** Student; release an unused parking commitment.
- **Trigger:** Cancel own parking reservation before arrival.
- **Preconditions:** Shared preconditions; own Confirmed parking and before arrival deadline; future booking may be cancelled immediately.
- **Main flow:** 1. Submit ID/key. 2. Check ownership/state/linkage. 3. If bundled, coordinate cancellation of the unstarted charging claim and parking claim through Core/M3. 4. Commit Cancelled and show receipt.
- **Alternatives/exceptions:** Parking-only cancellation with a linked charging commitment rejects LINKED_CHARGING; offer bundle cancellation. Active parking requires departure UC-M2-08, not cancellation. At deadline expiry wins. Concurrent arrival/cancel serializes; winner determines state. Retry does not release twice.
- **Postconditions:** Only unconsumed claims removed; never remove physical occupancy or an independently active charging session.
- **Trace:** FR-05/07 parking; BR-M2-01/04/05/06/07/08/11/12.

### UC-M2-08 - Arrive at and leave private parking

- **Actor / goal:** Private EV owner (Student); use and release the booked space.
- **Trigger:** Confirm arrival, later confirm departure in UI; simulated occupancy evidence enters via Core.
- **Preconditions:** Shared preconditions; own private-parking reservation; arrival in [start, expiry), or departure from Active with matching vehicle occupancy.
- **Main flow:** 1. Arrival validates owner, time and space under serialization. 2. Consume claim into one occupancy and set booking Active. 3. If charging was linked, M3 starts only with valid bay occupancy/connection simulation. 4. On departure, coordinate stop/completion of any active charging and Core occupancy removal in one accepted departure operation. 5. Set booking Completed and actual ended_at.
- **Alternatives/exceptions:** Early arrival rejected; at deadline expires. Unexpected occupant/overstay: try free compatible replacement with atomic claim transfer (plus charger if bundled), otherwise report RESOURCE_UNAVAILABLE, cancel unconsumed claim and offer alternatives. At planned end remain Active/occupied and notify M5. Charging stop failure prevents departure commit and preserves occupancy. Repeated arrival/departure returns prior outcome. Rental destination parking uses UC-M2-05, not this private departure flow.
- **Postconditions:** On arrival one parked private EV and no rental Trip; on departure no occupancy from this stay; on failure no partial mutation.
- **Trace:** FR-05/07 parking; BR-M2-01/04/06/07/08/11/12/14/15.

## 7. Proposed data and interaction obligations

These are **proposed interaction contract** requirements for M1/M7, not existing methods, endpoints or schema migrations. The sequence document expands transaction boundaries.

| Item | Required information / invariant | Difference from M7 draft |
|---|---|---|
| Rental Reservation | confirmed_at, selected_min_soc, planned_duration_minutes, hold_expires_at, version; scheduled_start_time = confirmed_at | Add confirmation/filter/duration fields; duration is not the hold |
| Trip | unique reservation_id; expected_return_at, actual pickup/return, incident reference/flag; origin/destination and occupant association | Add due time and incident association; OVERDUE/INCIDENT_ABORTED already listed by M7 |
| Private parking | scheduled_start_time, scheduled_end_time, hold_expires_at, actual arrived_at/ended_at, vehicle_id, parking purpose, linked charging ID | Add end/arrival/purpose/link fields. Use PARKING_ONLY plus purpose PRIVATE_STAY or RENTAL_RETURN; private charging bundle uses existing PRIVATE_EV_PARKING_CHARGING |
| ResourceClaim | resource ID, owner kind and ID, interval, status/version; exactly one reservation or dispatch-task owner | New proposed Core concept; no fake user for dispatch; ownership mapping requires M1/M4/M7 agreement |
| Current occupancy | space, vehicle, arrival, optional actual departure; unique current occupant per space and per vehicle | Distinct from future claim/status; existing Vehicle location fields must agree atomically |
| Command result | actor/operation/key unique, canonical payload hash, result, entity IDs, commit time | New persistence obligation for retries, including loss of response after commit |
| Atomic boundary | Core coordinator invokes registered module policy/persistence ports within one unit of work | Infrastructure belongs to M1; M2 owns Reservation/Trip rules; no cross-module repository access |
| Events | event ID, entity/version, previous/next state, source/actor, UTC time, correlation and simulation context | Durable event record in transaction; publish after commit with deduplication/retry to M3/M4/M5/M7; a notification cannot control correctness |

M1 must provide snapshot queries, atomic admission/release/pickup/return/bay-bundle operations, expiry/incident serialization, lookup by command key, Core-mediated M4 alternatives, and isolated simulation contexts. If Core v1 exposes only separate “update vehicle” calls, this design is **not implementable safely as-is**: agree a unit-of-work contract before coding, rather than patching with sequential commits.

## 8. ID inventory, proposed mapping and handoff

Inventory from all fetched dependency documents: M3 uses UC-06/06.1/06.2/06.3, UC-07/07.1/07.2, UC-11/11.1/11.2/11.3 and BR-08/09/10; M4 UC-A01..A09 and BR-A01..A12; M5 UC-08/09, BR-08-01/02 and BR-09-01/02/03; M6 UC-12 and BR-SIM-01..03; M7 UC-OP-01..10; M8 still has UC-xx/BR-xx/TC-xxx placeholders. CONTRIBUTING examples UC-05/BR-02/TC-041 are explicitly illustrative, not allocations.

Use UC-M2-01..08 and BR-M2-01..16 as **temporary, module-scoped labels**, intentionally not a claim of compliance with finalized team numbering. Proposed mapping for M8 review: UC-M2-01..08 -> UC-20..27, in order; BR-M2-01..16 -> BR-20..35, in order. Those numeric ranges were unused in fetched sources but are not reserved globally. M8 confirms availability, then updates all citations together. Verification labels V-M2 below are local design scenarios, **not TC IDs**.

Operator overlap mapping for later consolidation: UC-OP-01/07 refine M5 UC-08; UC-OP-02/08 refine M5 UC-09; UC-OP-03/04 expose M3 UC-11 and M4 UC-A06/A07; UC-OP-05/06 expose M4 UC-A01..A04/A08; UC-OP-09/10 split M6 UC-12 into execution and review/application. These are UI views of existing capabilities, not ten new M2 functions. Internal schedulers remain internal; keep Operator or external event source only where it crosses the system boundary.

## 9. Traceability and planned verification

Diagram keys: A1 rental search/confirmation, A2 cancel/expiry, A3 parking; S1 reserve, S2 pickup, S3 return; R1 rental state, R2 parking state; U1/U2 scoped use-case diagrams. See [activity](../design/behavioral/reservation-activity-diagram.md), [sequence](../design/behavioral/reservation-sequence-diagram.md), [states](../design/behavioral/reservation-state-machine.md).

| Scenario | FR -> UC | BR-M2 | Diagram | Given / when / expected outcome; technique |
|---|---|---|---|---|
| V-M2-01 | FR-02 -> UC-M2-01 | 01,02,13 | U1,A1 | Eligible/low/private/charging candidates; filter returns only eligible fleet with battery/as_of. Invalid Hub/type/-1 or 101% fails, empty set gives advisory alternatives; equivalence partitions. |
| V-M2-02 | FR-03/04 -> UC-M2-02/04/05 | 02,04,08,09,10 | A1,S1,S2,S3,R1 | Available parked fleet; reserve, pickup before deadline, return to free Hub; one Trip, correct two-Hub occupancy, vehicle Returned; use-case walkthrough. |
| V-M2-03 | FR-03/05 -> UC-M2-02/06 | 03,06,08,13 | A1,A3,S1 | 20-50 same-resource contenders; one success. Same student booking different resources: quota still holds. Rental vs dispatch: committed claim protected; concurrency and decision table. |
| V-M2-04 | FR-03 -> UC-M2-03/04 | 04,05,06,09 | A2,S2,R1 | Pickup/cancel/expiry at expiry-1 ms, expiry, expiry+1 ms; only before expiry eligible; one winner, no double release; boundary/state transitions. |
| V-M2-05 | FR-03/04 -> UC-M2-02/04/05 | 07,08,10 | S1,S2,S3,R1 | Lose response after commit, retry same key; same IDs/time. Same key changed payload rejects; new-key pickup/return cannot duplicate or relocate completed trip; fault injection. |
| V-M2-06 | FR-04/05 -> UC-M2-05/06 | 08,10,11,13 | A3,S3,R2 | Hub full or last space taken concurrently; no return mutation, alternatives create no hold; valid own hold consumable although unclaimed count is zero; capacity boundary. |
| V-M2-07 | FR-03/04 -> UC-M2-04/05 | 02,14 | S2,R1 | Fault before pickup cancels claim but preserves origin occupancy; fault in trip leaves Active until verified return/recovery; state/failure. |
| V-M2-08 | FR-05/07 -> UC-M2-06/08 | 04,11,12 | U2,A3,R2 | Private start at now/+24 h valid, outside invalid; duration 29/30/240/241; arrival at start valid and deadline invalid; [a,b) and [b,c) do not overlap; boundary. |
| V-M2-09 | FR-05/07 -> UC-M2-06/07/08 | 05,08,11,12 | A3,R2 | Joint bay+charger, inject failure after either write: neither confirms; charging completion/cancellation leaves occupied parking; one car counts once; integration/fault injection. |
| V-M2-10 | FR-04/05/07 -> UC-M2-05/08 | 10,11,14,15 | S3,R1,R2 | Return at due+60 min not overdue; +1 ms overdue. Private parking at end stays occupied; following arrival reassigns or fails explicitly, never exceeds capacity; boundary. |
| V-M2-11 | FR-02/03/04 -> UC-M2-01/02/04 | 02,13 | A1,S1,S2 | SOC 10/15/19.99/20: distinct incident/lockout/eligibility results; charging urgency excludes equality 15, metric excludes equality 20; decision table. |
| V-M2-12 | FR-02..05/07 -> UC-M2-01..08 | 16 | All; Core contract | Replay ordered commands on isolated snapshot and clock; same seed/order same result, operational state hash unchanged; apply recommendation requires fresh operational authorization; integration/isolation. |
| V-M2-13 | FR-03/04/05/07 -> UC-M2-02..08 | 01,06,07,08 | S1,S2,S3,R1,R2 | Foreign ID, wrong Hub/type/state, stale version; reject with no unauthorized state disclosure or mutation. Inject failure at every multi-entity step: full rollback; authorization/state/fault injection. |

These scenarios are ready for M8's official TC assignment. None is an executed application test. Design-review evidence and render commands are in the behavioral report.
