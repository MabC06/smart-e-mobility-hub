# Wireframes: Operator Dashboard

> Owner: M7 (Nguyễn Trung Kiên) · Date: 2026-11-07 · Reviewer: M5 (Đỗ Hoàng Việt)
> Report section: 3.4 (`docs/report/06-ui-design.md`). Flows: `ui-flow-diagrams.md`. Checks against the data: `ui-consistency-review.md`. Student screens: `wireframes-student.md`.
> Sources: operator use cases `UC-M7-01` to `UC-M7-10` (`use-case-operator-support.md`); M4's code (`router.py`, `service.py`, `config.py`) on `origin/feat/allocation-phase2`; M5's `fr-08-09-monitoring.md` (Final v1.1), `incident-data-model.md` and `monitoring-sequence-diagram.md` on `origin/docs/monitoring-phase1`; M6's `m6-simulation-design.md` and code on `origin/feat/m6-simulation-impl`; M3's `fr-06-07-11-charging.md` (version on `develop`); `core` (facade, `permissions.py`, `vehicle-state-machine.md`). Example names and sizes follow `reference-dataset.md`. Values in braces are placeholders.

Each screen is marked **Implemented** (the backend function exists in the code I read) or **Planned** (only in the requirements; no code yet). Wording of labels and messages is my own choice.

## 1. Rules for all screens

1. **Layout.** Every screen has a header (`user_id`, Logout), a tab bar (Overview, Charging, Dispatch, Incidents, Simulation Lab), the alert strip, and a footer with the time of the data and Refresh.
2. **Alert strip (NFR-20).** It lists the Hubs whose status is `WARNING` or `CRITICAL`, and the number of active incidents. M5 sets the Hub status (Planned). Until it does, the strip compares `occupied / parking_capacity` with `near_capacity_threshold` (default 90%) from `core.queries.get_config()` (Implemented). Until M5 provides incidents, the strip shows "Incidents: not available", never "0".
3. **Refresh (NFR-01).** A change must appear within 5 seconds. Pages re-read by polling every 3 seconds, the interval in M5's sequence diagram. That diagram polls `GET /api/v1/hubs/overview`, which does not exist in `core`; the `ui` module defines its own route.
4. **Stale data (Planned).** M5: telemetry delayed more than 30 seconds gives the Hub a "STALE DATA" icon and creates an `INC-COMM-01` ticket. The screen keeps showing the last numbers.
5. **Time.** Stored in UTC, shown in Asia/Ho_Chi_Minh (D-005).
6. **Version conflicts.** An action sends the `version` it read. `VERSION_CONFLICT` shows "Changed by someone else. Refreshed." and reloads the item.
7. **Confirm first.** Override, approve, cancel, resolve and apply-recommendation ask for confirmation.
8. **Errors (NFR-21).** A title, the cause, an alternative if there is one, and the code under "Details". No stack trace. The code comes from a `Result` (direct call) or from the REST body. M4's router returns `{"detail": {"code", "message"}}`, `core` returns `{"error": {...}}`.
9. **Role.** Only an operator reaches these screens. A student token gets `403` on the operator REST routes.
10. **How pages get data and run actions.** The `ui` module renders Jinja2 and HTMX pages and may call `core` directly (`architecture-diagram.md`, Section 11, point 2). The REST routes named below return the same data. The actions of O2 are `core.commands` calls made by a `ui` route with an `Actor` built from the logged-in operator (`Principal.actor()`); an operator may run every command (`permissions.py`). This route is Planned. The other actions use the owning module's service or router.
11. **Empty, loading and error states.** As in `wireframes-student.md`, rule 7 (M8 tests them).

## 2. Screens

### O1. Network overview (Implemented) · `UC-M7-01`, `UC-M7-07`

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

- Data: `core.queries.list_hubs()` (REST `GET /hubs`): name, `zone_code`, `status`, `occupied`, `parking_capacity`, `available_vehicles`, `charging_in_use`, `charging_points`, `as_of`.
- Severity is shown by a symbol and a word, not only by colour (`■ CRITICAL`, `▲ WARNING`, `● ACTIVE`, `✖ MAINTENANCE`). M5 also asks for an amber badge for `WARNING` and a red one for `CRITICAL`.
- A card for a `WARNING` or `CRITICAL` Hub has Dispatch (to O4) and Simulate (to O6) buttons. Open Hub goes to O2.
- Recent alerts: `core` does not store events, so past alerts must come from M5's tickets (Planned). Until then the page only lists status changes it saw in this session.
- Why: the operator sees at once which Hubs need attention (NFR-20).

### O2. Hub detail and resource control (reads Implemented, actions Planned) · `UC-M7-02`

```
+--------------------------------------------------------------------------+
| < Overview    H02 Dorm A         ▲ WARNING 92%    zone DORM              |
+--------------------------------------------------------------------------+
| [Vehicles] [Parking spaces] [Charging points]                            |
|                                                                          |
| Vehicles   Type [ v all ]  State [ v all ]  Owner [ v all ]              |
|  Code       Type      Owner    State        Battery  Fault  Space        |
|  EB-0123    E-bike    fleet    AVAILABLE    {96}%    –      {H02-S004}   |
|  ES-0045    Scooter   fleet    CHARGING     {54}%    –      {H02-S012}   |
|  EM-0007    Moto      fleet    MAINTENANCE  {63}%    ✖      {H02-S020}   |
|  59A-12345  Scooter   private  AVAILABLE    {70}%    –      {H02-S014}   |
+--------------------------------------------------------------------------+
| Selected: EM-0007        state MAINTENANCE · battery {63}% · fault ✖     |
|  Actions:  [ Repair: return to service ]                                 |
|  Last changes:  {10:20} report_fault by iot_sim · {09:58} return by user |
+--------------------------------------------------------------------------+
```

- Data: `core.queries` `get_hub`, `find_vehicles` (an operator also sees private vehicles), `list_spaces`, `list_charging_points`, `get_state_log` for the vehicle history, and `get_claims` for the next claim on a space or charging point. Filters by type, state and owner are done on the page. All except `get_claims` have REST routes.
- Actions on a vehicle: two events belong to the operator (`vehicle-state-machine.md`, T11 and T12): `report_fault` (to `MAINTENANCE`) from `AVAILABLE`, `RESERVED`, `RETURNED` or `CHARGING`, and `repair` from `MAINTENANCE`. After `repair`, `core` also applies `mark_ready` if the battery is above the threshold and there is no fault, so the vehicle becomes `AVAILABLE`; otherwise it stays `RETURNED`. The page shows the button that fits the vehicle's state. `core` decides, and a wrong event gives `INVALID_TRANSITION` "This vehicle cannot be changed directly now. Handle its reservation or trip first."
- A charging point can be set `OUT_OF_SERVICE`, `MAINTENANCE` or back to `AVAILABLE`, and a Hub `MAINTENANCE` or back to `ACTIVE`. The page does not offer `WARNING` and `CRITICAL` (M5 sets them) or the point status `CHARGING` (M3 sets it).
- Why: the history under the vehicle shows how it got there before the operator overrides it.

### O3. Charging coordination (Planned) · `UC-M7-03`, `UC-M7-04`

```
+--------------------------------------------------------------------------+
| Charging      Hub [ v H02 Dorm A ]         Owner [ v all ]               |
+--------------------------------------------------------------------------+
| Charging points {10}: in use {9} · out of service {1}                    |
|                                                                          |
| Queue                                                                    |
|  Vehicle    Owner    Battery -> target   Priority  Status     Point      |
|  EB-0123    fleet    {12}% -> {80}%      {0.91} !  Waiting    –          |
|  59A-12345  private  {40}% -> {100}%     {0.55}    Scheduled  {H02-CP03} |
|  ES-0045    fleet    {54}% -> {80}%      {0.40}    Charging   {H02-CP01} |
|  ! = low-battery override (battery at or below {15}%)                    |
|                                                                          |
| Sessions interrupted by a charging-point failure                         |
|  {session}  {H02-CP02} failed {10:18} -> moved to {H02-CP04}             |
+--------------------------------------------------------------------------+
```

- M3 has no code. Data from M3's sessions: vehicle, owner kind, battery and target, priority score (`BR-M3-03`), status, point. Counts and points come from `core`.
- The status words are provisional (M3's documents disagree, see `erd.md`, Section 5).
- `UC-M3-06` and `UC-M3-07` name the operator as an actor, but M3 does not say what the operator can change. Buttons such as Move to another slot or Recalculate are shown only if M3 offers them. Otherwise the screen is read-only.
- The last block shows the result of `UC-M3-08` (session moved to another point, or put back in the queue). The screen decides nothing there.
- Why: fleet and private vehicles compete for the same points, so one queue with an owner filter shows that.

### O4. Dispatch (Implemented, Reject Planned) · `UC-M7-05`, `UC-M7-06`

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

- Data (M4 router): `GET /tasks`: `task_id`, `source_hub_id`, `target_hub_id`, `vehicle_type`, `quantity`, `assigned_vehicles`, `status`, `priority`, `reason`. A task has no creation time. The warning about old data (`UC-M4-01`) is Planned, because the router returns no time.
- **Update recommendations:** `POST /tasks/plan` saves new tasks as `RECOMMENDED`. It writes data, so it is a button and not run on page load. If nothing is needed the screen says "No task is needed".
- **Approve:** `POST /tasks/{id}/approve`, optional `adjusted_quantity`. It works only on a `RECOMMENDED` task. A smaller number keeps the first vehicles and drops the rest; a larger number changes nothing, so the operator can only lower the quantity. If the destination would fall below the parking buffer, the task becomes `FAILED` with a reason (`HUB_FULL`). If a vehicle is no longer available or its battery is too low, the request is refused (`RESOURCE_UNAVAILABLE`, `BATTERY_TOO_LOW`) and the task stays `RECOMMENDED`. On success the vehicles and one destination space are held and the task is `APPROVED`.
- **Reject:** in `UC-M4-02` but M4's code has no endpoint for it (Planned).
- **Pick-up and delivery:** `POST /tasks/{id}/pickup` makes it `IN_PROGRESS`. `POST /tasks/{id}/return` (optional delivered battery 0 to 100) makes it `COMPLETED`. **Cancel:** `POST /tasks/{id}/cancel` with a reason releases the holds. `UC-M4-04` allows it for `APPROVED` and `IN_PROGRESS`; the screen offers it for those two.
- **Allocation settings (`UC-M4-09`):** `GET` and `PUT /config` with nine numbers: horizon, safety stock, parking buffer, minimum dispatch battery, maximum tasks per Hub, maximum vehicles per task, task timeout, staleness limit, reservation lookahead. The server checks the limits and the screen shows its message.
- Why: a failed task keeps its reason on the card, so the operator does not have to ask why.

### O5. Incident management (Planned) · `UC-M7-08`

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
|  [ Acknowledge ]                                [ Resolve and close ]    |
+--------------------------------------------------------------------------+
```

- M5 has no code. Its use cases (`fr-08-09-monitoring.md`, Final v1.1) and data model (`incident-data-model.md`) are published, and the screen follows them.
- Data (table `monitoring_incidents`): type with its code, severity, status, Hub, component (`entity_type` and `entity_id`), `error_code`, `description`, `reported_by`, `assigned_operator_id`, `resolution_notes` and the time stamps. History comes from `monitoring_incident_audit_logs`.
- Types: `INC-HW-01` charging-point fault, `INC-HW-02` parking sensor, `INC-CAP-01` Hub full, `INC-CAP-02` vehicle deficit, `INC-BAT-01` low battery, `INC-COMM-01` telemetry loss, `INC-USR-01` overdue rental.
- Lifecycle: `OPEN` to `IN_PROGRESS` to `RESOLVED` to `CLOSED`, and `OPEN` to `ESCALATED` to `IN_PROGRESS`. A `HIGH` or `CRITICAL` ticket that stays `OPEN` for 5 minutes becomes `ESCALATED` by the system, which also notifies the duty supervisor (`BR-M5-04`). The screen never sets `ESCALATED`.
- **Acknowledge:** on an `OPEN` or `ESCALATED` ticket, gives `IN_PROGRESS`. **Resolve and close:** the operator writes resolution notes (required), the system sets `RESOLVED` and then `CLOSED` (`UC-M5-02`, step 9).
- In M5's flow the system restores the resource in `core` when the device is healthy again (`UC-M5-02`, step 8). The operator does not need to restore it; the override in O2 stays available.
- A remote reset (`UC-M5-02`, step 6) is shown only if M5 provides a command for it. If it fails, the operator hands the ticket to a field technician. The ticket has no field for the technician, so this goes in the notes. The technician and the duty supervisor are outside the system and have no screen.
- Default view: active tickets, most severe first, then oldest.

### O6. What-if Simulation Lab (demand surge Implemented, rest Planned) · `UC-M7-09`, `UC-M7-10`

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
|  1. Move {3} vehicles H01 -> H02       feasible   Pending  -> M4         |
|        reason: {shortage rate above threshold}   [ Approve ] [ Reject ]  |
|  Assumptions and limits: {...}                                           |
|  [ Export report ]                           [ Discard and reset ]       |
+--------------------------------------------------------------------------+
```

- M6's code has the demand-surge scenario only and no route. The rest follows `m6-simulation-design.md`. M6 asks M7 to agree on the configuration fields, the report and the approval steps, so this screen is also M7's proposal to M6.
- Five scenarios: demand surge, Hub at capacity, charging surge, charging-point failure, vehicle imbalance. Common inputs: scenario, time horizon, time step, random seed. The form changes with the scenario. Inputs per scenario (from the design):

| Scenario | Inputs |
|---|---|
| Demand surge | target Hubs, surge multiplier (default 1.5), duration, optional destination distribution |
| Hub at capacity | target Hub, incoming return rate, occupancy warning threshold (default 0.90), neighbour Hub radius |
| Charging surge | target Hubs, state-of-charge trigger (default 0.20), initial low-battery count, charging demand multiplier (default 2.0), maximum queue depth |
| Charging-point failure | failed point IDs, failure start offset, estimated repair time (default 30 min), fallback policy (`FLEET_FIRST` or `FCFS`) |
| Vehicle imbalance | surplus Hubs, deficit Hubs, batch size, transit delay |

- The screen does not fix the allowed ranges, because M6's design and code differ (for demand surge the design says duration 15 to 240 and horizon 60 to 360; the code accepts 15 to 360 and 30 to 360). M6 checks the inputs before running. Its code raises plain `ValueError` text, so the screen writes its own message for each field.
- Result: the code returns `baseline_shortage_rate_pct` and, for each Hub, total requests, unmet requests and shortage rate, plus a list of recommendations. The design adds the mitigated run, the comparison, assumptions and errors, and four metrics (shortage rate, Hub overflow or return rejection, average charging queue wait, critical battery count). The wireframe shows the design.
- A recommendation has a type, Hubs, quantity, reason, target module, feasibility and approval status. It stays advice until the operator approves. Approve sends it to the owning module (M4, M3 or M2), which checks it against the real state and may refuse. How M6 passes a recommendation to M4 is not defined: M4's router has no endpoint that creates a task from outside. Until then the operator uses O4 or O3.
- The banner "SIMULATION: a copy of the state" is only on this screen. The seed is shown with each result (NFR-13). Export format is open; I propose a JSON file of the report.

## 3. Messages for refused actions

The codes are the same for a direct call and over REST.

| Code | Message to the operator | Alternative |
|---|---|---|
| `UNAUTHENTICATED` | Please log in again. | Login |
| `FORBIDDEN` | You are not allowed to do this. | Back |
| `NOT_FOUND` | This item no longer exists. | Reload |
| `INVALID_INPUT` | The field message | Fix the field |
| `VERSION_CONFLICT` | Changed by someone else. Refreshed. | Try again |
| `CLAIM_CONFLICT` | Another booking holds this resource then. | Choose another |
| `INVALID_TRANSITION` | This is not possible in the current state. | Handle the reservation or trip first |
| `RESOURCE_UNAVAILABLE` | A resource is no longer available. | Update recommendations |
| `HUB_FULL` | The destination Hub has no free space. | Update recommendations |
| `SPACE_NOT_FREE` | The space is taken. | Choose another |
| `BATTERY_TOO_LOW` | A vehicle's battery is below the minimum. | Update recommendations |
| `INTERNAL_ERROR` | Something went wrong. Nothing was changed. | Retry |

M4's router answers `BATTERY_TOO_LOW` and `CLAIM_CONFLICT` with HTTP 500. The code is still in the body, so the screen reads the code from the body, not the HTTP status.

## 4. Open points

1. How a page reaches the services of M3, M4, M5 and M6: `architecture-diagram.md` says `ui` "talks HTTP" (Section 4) and also "may call `core` in-process" (Section 11, point 2). To settle with M1.
2. M3: what the operator may change in the queue, and the session states.
3. M4: a reject endpoint; how a recommendation from M6 becomes a task; the router uses a fixed operator `OP01` with no token check; the HTTP 500 mapping above.
4. M5: the remote-reset command, the foreign key on `assigned_operator_id`, how stale data is reported, alert records, and the polled route in its sequence.
5. M6: routes, final input ranges, how an approved recommendation is sent, and the export format.
