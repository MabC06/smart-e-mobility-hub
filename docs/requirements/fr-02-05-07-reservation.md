# M2 - Reservation & Trip: requirements and design baseline

> Owner: M2 - 2452620 Đặng Tuấn Kiệt. Created: 2026-10-11; updated: 2026-11-04 (ICT).
> Status: **Proposed for team review**. M2 policies and interaction designs remain Proposed. Do not code against the design until the Core API spec, class diagram and Vehicle state machine are on develop.

## 1. Scope

M2 owns FR-02, FR-03, FR-04, FR-05 and the parking part of FR-07. Trips are Hub-to-Hub. Payment, penalties, GPS, route planning, physical unlocking and hardware control are excluded. Student actions and simulated events represent pickup/return/occupancy. M3 owns charging and private-vehicle charging-profile registration; M2 consumes registered ownership data. M1 owns authentication and resource state; M7 owns UI and schema integration. M2 does not write another module's tables directly.

## 2. Shared constraints

Authorization and validation follow NFR-16 and NFR-18. Resource exclusivity follows BR-M1-01 and NFR-06; capacity follows BR-M1-02 and NFR-07; valid resource transitions follow BR-M1-03 and NFR-08. Multi-entity changes follow NFR-09. Confirmed/Active claims are protected by BR-M4-02. Simulation isolation follows NFR-12. The [NFR list](nfr.md) is Final; [Core rules](fr-01-core.md) own shared resource invariants.

M3 owns charging failure recovery and M4 supplies cross-Hub alternatives. M4 class priority and M3 within-class charging priority follow D-012. Charging uses one same-Hub parking bay per vehicle. Dispatch claim ownership and shared interface shapes require agreement with Core; student rental operations do not authorize dispatch or create dispatch Trips.

## 3. Canonical parameter register

**This table is the single source of M2 parameter values. M2 policy choices are Proposed for team review; shared constraints follow their owner documents.** Names below are design names, not existing environment variables or API fields. Changing a value requires revising its BR, diagram guards and report references together.

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
| RENTAL_POOL_LOCKOUT | 15 | percent | M5 BR-M5-05 | Safety exclusion | soc <=15 is blocked independently of search filter | M1/M2/M5 | Proposed; M5 |
| CHARGING_URGENT_SOC | 15 | percent | M3 BR-M3-03 current draft | Queue urgency, not rental eligibility | soc <=15; at 15 urgency applies; only next unclaimed bay | M3/M4 | Proposed; M3/M4 |
| SIMULATION_LOW_SOC | 20 | percent | M6 depletion metric | Analytics only | soc <20; at 20 not depleted for this metric | M6 | Proposed; M6 |
| UPCOMING_WINDOW | 30 | minutes | 0 <= scheduled_start_time-t <=30 min, plus all unexpired immediate rental holds | Common view for M3/M4 | Expired claims excluded; all Confirmed/Active claims protected even outside window | M1/M2/M3/M4 | Proposed; M1/M3/M4 |
| STUDENT_LIMITS | 1 rental and 1 parking | live reservation per category | Count Confirmed + Active, including future parking | Prevent hoarding; parking+charging bundle counts once | Check per-user counters atomically across different resources; terminal records excluded | M1/M2/M7 | Proposed; M1/M2 |
| DESTINATION_AUTO_HOLD | No | boolean | Rental booking does not reserve return capacity | Destination and arrival can change | Show “return space not reserved”; optional separate FR-05 hold below | M2/M4/M7 | Proposed; M2/M4 |
| RENTAL_RETURN_PARKING_HOLD | 10 | minutes | Active trip may reserve an empty destination space now | Useful FR-05 support without predicting rental dwell | No advance start; arrival before expiry; on successful return booking Completed, physical occupancy remains until vehicle leaves | M1/M2/M4/M7 | Proposed; M1/M2/M4 |
| TIME_BASIS | UTC storage; Asia/Ho_Chi_Minh display | zone | Follow proposed D-005; injectable authoritative clock | Reproducible events/simulations | Time read inside serialized command, not from client clock; compare instants at stored precision | M1-M8 | Proposed D-005; M1 |

Interval overlap is `a.start < b.end AND b.start < a.end`; equal endpoints do not overlap. There is no early-arrival buffer. A return-parking hold blocks its space from confirmation until arrival/expiry; after return, real occupancy has no assumed end. Therefore, confirm a rental return-space hold only on a space with no other future commitment, and do not place a future booking behind that live return hold. If it expires unused, the space can be offered again; if consumed, verified departure is required. An occupied space with no verified departure is not offered for a new future booking. Multiple non-overlapping private-stay claims on an empty space may be planned, but admission always checks actual occupancy; an overstay triggers reassignment or explicit failure, never overcapacity. This is a capacity plan, not a guarantee against incidents or overstays.

Processing timeouts are separate from all business deadlines. Propose a 5-second UI wait before displaying “outcome unknown; checking status”, not “booking failed”. Retrying uses the same request. No timeout frees a hold or completes a trip. The committed Reservation / Trip state, not receipt of the HTTP response, determines success. This operational proposal requires M1/M7 review and does not replace NFR-03's 1-second p95 target.

## 4. Functional requirements and acceptance criteria

All operations require an authenticated active Student account (NFR-16); derive user identity from the trusted session. Unknown/foreign reservation IDs yield NOT_FOUND_OR_NOT_OWNED without revealing another student's data. IDs below keep README numbering; FR-07 here is explicitly only its parking slice.

| FR | Input and required behavior/output | Acceptance criteria (design obligations, not executed tests) |
|---|---|---|
| FR-02 | Origin Hub, optional destination Hub, supported vehicle type and minimum battery. Return fleet candidates with ID/type, Hub, battery, availability, version and as_of time; show destination free-capacity snapshot, never a guarantee. Filter by Core eligibility and BR-M2-02; sort battery descending then vehicle ID. | Invalid Hub/type or minimum outside 0..100 gives field error and no mutation. Empty results give NO_VEHICLE and advisory alternatives. Private, reserved, charging, faulty or low-battery vehicles are excluded. Stale search result may lose at confirmation. |
| FR-03 | Chosen vehicle/origin, optional destination, planned duration, requested minimum, observed version. Confirm a ten-minute hold or return a reason. Owner may cancel before pickup. | Exactly one concurrent contender acquires a vehicle; user limit checked even for different vehicles. Successful response includes reservation ID, Confirmed, expiry and server time. Cancel/expiry releases the vehicle claim, never its occupied origin space. Duplicate commands do not create another reservation. |
| FR-04 | Reservation ID and pickup Hub for pickup; trip ID, destination Hub and optional parking booking ID for return; resource versions. Create one Trip at pickup and record actual return. | Wrong owner, expiry, changed vehicle eligibility or wrong Hub prevents pickup. Pickup atomically makes reservation Active, Trip IN_PROGRESS, vehicle IN_USE and frees origin occupancy. Return atomically occupies an admissible destination space, completes trip/booking and records vehicle RETURNED or MAINTENANCE; full Hub leaves trip Active and offers advisory alternatives. |
| FR-05 | Hub plus arrival interval/private vehicle, or an owned Active trip for immediate return-space hold. Return parking reservation ID, assigned space, arrival deadline and planned end when applicable. Support cancellation, arrival and departure. | No two overlapping claims for one space and no two actual occupants. At expiry no admission. Cancel releases only the claim. Private departure releases actual occupancy after confirmation through Core. Rental return consumes its hold once but does not free the returned vehicle's space. |
| FR-07 (parking) | An owned registered PRIVATE vehicle, Hub/start/duration, optional M3 charging request correlation. Confirm private parking or return validation/conflict reason. | Another owner's/unregistered vehicle is rejected; private vehicles never appear in FR-02 fleet results. Charging bundle confirms the bay and charger jointly, counting one parking space, or neither. Charging cancellation alone leaves active parking intact. No rental Trip is created for private parking. |

## 5. Business rules (stable M2 IDs)

| ID | Rule | Trace |
|---|---|---|
| BR-M2-02 | Search/confirmation eligibility requires FLEET, Core Available, current origin occupancy, no incident/dispatch/charging/other claim, known battery meeting RENTAL_MIN_SOC and requested minimum, and no M5 lockout. At pickup require Core Reserved with this booking's own claim instead of Available; recheck all other eligibility conditions. | FR-02, FR-03, FR-04, NFR-07 |
| BR-M2-03 | Enforce STUDENT_LIMITS for all live bookings. Joint parking/charging counts once; dispatch claims do not consume student quota. | FR-03, FR-05, FR-07, NFR-06 |
| BR-M2-04 | Use canonical hold/arrival windows (§3). Rental is immediate only. At t >= hold_expires_at a Confirmed reservation is unusable. Process expiry as a distinct valid transition; Active never expires from a pickup deadline. | FR-03, FR-05, FR-07, NFR-08 |
| BR-M2-05 | Owner cancellation is allowed only in Confirmed and before expiry. Cancel/expire removes unconsumed claims, not occupied spaces. Core re-evaluates readiness before making a formerly reserved vehicle Available. | FR-03, FR-05, FR-07, NFR-08, NFR-09 |
| BR-M2-09 | Pickup requires owner, Confirmed, correct origin and t < expiry, plus current eligibility with this reservation's own claim permitted. It creates one IN_PROGRESS Trip with expected_return_at from actual pickup and releases precisely the occupied origin space. Repeating the same request returns the result already recorded, without a second Trip or reservation. | FR-04, NFR-08, NFR-09 |
| BR-M2-10 | Return requires owned Active rental and open Trip, a valid receiving Hub, and an available space or the student's valid matching hold. Full/failed destination leaves trip, vehicle location and reservation unchanged. Consume only a matching hold; an unrelated destination hold remains until explicit cancellation/expiry, with a UI reminder. Return completion is not vehicle rental readiness. Repeating the same request returns the result already recorded, without a second Trip or reservation. | FR-04, FR-05, BR-M1-02, NFR-07, NFR-09 |
| BR-M2-11 | Parking uses interval exclusion plus actual occupancy checks (§3). On private arrival consume claim into one occupancy; on departure close booking and release that occupancy. End time/charging completion alone never frees parking. Rental return parking completes upon successful rental return while the space remains occupied by the fleet vehicle. | FR-05, FR-07, NFR-06, NFR-07 |
| BR-M2-12 | A charging bundle reserves one same-Hub bay and charger for compatible intervals in one Core transaction. Charger interval must lie within parking interval. Reuse the vehicle's matching occupancy/claim instead of adding a second space. No connector-only allocation without parking. Cancel before arrival can cancel the whole bundle through coordinated M2/M3 commands; reject parking-only cancellation while a linked charging commitment exists. | FR-05, FR-06, FR-07, NFR-07, NFR-09 |
| BR-M2-14 | Core-accepted failure before pickup cancels the booking with RESOURCE_UNAVAILABLE, releases the exclusive claim and keeps vehicle/space physically occupied and unavailable. During a trip record the incident but keep Reservation Active and Trip open until verified return or operator-confirmed custody recovery. Only then finish with Trip INCIDENT_ABORTED and Reservation Completed; no fabricated arrival/space release. | FR-03, FR-04, FR-09, NFR-08, NFR-09 |
| BR-M2-15 | At t > expected_return_at +60 min the open Trip becomes OVERDUE through M5/Core; reservation stays Active. At private parking end, mark overstay for M5 while keeping Active and occupied. No fines, auto-extension or forced completion. | FR-04, FR-05, FR-07, FR-09, NFR-08 |

Repeated pickup or return requests return the result already recorded without creating a second Trip or reservation. A Cancelled/Expired reservation cannot be revived.

For deadlines, M2 reads Core time **after acquiring the serialization boundary**. Pickup and cancel/expire race on the same reservation version. Exactly one valid transition commits. A sweep delay cannot extend eligibility. An expired-reservation maintenance transition may commit before a rejected pickup; it is separately logged, not a partial pickup. Safety-event ordering also uses Core's accepted sequence, not client event timestamps.

## 6. Use-case specifications

The system boundary is the whole Smart E-Mobility Hub. Student is the primary actor; Private EV Owner is a Student role. Operator is external for incident recovery; the simulated sensor/event source is external per D-004. UI, Core, Reservation and the internal expiry scheduler are **not** external use-case actors. Timer expiry is an internal event, not a human goal.

UC-M2 IDs follow the stable module-scoped convention (section 8). Shared preconditions: authenticated active Student, reachable Core; failures return a reason and no command side effects except separately identified expiry/incident transitions. All mutations follow BR-M1-01, NFR-06, NFR-09. UML sources/previews: [rental](use-case-diagrams/uc-m2-rental.svg) ([source](use-case-diagrams/uc-m2-rental.puml)) and [parking](use-case-diagrams/uc-m2-parking.svg) ([source](use-case-diagrams/uc-m2-parking.puml)). These scoped diagrams feed the Phase 1 overview linked in the actor analysis.

### UC-M2-01 - Find suitable rental vehicles

- **Actor / goal:** Student; find a usable fleet vehicle and inspect destination capacity.
- **Trigger:** Student submits Hub and filter choices.
- **Preconditions:** Shared preconditions; no booking required.
- **Main flow:** 1. Select origin, optional destination, type and minimum battery. 2. Validate fields. 3. Read Core snapshot and apply eligibility filter. 4. Sort and show candidates, battery, as_of and destination capacity. 5. Student selects a candidate for UC-M2-02.
- **Alternatives/exceptions:** Invalid field gives a field error; no match gives NO_VEHICLE and Core/M4 advisory Hub alternatives; Core unavailable gives retry feedback, not an empty-success list. Selecting an alternative reruns the search and makes no hold.
- **Postconditions:** No resources changed; results may change before confirmation.
- **Trace:** FR-02; NFR-16, NFR-18, BR-M2-02, BR-M4-02, NFR-12.

### UC-M2-02 - Reserve a rental vehicle

- **Actor / goal:** Student; secure immediate pickup.
- **Trigger:** Confirm selected vehicle, planned duration and optional destination.
- **Preconditions:** Shared preconditions; valid selected fleet vehicle; no live rental for the student.
- **Main flow:** 1. UI sends vehicle/origin, filters, duration and observed version. 2. Validate and check the existing M2 Reservation record. 3. At Core serialization boundary read fresh eligibility/time/quota. 4. Atomically create Confirmed reservation and claim, set Vehicle Reserved and retain origin occupancy. 5. Show ten-minute deadline, ID and explicit absence of an automatic return-space hold.
- **Alternatives/exceptions:** Stale version/concurrent booking yields CONFLICT; low battery, fault, dispatch or charging yields RESOURCE_UNAVAILABLE; quota yields LIMIT_REACHED; future rental start rejected. Failed attempt holds nothing. Exact retry returns its original result; timeout triggers status lookup using the same request.
- **Postconditions:** One exclusive vehicle hold or none; no Trip yet; no destination claim.
- **Trace:** FR-03; NFR-16, NFR-18, BR-M2-02, BR-M2-03, BR-M2-04, BR-M1-01, NFR-06, NFR-09, BR-M4-02.

### UC-M2-03 - Cancel a rental reservation

- **Actor / goal:** Student; release an unused rental hold.
- **Trigger:** Select Cancel on own reservation.
- **Preconditions:** Shared preconditions; owned Confirmed booking and t < expiry.
- **Main flow:** 1. Send ID. 2. Validate owner/time/state at Core boundary. 3. Commit Cancelled and release vehicle claim. 4. Core chooses eligible Available or unavailable state; leave origin occupancy unchanged. 5. Show cancellation receipt.
- **Alternatives/exceptions:** At expiry, process expiry instead and report EXPIRED. Concurrent pickup winner makes cancellation invalid; do not undo the Trip. Exact retry returns original result; already Cancelled returns ALREADY_CANCELLED. Active/Completed rejected.
- **Postconditions:** Cancelled hold no longer blocks resource; parked vehicle remains parked.
- **Trace:** FR-03; NFR-16, NFR-18, BR-M2-04, BR-M2-05, BR-M1-01, NFR-06, NFR-09.

### UC-M2-04 - Pick up a rental vehicle

- **Actor / goal:** Student; start the reserved trip.
- **Trigger:** Student confirms pickup at origin Hub in UI.
- **Preconditions:** Shared preconditions; own Confirmed rental, correct origin, t < expiry, vehicle still eligible except for own reservation claim.
- **Main flow:** 1. Submit booking/origin/version. 2. M2 checks its booking owner and deadline, then Core validates the resource and competing events. 3. Commit Active reservation, unique IN_PROGRESS Trip and expected_return_at; set Vehicle InUse, clear current Hub/space and free the source occupancy. 4. Return trip ID, pickup time and expected return time.
- **Alternatives/exceptions:** t = expiry is expired; wrong owner/Hub fails; current fault cancels via separate incident transition, not pickup; low battery makes vehicle ineligible and cancels with reason. Cancel/expiry winning the race prevents Trip creation. Retry returns existing Trip once.
- **Postconditions:** One open trip and no source occupancy, or no pickup effects.
- **Trace:** FR-04; NFR-16, NFR-18, BR-M2-02, BR-M2-04, BR-M1-01, NFR-06, NFR-09, BR-M2-09, BR-M2-14, BR-M2-15.

### UC-M2-05 - Return a rental vehicle

- **Actor / goal:** Student; finish trip at an accepting Hub.
- **Trigger:** Student selects destination and confirms return.
- **Preconditions:** Shared preconditions; own Active rental and IN_PROGRESS/OVERDUE Trip (including incident flag); vehicle is in student's custody.
- **Main flow:** 1. Send trip/destination, optional matching parking hold. 2. M2 checks owner/open trip; Core checks destination serviceability. 3. Select own valid held space or an unclaimed available space with no future commitment that indefinite fleet occupancy would violate. 4. Atomically occupy destination, record actual Hub/time/battery, complete Trip/reservation, consume matching parking hold and set Vehicle Returned (Maintenance if fault). 5. Show receipt; Core/M3 separately determine charging/readiness.
- **Alternatives/exceptions:** Full/blocked Hub returns NO_PARKING and advisory alternatives through Core/M4; choosing one requires a new confirmation. Expired destination hold offers a new unheld capacity check without reviving the hold. Changed resources cause CONFLICT and rollback. Fault does not invent physical recovery: normal return can still park safely if Hub accepts it; operator recovery is separately authorized under BR-M2-14. Duplicate return never moves a completed vehicle again.
- **Postconditions:** Trip ends once with one destination occupancy; or rental remains Active and current in-trip location unchanged.
- **Trace:** FR-04, FR-05; NFR-16, NFR-18, BR-M1-01, NFR-06, NFR-09, BR-M2-10, BR-M2-11, BR-M4-02, BR-M2-14, BR-M2-15, BR-M1-02.

### UC-M2-06 - Reserve parking

- **Actor / goal:** Student (private EV owner or active renter); obtain an arrival space.
- **Trigger:** Confirm Hub and parking request.
- **Preconditions:** Shared preconditions; no live parking booking; owned registered private EV, or owned Active rental Trip.
- **Main flow:** 1. For private EV choose start within 24 h and duration 30..240 min (default 120); for rental return use immediate ten-minute hold. 2. Validate vehicle association, quota and times. 3. Through Core select a usable space, check interval exclusion/occupancy and commit Confirmed booking/claim. 4. Show space, arrival window/deadline and planned end when private.
- **Alternatives/exceptions:** If the Hub is CRITICAL (100% occupancy), reject the new parking reservation with HUB_CRITICAL and suggest alternative Hubs under BR-M5-02; create no claim. Full Hub, overlapping claim, different owner, invalid duration or concurrent request rejects without claim. Charging option delegates charging validation to M3 through Core; commit linked bay+charger together or neither. Already parked same vehicle reuses its occupancy only through coordinated validation; it must not create duplicate occupancy. No early admission or automatic extension.
- **Postconditions:** One exclusive claim (one bay for a bundle), no occupancy created before actual arrival.
- **Trace:** FR-05, FR-07 parking; NFR-16, NFR-18, BR-M2-03, BR-M1-01, NFR-06, NFR-09, BR-M2-11, BR-M2-12, BR-M4-02, BR-M1-02, BR-M5-02.

### UC-M2-07 - Cancel parking

- **Actor / goal:** Student; release an unused parking commitment.
- **Trigger:** Cancel own parking reservation before arrival.
- **Preconditions:** Shared preconditions; own Confirmed parking and before arrival deadline; future booking may be cancelled immediately.
- **Main flow:** 1. Submit ID. 2. Check ownership/state/linkage. 3. If bundled, coordinate cancellation of the unstarted charging claim and parking claim through Core/M3. 4. Commit Cancelled and show receipt.
- **Alternatives/exceptions:** Parking-only cancellation with a linked charging commitment rejects LINKED_CHARGING; offer bundle cancellation. Active parking requires departure UC-M2-08, not cancellation. At deadline expiry wins. Concurrent arrival/cancel serializes; winner determines state. Retry does not release twice.
- **Postconditions:** Only unconsumed claims removed; never remove physical occupancy or an independently active charging session.
- **Trace:** FR-05, FR-07 parking; NFR-16, NFR-18, BR-M2-04, BR-M2-05, BR-M1-01, NFR-06, NFR-09, BR-M2-11, BR-M2-12.

### UC-M2-08 - Arrive at and leave private parking

- **Actor / goal:** Private EV owner (Student); use and release the booked space.
- **Trigger:** Confirm arrival, later confirm departure in UI; simulated occupancy evidence enters via Core.
- **Preconditions:** Shared preconditions; own private-parking reservation; arrival in [start, expiry), or departure from Active with matching vehicle occupancy.
- **Main flow:** 1. Arrival validates owner, time and space under serialization. 2. Consume claim into one occupancy and set booking Active. 3. If charging was linked, M3 starts only with valid bay occupancy/connection simulation. 4. On departure, coordinate stop/completion of any active charging and Core occupancy removal in one accepted departure operation. 5. Set booking Completed and actual ended_at.
- **Alternatives/exceptions:** Early arrival rejected; at deadline expires. Unexpected occupant/overstay: try free compatible replacement with atomic claim transfer (plus charger if bundled), otherwise report RESOURCE_UNAVAILABLE, cancel unconsumed claim and offer alternatives. At planned end remain Active/occupied and notify M5. Charging stop failure prevents departure commit and preserves occupancy. Repeated arrival/departure returns prior outcome. Rental destination parking uses UC-M2-05, not this private departure flow.
- **Postconditions:** On arrival one parked private EV and no rental Trip; on departure no occupancy from this stay; on failure no partial mutation.
- **Trace:** FR-05, FR-07 parking; NFR-16, NFR-18, BR-M2-04, BR-M1-01, NFR-06, NFR-09, BR-M2-11, BR-M2-12, BR-M2-14, BR-M2-15.

## 7. Proposed data and interaction obligations

M2 entity fields below are proposed policy data; Core infrastructure follows the released Core API v1.1 and D-015 through D-020. The sequence document maps these obligations to concrete Core commands.

| Item | Required information / invariant | Difference from M7 draft |
|---|---|---|
| Rental Reservation | confirmed_at, selected_min_soc, planned_duration_minutes, hold_expires_at, version; scheduled_start_time = confirmed_at | Add confirmation/filter/duration fields; duration is not the hold |
| Trip | unique reservation_id; expected_return_at, actual pickup/return, incident reference/flag; origin/destination and occupant association | Add due time and incident association; OVERDUE/INCIDENT_ABORTED already listed by M7 |
| Private parking | scheduled_start_time, scheduled_end_time, hold_expires_at, actual arrived_at/ended_at, vehicle_id, parking purpose, linked charging ID | Add end/arrival/purpose/link fields. Use PARKING_ONLY plus purpose PRIVATE_STAY or RENTAL_RETURN; private charging bundle uses existing PRIVATE_EV_PARKING_CHARGING |
| ResourceClaim | resource ID, holder_kind, holder_ref, half-open interval and status; exactly one typed holder | Released Core ResourceClaim (D-017); RESERVATION belongs to M2, DISPATCH_TASK to M4, CHARGING_SESSION to M3; no fake user for dispatch |
| Current occupancy | space, vehicle, arrival, optional actual departure; unique current occupant per space and per vehicle | Distinct from future claim/status; existing Vehicle location fields must agree atomically |
| Atomic boundary | M2 orchestrates Core commands and its registered entity writes within `core.unit_of_work()` | Infrastructure belongs to M1; M2 owns Reservation/Trip rules; no cross-module repository access |
| Events | event ID, entity/version, previous/next state, source/actor, UTC time, correlation and simulation context | Durable event record in transaction; publish after commit with deduplication/retry to M3/M4/M5/M7; a notification cannot control correctness |

Core v1.1 provides the required atomic boundary, shared-state commands and read queries. M2 registers Reservation/Trip tables through `core.register_entity` and never writes Core entities directly. Repeated requests read the owned M2 record first, then recheck under the unit-of-work lock (D-015). M2 releases its own expired claims (D-017). Provider types live in `core.providers` (D-020); M3 bundle and M4 alternatives remain integration contracts. Core snapshots omit M2 records: M6 obtains booking/trip due-time data through `ReservationDemand`.

## 8. ID inventory and handoff


UC-M2-01..08 and the retained BR-M2 IDs are stable module-scoped IDs under CONTRIBUTING section 5. No flat-number conversion is planned. FR-07 remains one M2 parking row; if it is split, use FR-07.M2.1, FR-07.M2.2, etc., distinct from M3. Verification labels V-M2 below are local design scenarios, **not TC IDs**.

Current operator-view mappings and external/internal actor boundaries are recorded in [stakeholder/actor analysis](stakeholder-actor-analysis.md). M7 UI views do not create duplicate business use cases; its UC-M7-02 resource-state override remains a separately owned capability pending M1 state guards.

## 9. Traceability and planned verification

Diagram keys: A1 rental search/confirmation, A2 cancel/expiry, A3 parking; S1 reserve, S2 pickup, S3 return; R1 rental state, R2 parking state; U1/U2 scoped use-case diagrams. See [activity](../design/behavioral/reservation-activity-diagram.md), [sequence](../design/behavioral/reservation-sequence-diagram.md), [states](../design/behavioral/reservation-state-machine.md).

| Scenario | FR -> UC | Rules / constraints | Diagram | Given / when / expected outcome; technique |
|---|---|---|---|---|
| V-M2-01 | FR-02 -> UC-M2-01 | NFR-16, NFR-18, BR-M2-02, BR-M4-02 | U1,A1 | Eligible/low/private/charging candidates; filter returns only eligible fleet with battery/as_of. Invalid Hub/type/-1 or 101% fails, empty set gives advisory alternatives; equivalence partitions. |
| V-M2-02 | FR-03/04 -> UC-M2-02/04/05 | BR-M2-02, BR-M2-04, NFR-09, BR-M2-09, BR-M2-10 | A1,S1,S2,S3,R1 | Available parked fleet; reserve, pickup before deadline, return to free Hub; one Trip, correct two-Hub occupancy, vehicle Returned; use-case walkthrough. |
| V-M2-03 | FR-03/05 -> UC-M2-02/06 | BR-M2-03, BR-M1-01, NFR-06, NFR-09, BR-M4-02 | A1,A3,S1 | 20-50 same-resource contenders; one success. Same student booking different resources: quota still holds. Rental vs dispatch: committed claim protected; concurrency and decision table. |
| V-M2-04 | FR-03 -> UC-M2-03/04 | BR-M2-04, BR-M2-05, BR-M1-01, NFR-06, BR-M2-09 | A2,S2,R1 | Pickup/cancel/expiry at expiry-1 ms, expiry, expiry+1 ms; only before expiry eligible; one winner, no double release; boundary/state transitions. |
| V-M2-05 | FR-03/04 -> UC-M2-02/04/05 | NFR-09, BR-M2-10 | S1,S2,S3,R1 | Lose response after commit, retry same request; same IDs/time. Repeated pickup/return cannot duplicate or relocate a completed trip; fault injection. |
| V-M2-06 | FR-04/05 -> UC-M2-05/06 | BR-M1-02, BR-M5-02, NFR-09, BR-M2-10, BR-M2-11, BR-M4-02 | A3,S3,R2 | CRITICAL Hub rejects new parking with HUB_CRITICAL and alternatives; Hub full or last space taken concurrently leaves no return mutation, alternatives create no hold; valid own hold consumable although unclaimed count is zero; capacity boundary. |
| V-M2-07 | FR-03/04 -> UC-M2-04/05 | BR-M2-02, BR-M2-14 | S2,R1 | Fault before pickup cancels claim but preserves origin occupancy; fault in trip leaves Active until verified return/recovery; state/failure. |
| V-M2-08 | FR-05/07 -> UC-M2-06/08 | BR-M2-04, BR-M2-11, BR-M2-12 | U2,A3,R2 | Private start at now/+24 h valid, outside invalid; duration 29/30/240/241; arrival at start valid and deadline invalid; [a,b) and [b,c) do not overlap; boundary. |
| V-M2-09 | FR-05/07 -> UC-M2-06/07/08 | BR-M2-05, NFR-09, BR-M2-11, BR-M2-12 | A3,R2 | Joint bay+charger, inject failure after either write: neither confirms; charging completion/cancellation leaves occupied parking; one car counts once; integration/fault injection. |
| V-M2-10 | FR-04/05/07 -> UC-M2-05/08 | BR-M2-10, BR-M2-11, BR-M2-14, BR-M2-15 | S3,R1,R2 | Return at due+60 min not overdue; +1 ms overdue. Private parking at end stays occupied; following arrival reassigns or fails explicitly, never exceeds capacity; boundary. |
| V-M2-11 | FR-02/03/04 -> UC-M2-01/02/04 | BR-M2-02, BR-M4-02 | A1,S1,S2 | SOC 14.99/15/15.01/19.99/20: incident and lockout apply at or below 15; rental eligibility starts at 20; charging urgency includes equality 15, metric excludes equality 20; decision table. |
| V-M2-12 | FR-02..05/07 -> UC-M2-01..08 | NFR-12 | All; Core contract | Replay ordered commands on isolated snapshot and clock; same seed/order same result, operational state hash unchanged; apply recommendation requires fresh operational authorization; integration/isolation. |
| V-M2-13 | FR-03/04/05/07 -> UC-M2-02..08 | NFR-16, NFR-18, BR-M1-01, NFR-06, NFR-09 | S1,S2,S3,R1,R2 | Foreign ID, wrong Hub/type/state, stale version; reject with no unauthorized state disclosure or mutation. Inject failure at every multi-entity step: full rollback; authorization/state/fault injection. |

These scenarios are ready for M8's official TC assignment. None is an executed application test. Design-review evidence and render commands are in the behavioral report.
