## 3.4 User-interface Design

> Draft · Owner: M7 · Date: 2026-11-09
> Full wireframes: `docs/design/ui/wireframes-student.md` and `wireframes-operator.md`. Flows: `ui-flow-diagrams.md`. Checks against the data: `ui-consistency-review.md`. "Planned" means the screen follows a requirement for which there is no code yet. Figure numbers are provisional.

### 3.4.1 Approach and principles

The interface is a set of server-rendered web pages (Jinja2, with HTMX to refresh parts of a page by polling) served by the `ui` module in the same application as the API (D-002). A page may call `core` directly and keeps the login token in a cookie. There are two interfaces: nine screens for the student (S1 to S9) and six for the operator (O1 to O6). The role of the logged-in account (A-06) decides which one is shown. The wireframes show content, actions and feedback, not colours or spacing.

Principles:

1. **The interface shows state and sends actions; it holds no business rule.** The backend decides, and a refused action is explained.
2. **Critical status is visible without navigation (NFR-20).** The operator's alert strip is on every screen.
3. **Every refusal explains itself (NFR-21).** It gives the cause, an alternative when there is one, and the error code under "Details". No stack trace is shown.
4. **Data shows its age.** Screens show the time of the data (`as_of`).
5. **A slow answer is not reported as a failure.** For rental commands the screen reads the booking again before saying "failed", and a retry uses the same reservation ID.

### 3.4.2 Major user flows and navigation

**Student.** After login the student lands on the Hub list (S2). My bookings and Logout are in the header of every screen. The main path is Find a Hub, Search, Confirm, My bookings. After a return, the student can request charging for that vehicle. A parking booking with the charging box ticked continues in the charging screen, because the two are booked together (`BR-M2-12`).

```mermaid
flowchart TD
    S1([S1 Login]) --> S2([S2 Find a Hub])
    S2 --> S3([S3 Search vehicles])
    S2 --> S5([S5 My bookings])
    S2 --> S6([S6 Parking])
    S2 --> S7([S7 My private EV])
    S2 --> S8([S8 Charging])
    S3 --> S4([S4 Confirm rental])
    S4 -->|reserved| S5
    S4 -->|refused| S3
    S5 -->|after a return| S8
    S6 -->|also charge| S8

    classDef planned stroke-dasharray: 5 4
    class S6,S7,S8 planned
```

*Figure 3.8 — Student flows. A dashed box is Planned.*

**Operator.** After login the operator lands on the overview (O1). A tab bar and the alert strip are on every screen, so each tab screen is one click from the others, and a Hub in `WARNING` or `CRITICAL` is always one click away. The Hub detail (O2) opens from a Hub card. The What-if screen changes nothing: a recommendation goes to the owning module only after the operator approves it, and that module may refuse it.

```mermaid
flowchart TD
    S1([S1 Login]) --> O1([O1 Overview])
    O1 --> O2([O2 Hub detail])
    O1 --> O3([O3 Charging])
    O1 --> O4([O4 Dispatch])
    O1 --> O5([O5 Incidents])
    O1 --> O6([O6 Simulation Lab])
    O2 --> O4
    O2 --> O6
    O5 -.->|manual override only| O2
    O6 -->|open| O3
    O6 -->|open| O4

    classDef planned stroke-dasharray: 5 4
    class O3,O6 planned
```

*Figure 3.9 — Operator flows. A dashed box is Planned.*

### 3.4.3 Information shown to each actor

| Student screen | Information |
|---|---|
| S2 Find a Hub | For each Hub: vehicles available, free spaces, charging points in use, status in words, time of the data |
| S3 Search | Vehicles of the Hub (code, type, battery); free spaces at the return Hub, marked "not a reservation" |
| S4 Confirm | Vehicle, pick-up Hub, return Hub (space not held), planned minutes, the 10-minute deadline |
| S5 My bookings | Booking state, pick-up deadline, expected return time, overdue notice, return receipt |
| S6 Parking (Planned) | Assigned space, arrival window, planned end |
| S7 My vehicle | Registered private EVs and their state |
| S8 Charging (Planned) | The student's charging requests and their status |

| Operator screen | Information |
|---|---|
| O1 Overview | Per Hub: status, parking use, vehicles available, charging in use; alert strip |
| O2 Hub detail | Vehicles, spaces and charging points with state, battery and fault; state history of a vehicle |
| O3 Charging (Planned) | Charging queue with battery, target, priority, status, point |
| O4 Dispatch | Tasks with route, vehicles, status, priority, reason; allocation settings |
| O5 Incidents | Tickets with type, severity, status, age, history |
| O6 Simulation (Planned) | Scenario inputs, baseline against mitigated results, recommendations |

```
+--------------------------------------------------------------------------+
| Smart E-Mobility Hub        {user_id}           My bookings | Logout     |
+--------------------------------------------------------------------------+
| From Hub: choose a row below                                             |
|                                                                          |
| Hub                 Zone   Vehicles  Free spaces   Charging in use Status|
| H01 Metro           METRO   {36}     {20} of 70    {3} of 10       Open  |
| H02 Dorm A          DORM    {7}      {2} of 60     {9} of 10  Nearly full|
| H03 Dorm B          DORM    {0}      {0} of 50     {8} of 8        Full  |
|                                         [ Find a vehicle at this Hub ]   |
+--------------------------------------------------------------------------+
| as of {10:42:05} · Refresh                                               |
+--------------------------------------------------------------------------+
```

*Figure 3.10 — S2, the Hub list.*

```
+--------------------------------------------------------------------------+
| < Hubs     Vehicles at H01 Metro                                         |
+--------------------------------------------------------------------------+
| Type [ v any ]   Minimum battery [ 20 ] %    Return to [ v any Hub ]     |
|                                                       [ Search ]         |
|                                                                          |
|    Vehicle       Type            Battery                                 |
| ( ) {EB-0123}    E-bike           {96}%                                  |
| (•) {ES-0045}    E-scooter        {81}%                                  |
| ( ) {EM-0007}    E-motorcycle     {63}%                                  |
|                                                                          |
| Return Hub H05 Campus A: {4} free spaces now. Not a reservation.         |
|                                          [ Reserve selected vehicle ]    |
+--------------------------------------------------------------------------+
| Hub data as of {10:42:05} · results can change before you confirm        |
+--------------------------------------------------------------------------+
```

*Figure 3.11 — S3, vehicle search.*

```
+--------------------------------------------------------------------------+
| RENTAL {reservation_id}   Reserved                                       |
|  Vehicle {ES-0045}        Pick up at {H01 Metro}                         |
|  Pick up before {10:52:05}   (time left {07:42})                         |
|        [ I picked up the vehicle ]          [ Cancel reservation ]       |
+--------------------------------------------------------------------------+
```

*Figure 3.12 — S5, a reserved rental.*

```
+--------------------------------------------------------------------------+
| Smart E-Mobility Hub: Operator   {user_id}                     Logout    |
| [Overview] [Charging] [Dispatch] [Incidents] [Simulation Lab]            |
| Alerts: ■ H03 CRITICAL · ▲ H02 WARNING · Incidents: not available        |
+--------------------------------------------------------------------------+
| Zone [ v all ]  Status [ v all ]                                         |
|                                                                          |
| +----------------+ +----------------+ +----------------+                 |
| | H03 Dorm B  ■  | | H02 Dorm A  ▲  | | H01 Metro   ●  |   ...           |
| | CRITICAL       | | WARNING        | | ACTIVE         |                 |
| | Parking 50/50  | | Parking {55}/60| | Parking {40}/70|                 |
| | [██████████]   | | [█████████░]   | | [██████░░░░]   |                 |
| | Vehicles {0}   | | Vehicles {7}   | | Vehicles {36}  |                 |
| | Charging {8}/8 | | Charging {9}/10| | Charging {3}/10|                 |
| +----------------+ +----------------+ +----------------+                 |
| (cards ordered by severity, then by occupancy)                           |
+--------------------------------------------------------------------------+
| Data as of {10:42:05}                                         [Refresh]  |
+--------------------------------------------------------------------------+
```

*Figure 3.13 — O1, network overview with the alert strip.*

```
+--------------------------------------------------------------------------+
| Dispatch                                      [ Update recommendations ] |
+--------------------------------------------------------------------------+
| ⚠ Recommendations are from {10:30} (older than {15} min).                |
|                                                                          |
| Tasks             Status [ v all ]                                       |
|  {T-014}  H01 -> H02   E-scooter  quantity {3}   priority {1}            |
|           RECOMMENDED   reason: {Hub H02 expects 6 pickups, has 2}       |
|           Vehicles: {EB-0123, ES-0031, EM-0007}                          |
|           Quantity [ - ] {3} [ + ]   [ Approve ]   [ Reject ]            |
|                                                                          |
|  {T-012}  H05 -> H01   E-bike     quantity {2}   IN_PROGRESS             |
|           [ Confirm pick-up ]  [ Confirm delivery ]  [ Cancel ]          |
|  {T-009}  H02 -> H04   FAILED   reason: {destination below buffer}       |
|                                                                          |
| [ Allocation settings v ]                                                |
+--------------------------------------------------------------------------+
```

*Figure 3.14 — O4, dispatch tasks.*

```
+--------------------------------------------------------------------------+
| Incidents Severity [ v all ] Status [ v active ] Hub [ v all ] Type [ v ]|
+--------------------------------------------------------------------------+
|  Type                          Hub  Severity  Status       Age           |
|  INC-HW-01 Charger fault       H02  Critical  OPEN         {2} min       |
|  INC-CAP-01 Hub full           H03  High      ESCALATED    {12} min      |
|  INC-USR-01 Rental overdue     H05  Low       IN_PROGRESS  {35} min      |
+--------------------------------------------------------------------------+
| INC-CAP-01 Hub reached 100% parking capacity: H03     High  ESCALATED    |
|  (not acknowledged for more than 5 minutes)                              |
|  Component {Hub H03} · error code {-} · reported by {SYSTEM_IOT_INTAKE}  |
|  History  {10:30} created · {10:35} escalated by the system              |
|  Notes  [__________________________________________________________]     |
|  [ Acknowledge ]                          [ Resolve ]   [ Close ]        |
+--------------------------------------------------------------------------+
```

*Figure 3.15 — O5, incident tickets with the selected ticket.*

```
+--------------------------------------------------------------------------+
| Simulation Lab  ┌ SIMULATION: a copy of the state, nothing real changes ┐|
+--------------------------------------------------------------------------+
| Scenario [ v Peak-hour demand surge ]                                    |
|  Target Hubs     [ H01 x ] [ H02 x ]                                     |
|  Surge multiplier [ 1.5 ]      Duration [ 60 ] min                       |
|  Time horizon     [ 120 ] min   Random seed [ 42 ]       [ Run ]         |
|  ⚠ (on error) The multiplier must be between 1.0 and 5.0.                |
+--------------------------------------------------------------------------+
| Result   snapshot {SNAP-001} taken {10:42:05}   status {SUCCESS}         |
|                              Baseline    With recommendations            |
|  Vehicle shortage rate       {28}%          {9}%                         |
|  Hub overflow / rejected returns {12}%      {3}%                         |
|  Avg charging queue wait     {22} min       {12} min                     |
|  Critical battery count      {6}            {2}                          |
|                                                                          |
| Recommendations                                                          |
|  1. Move {3} vehicles H01 -> H02       feasible   Pending  -> allocation |
|        reason: {shortage rate above threshold}   [ Approve ] [ Reject ]  |
|  Assumptions and limits: {...}                                           |
|  [ Export report ]                           [ Discard and reset ]       |
+--------------------------------------------------------------------------+
```

*Figure 3.16 — O6, What-if Simulation Lab with baseline and mitigated results.*

### 3.4.4 User actions and system feedback

| Student action | On success | When refused |
|---|---|---|
| Reserve a vehicle (S4) | Booking "Reserved" with its deadline and "Return space not reserved" | "Someone else just reserved this vehicle", "This vehicle can no longer be rented", or "You already have a rental" |
| Pick up (S5) | "In progress" with the expected return time | "The time to pick up has passed. Make a new reservation" |
| Return (S5) | A receipt with Hub, space and time | "No space is free at this Hub", with nearby Hubs; nothing changes |
| Cancel, hold a return space (S5, Planned) | "Cancelled"; a 10-minute hold | "The trip has started. Return the vehicle instead" |
| Parking (S6, Planned) | Space, arrival window, planned end | "The Hub is full and takes no new parking bookings" |
| Register a private EV (S7) | Vehicle listed as "Away" | "This plate is already registered" |
| Charging (S8, Planned) | "Waiting", "Scheduled" or "Charging" | "No charging point is free then", with another time, port or Hub |

| Operator action | On success | When refused |
|---|---|---|
| Change a vehicle, point or Hub state (O2) | New state and a new line in the history | "Cannot be changed directly now. Handle its reservation or trip first", or "Changed by someone else. Refreshed" |
| Plan, approve, pick-up, delivery, cancel (O4) | The task with its new status | The task keeps its reason when it fails, or the request is refused with the cause |
| Acknowledge, resolve, close (O5) | Ticket "In progress", "Resolved" or "Closed" | The action is hidden when the status does not allow it |
| Run a simulation, approve a recommendation (O6) | The report; the recommendation sent to its module | A field message for invalid inputs; the receiving module may refuse |

Every refusal uses the same block: what failed, the cause, up to two alternatives, and the code under "Details".

### 3.4.5 Design decisions for usability and clarity

| Screen | Decision | Reason |
|---|---|---|
| S2 | One table with vehicles, free spaces and charging | The student compares Hubs without opening each one |
| S3 | Note "Not a reservation" under the return Hub | The student does not think a space is held |
| S4 | The 10-minute deadline, planned time and missing return space shown before confirming | These are the facts that surprise students most |
| S5 | Only the actions allowed in the booking's state; deadline as a time and a countdown | The student cannot try a pick-up on an expired booking |
| O1 | One card per Hub, ordered by severity; symbol and word, not colour alone | Hubs that need attention are seen at once, and the screen is readable without colour |
| O2 | State history under the vehicle; only the button that fits the state | The operator sees how the vehicle got there before overriding |
| O4 | "Update recommendations" is a button; a failed task keeps its reason | Planning writes data, so it must be deliberate; no need to ask why a task failed |
| O5 | Active tickets first, most severe and oldest on top; only the actions the status allows; history under the ticket | The operator handles the worst ticket first and cannot close a ticket before it is resolved |
| O6 | Banner that the screen works on a copy; baseline next to the mitigated result; seed shown | Simulated results are not mistaken for real state, and the same seed gives the same result (NFR-13) |
| All | Loading, empty and error states | The user can tell "nothing here" from "something failed" |

### 3.4.6 Interfaces for ordinary users and operators

| Capability | FR | Screens |
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

A private EV owner is a student with a registered vehicle and uses the student interface. `iot_sim` has no screen.

### 3.4.7 Non-functional requirements

| NFR | How the interface meets it |
|---|---|
| NFR-01 | Parts of a page are re-read by polling every 3 seconds |
| NFR-12, NFR-13 | O6 works on a copy and shows the random seed |
| NFR-16 | The role comes from the login; the API refuses a student on operator routes |
| NFR-20 | Alert strip on every operator screen; O1 ordered by severity |
| NFR-21 | One refusal block with cause, alternative and code |

The review of NFR-20 and NFR-21 on the running interface is planned for Phases 3 and 4.

### 3.4.8 Consistency with the data design and status

Every field on a screen was traced to a `core` query, a table in Section 3.2.2, a function of the reservation, allocation or monitoring module, or a requirement of the charging or simulation module. Three points matter:

- Some `core` queries have no REST route (the next claim on a resource, one vehicle by ID, the configured limits). A page calls them directly, so they do not block the interface.
- The architecture document says both that `ui` talks HTTP and that it may call `core` directly. How a page reaches the other modules' services is still to be decided.
- The charging module's code has no session status and its documents list different states, so the status words of the charging screens are provisional.

| Backend | Status |
|---|---|
| `core`: login, Hubs, vehicles, spaces, charging points, history | Implemented |
| Reservation (M2): reserve, pick up, return | Implemented as a service, no route yet |
| Reservation (M2): cancel, parking, return-space hold | Planned |
| Charging (M3) | Queue in memory only, no route; screens planned |
| Allocation (M4): plan, approve, pick-up, delivery, cancel, settings | Implemented; reject planned |
| Monitoring (M5): incidents and metrics | Implemented; remote reset and stale data planned |
| Simulation (M6) | Demand surge implemented, no route; the rest planned |

This section will be revised in Phase 3 to match the implementation.
