# Wireframes: Student Interface

> Update of 2026-11-25 (PR 4, M1): every screen is connected; what each screen calls is in `docs/report/06-ui-design.md`, Section 3.4.8. The notes below that still say "Planned" describe the design before that date.

> Owner: M7 (Nguyễn Trung Kiên) · Date: 2026-11-09 · Revised for Phase 3: 2026-11-25 · Reviewer: M5 (Đỗ Hoàng Việt)
> Report section: 3.4 (`docs/report/06-ui-design.md`). Flows: `ui-flow-diagrams.md`. Checks against the data: `ui-consistency-review.md`.
> Sources: M2's `fr-02-05-07-reservation.md` (`UC-M2-01` to `UC-M2-08`) and the M2 code on `develop` (`src/reservation`, routes in `router.py`); M3's `fr-06-07-11-charging.md` (the version on `develop`; M3's newer branch replaces it with report text) and M3's code on `origin/feat/charging-phase2`; `core` (facade and REST routes); `architecture-diagram.md` Section 11 point 2. Example names and sizes follow `reference-dataset.md`. Values in braces are placeholders.

Each screen is marked **Implemented** (the backend function exists in the code I read) or **Planned** (only in the requirements; no code yet). Wording of labels and messages is my own choice, not a requirement of another module.

## 1. Rules for all screens

1. **Header and footer.** The header shows the student's `user_id`, My bookings and Logout. The footer shows the time of the data (`as_of`) and a Refresh link. There is no name, because `user_accounts` has no name column.
2. **Time.** Times are stored in UTC and shown in Asia/Ho_Chi_Minh (D-005). The server decides deadlines. A countdown on screen is only for information.
3. **Fleet only.** A student never sees other students' private vehicles.
4. **Slow answers (Planned).** M2 proposes that if no answer comes in 5 seconds, the screen says "Outcome unknown, checking status" and reads the booking again. A retry uses the same reservation ID. The screen creates that ID once per attempt.
5. **Refresh (NFR-01).** A change must appear within 5 seconds. Pages re-read by polling every 3 seconds, the interval used in M5's sequence diagram.
6. **How pages get data.** The `ui` module renders HTML with Jinja2 and HTMX. It may call `core` directly and keeps the login token in a cookie (`architecture-diagram.md`, Section 11, point 2). The REST routes named below return the same data. For the other modules (M3 here) a page calls their REST routes with the student's token through the internal client in `src/ui/api.py`, because `ui` may not import another module (NFR-22).
7. **Empty, loading and error states.** M8 tests these. Every list and form shows "Loading…" while loading, a message with the next step when empty, and the error block of S9 with Retry when the backend fails.

## 2. Screens

### S1. Login (Implemented)

```
+--------------------------------------------------+
|              Smart E-Mobility Hub                |
|   Code      [____________________]               |
|   Password  [____________________]               |
|             [        Log in       ]              |
|   ⚠ Code or password is not correct.             |
+--------------------------------------------------+
```

- `AuthService.login(code, password)` (REST `POST /auth/login`) returns a token, `user_id` and `role`. The token lasts 60 minutes by default. A student goes to S2, an operator to the operator overview.
- A wrong code and a wrong password give the same message.
- Accounts are seeded (A-06), so there is no sign-up.

### S2. Find a Hub (Implemented) · `FR-01`, start of `UC-M2-01`

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

- Data: `core.queries.list_hubs()` (REST `GET /hubs`): name, `zone_code`, `available_vehicles` (rental fleet only), `free_spaces` and `parking_capacity`, `charging_in_use` and `charging_points`, `status`, `as_of`.
- Status words: `ACTIVE` Open, `WARNING` Nearly full, `CRITICAL` Full, `MAINTENANCE` Closed. M5 sets `WARNING` at 90% and `CRITICAL` at 100% parking use. For a `CRITICAL` Hub the screen says "No new parking bookings" (M2 refuses them, `HUB_CRITICAL`, Planned).
- If the student already has a rental, the button is disabled with "You can hold one rental at a time" (`LIMIT_REACHED`). Reading the student's bookings is Planned.
- Why: the student compares vehicles, free spaces and charging in one table.

### S3. Search for a vehicle (Implemented) · `UC-M2-01`, `FR-02`

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

- Data: `core.queries.find_vehicles(...)` (REST `GET /hubs/{hub_id}/vehicles?state=AVAILABLE&type=&min_battery=`): `plate_or_code`, `vehicle_type`, `battery_pct`, `version`. The return Hub's free spaces come from `list_hubs`.
- Minimum battery is a number from 0 to 100. A value under 20 has no effect, because M2 requires at least 20% (`max(20, requested)`).
- Planned (M2 search): order by battery, highest first, then by vehicle ID (`FR-02`); hide vehicles that are not eligible (`BR-M2-02`); never offer a vehicle at or below 15% (`BR-M5-05`); when nothing matches, show nearby Hubs that have vehicles (`NO_VEHICLE`).
- Why: the note "Not a reservation" stops the student from thinking a return space is held.

### S4. Confirm the reservation (Implemented) · `UC-M2-02`, `FR-03`

```
+--------------------------------------------------------------------------+
| < Back       Confirm your rental                                         |
+--------------------------------------------------------------------------+
|  Vehicle       {ES-0045}  E-scooter, battery {81}%                       |
|  Pick up at    {H01 Metro}                                               |
|  Return to     {H05 Campus A}   (return space is NOT held)               |
|  Planned time  [ 30 ] minutes    (5 to 120)                              |
|                                                                          |
|  You will have 10 minutes after confirming to pick the vehicle up.       |
|                                                                          |
|          [ Confirm reservation ]            [ Cancel ]                   |
+--------------------------------------------------------------------------+
```

- "Confirm reservation" calls M2's `POST /reservations` with a reservation ID (made by the screen), vehicle, origin Hub, the vehicle `version` shown in S4, the destination Hub if one was chosen in S3, and planned minutes (5 to 120, default 30). The minimum battery is left at M2's 20%.
- Success: the booking is `CONFIRMED` and `hold_expires_at` is 10 minutes after confirmation. The screen goes to S5.
- Refusals hold nothing. The error block shows M2's cause and code and a link to choose a vehicle (S2). Planned messages (DEV-13): `CONFLICT` "Someone else just reserved this vehicle"; `RESOURCE_UNAVAILABLE` "This vehicle can no longer be rented"; `LIMIT_REACHED` "You already have a rental"; `INVALID_INPUT` shows the field message.
- Why: the 10-minute deadline, the planned time and the missing return space are shown before the student commits.

### S5. My bookings: pick up, cancel, return, hold a return space (Implemented) · `UC-M2-03` to `UC-M2-05`

```
+--------------------------------------------------------------------------+
| RENTAL {reservation_id}   Reserved                                       |
|  Vehicle {ES-0045}        Pick up at {H01 Metro}                         |
|  Pick up before {10:52:05}   (time left {07:42})                         |
|        [ I picked up the vehicle ]          [ Cancel reservation ]       |
+--------------------------------------------------------------------------+
```

```
+--------------------------------------------------------------------------+
| RENTAL {reservation_id}   In progress     Trip {trip_id}                 |
|  Picked up {10:44}      Expected back {11:14}                            |
|  Return to  [ v H05 Campus A ]                                           |
|        [ Hold a return space for 10 min ]     [ Return the vehicle ]     |
|  ⚠ (when OVERDUE) You are {20} minutes past the expected return time.    |
+--------------------------------------------------------------------------+
```

- Data: M2's `GET /reservations/mine`: the student's bookings (status, `hold_expires_at`), the open trips (`picked_up_at`, `expected_return_at`, status) and the current `version` of each vehicle. Newest booking first. A `CONFIRMED` booking is shown as Reserved and a booking with an open trip as In progress; the others are listed under "Earlier bookings" with their status.
- **Pick up** (Implemented): only while `CONFIRMED` and before the deadline. Refusals: `EXPIRED` "The time to pick up has passed. Make a new reservation"; wrong Hub (`INVALID_INPUT`) "Pick the vehicle up at {origin Hub}"; `INVALID_STATE` "This booking is no longer reserved". If the vehicle is no longer eligible, the code returns `RESOURCE_UNAVAILABLE` and changes nothing; M2's design says the booking is then cancelled (Planned).
- **Return** (Implemented): M2's `POST /reservations/{id}/return` with the Hub chosen in the list. Afterwards S5 lists the booking as `COMPLETED`; a receipt with Hub, space and time is Planned, because M2's list has no closed trips (DEV-10). If no space is free (`NO_PARKING`), nothing changes, the trip stays open and the screen shows nearby Hubs (Planned). If a fault was reported during the trip, the trip ends as `INCIDENT_ABORTED`.
- **Cancel** (Implemented, `UC-M2-03`): only on a Reserved booking; it then moves to "Earlier bookings" as `CANCELLED`. **Hold a return space** is Planned (`UC-M2-06`), because M2 has no route for it (DEV-15).
- **OVERDUE:** the status exists in the code. M5 sets it (Planned). It informs only; there are no fines (A-07).
- Pick up and return need the vehicle's current `version`. S5 sends the one in M2's list (`vehicle_versions`).
- Why: only the actions allowed in the booking's state are shown, and the deadline is shown as a time and a countdown.

### S6. Parking booking (Implemented) · `UC-M2-06` to `UC-M2-08`

```
+--------------------------------------------------------------------------+
| Parking                                                                  |
+--------------------------------------------------------------------------+
| Hub [ v H02 Dorm A ]            Vehicle [ v {59A-12345 E-scooter} ]      |
| Start [ today 14:00 v ]  (within 24 hours)                               |
| Stay  [ 120 ] minutes    (30 to 240)                                     |
| [ ] Also charge my vehicle during the stay                               |
|                                              [ Reserve parking ]         |
|                                                                          |
| Your parking booking                                                     |
|  {reservation_id}  Reserved   Space {H02-S014}                           |
|  Arrive between 14:00 and 14:10        Planned end 16:00                 |
|        [ I arrived ]    [ Cancel ]    (when in progress: [ I'm leaving ])|
+--------------------------------------------------------------------------+
```

- Not in M2's code yet (M2's Phase 3). The screen follows M2's requirements.
- Fields: Hub, one of the student's registered private EVs (S7), start within 24 hours, stay 30 to 240 minutes (default 120). The charging box asks M3 for a bay and charger together with the parking.
- **I arrived:** from the start time until start + 10 minutes. Later, the booking is `EXPIRED`.
- **Cancel:** before arrival. If charging is linked, the screen asks to cancel both (`LINKED_CHARGING`).
- Refusals: `HUB_CRITICAL` (Hub full, other Hubs suggested); no free space in that period; stay outside 30 to 240 minutes; `LIMIT_REACHED` (one parking booking at a time).
- After the planned end the booking stays active; there is no automatic release or fine.

### S7. Register a private EV (Implemented) · `UC-M3-04`

```
+--------------------------------------------------------------------------+
| My vehicle                                                               |
+--------------------------------------------------------------------------+
| Plate / code      [ 59A-12345 ]                                          |
| Type              [ v E-scooter ]                                        |
| Battery capacity  [ 3.2 ] kWh                                            |
| Current charge    [ 70 ] %                                               |
| Connector         [ ____________ ]                                       |
|                                        [ Save vehicle ]                  |
| Saved:  59A-12345 · E-scooter · {Away}                                   |
+--------------------------------------------------------------------------+
```

- Fields are the ones `FR-07.M3.1` lists (capacity, connector, current charge) plus plate and type, which `register_vehicle` in `core` needs.
- Only the charging module (M3), an operator or `iot_sim` may call `register_vehicle` (`permissions.py`). So the form posts to M3's route `POST /charging/private/vehicles`, called through `ui/api.py`. The saved vehicles are read from `core` (only the student's own).
- A new private EV starts as `IN_USE`, away from every Hub, shown as "Away". `AVAILABLE` is shown as "Parked" and `CHARGING` as "Charging".
- A duplicate plate should give `INVALID_INPUT` "This plate is already registered". Today M3's route fails on a refused `core` command, so the page shows `INTERNAL_ERROR` with a fixed message instead.

### S8. Request or schedule charging (Implemented for a private EV; change and cancel Planned) · `UC-M3-01` to `UC-M3-03`, `UC-M3-05`

```
+--------------------------------------------------------------------------+
| Charging                                                                 |
+--------------------------------------------------------------------------+
| Vehicle  (•) The rental vehicle I just returned  {ES-0045 at H05}        |
|          ( ) My private EV  [ v 59A-12345 ]                              |
| Hub      [ v H05 Campus A ]                                              |
| When     (•) Charge now                                                  |
|          ( ) Schedule   Date/time [ today 14:00 v ]  Duration [ 60 ] min |
|                                              [ Request charging ]        |
|                                                                          |
| Your charging requests                                                   |
|  {session}  Scheduled   Point {H05-CP03}   14:00 to 15:00                |
|        [ Change time ]   [ Cancel ]   (shown only before the cutoff)     |
|  {session}  Charging    Point {H05-CP01}   {54}% to {80}%                |
+--------------------------------------------------------------------------+
```

- The form calls M3's routes `POST /charging/requests/immediate` and `/charging/requests/schedule`, and the list "Your charging requests" comes from `GET /charging/sessions` (a student sees only their own), all through `ui/api.py`. The screen offers a private EV only: a returned rental vehicle needs a route of M2. In M3's requirements, `FR-06` is a student's charging request for a rental vehicle returned at a Hub (now or scheduled, with change and cancel), and `FR-07.M3.2` is a charging slot for a private EV.
- Change and Cancel are allowed up to a time limit before the slot. M3 gives no value for that limit.
- `UC-M3-01` says the student selects an available charging port. The REST route for charging points is for operators only, but a page can read them directly (`core.queries.list_charging_points`).
- The status words are the session states of M3's code: Queued, Scheduled, Charging, Completed, Interrupted, Cancelled.
- If no port is free, M3 offers another time, another port in the same Hub, or another Hub (`BR-M3-02`). The screen shows M3's refusal and does not offer these alternatives yet.
- Students do not see the priority score or the queue length; the operator does (O3).

### S9. Error block · `NFR-21`

```
+--------------------------------------------------------------+
| ⚠ We could not reserve this vehicle                          |
|   Someone else reserved it a moment ago.                     |
|   [ See other vehicles at H01 ]   [ Try H02 (5 vehicles) ]   |
|   Details: CONFLICT                                          |
+--------------------------------------------------------------+
```

Every refusal shows what failed, the cause in plain words, up to two alternatives, and the code under "Details". `INTERNAL_ERROR` shows a fixed message and never a stack trace.

## 3. Messages for M2's error codes

These are the codes in `BookingErrorCode` in the M2 code. M2's own messages are short English texts for developers, so the screen should write its own. These messages are Planned (DEV-13); today the error block shows M2's message and code.

| Code | Message to the student | Alternative |
|---|---|---|
| `FORBIDDEN` | You are not allowed to do this. | Back |
| `NOT_FOUND_OR_NOT_OWNED` | This booking was not found. | My bookings |
| `INVALID_INPUT` | The field message | Fix the field |
| `LIMIT_REACHED` | You already have a rental. | My bookings |
| `CONFLICT` | Someone else changed this just now. | Reload the list |
| `INVALID_STATE` | This is no longer possible for this booking. | My bookings |
| `EXPIRED` | The time to do this has passed. | Make a new reservation |
| `RESOURCE_UNAVAILABLE` | This vehicle can no longer be rented. | Other vehicles |
| `NO_PARKING` | No space is free at this Hub. | Nearby Hubs |
| `INTERNAL_ERROR` | Something went wrong. Nothing was changed. | Retry |

The M2 documents also use `HUB_CRITICAL`, `NO_VEHICLE`, `ALREADY_CANCELLED` and `LINKED_CHARGING`. They are not in the code yet. Errors from `core` reads have the same names whether a page reads directly or through REST (`UNAUTHENTICATED`, `FORBIDDEN`, `NOT_FOUND`, `INVALID_INPUT`, `INTERNAL_ERROR`).

## 4. Open points

1. Settled with M1 (D-026): a page reads `core` directly and calls the other modules' REST routes through the internal client in `src/ui/api.py`.
2. The 5-second rule is M2's proposal and asks M1 and M7 to review. This file uses it.
3. Settled: the charging screens use the session states of M3's code (see S8).
4. M3's branch holds report text in `fr-06-07-11-charging.md`. The `FR-06` and `UC-M3` text used here is the version on `develop`.
