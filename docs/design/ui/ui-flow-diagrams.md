# UI Flow Diagrams

> Owner: M7 (Nguyễn Trung Kiên) · Date: 2026-11-09 · Revised for Phase 3: 2026-11-25 · Reviewer: M5 (Đỗ Hoàng Việt)
> One diagram for each actor. Screens `S1` to `S9` are in `wireframes-student.md`, `O1` to `O6` in `wireframes-operator.md`.
> A box is a screen; every screen is in the code. A line is a move from one screen to another. The commands on each screen and what happens when they are refused are in the tables. `iot_sim` has no screen.

## 1. Student

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
    S4 -->|refused| S2
    S5 -->|own EV| S8
    S6 -->|after Arrive| S8

```

*Student flows.*

After login the student lands on S2. Find a Hub, My bookings, Parking, Charging, My EV and Logout are in the header of every screen. The main path is S2, S3, S4, S5. A returned rental vehicle is charged by operators; S5 links to S8 for the student's own EV. A private EV is parked first (S6, Arrive) and then charged in S8; there is no joint parking and charging booking (`BR-M2-12`, DEV-15).

| Screen | Commands | Use cases | Backend | If refused |
|---|---|---|---|---|
| S3, S4 | Search, `reserve` | `UC-M2-01`, `UC-M2-02` | Implemented (M2 routes) | Error block with M2's cause and code |
| S5 | Pick up | `UC-M2-04` | Implemented | Expired: make a new reservation |
| S5 | Return | `UC-M2-05` | Implemented | No space: the trip stays open (nearby Hubs planned) |
| S5 | Cancel | `UC-M2-03` | Implemented | Offered only before pick-up |
| S5 | Hold a return space | `UC-M2-06` | Implemented | No free space: other Hub |
| S6 | Reserve, arrive, leave, cancel parking | `UC-M2-06` to `UC-M2-08` | Implemented | No free space, too early, deadline passed |
| S7 | Register a private EV | `UC-M3-04` | Implemented (M3 route) | Duplicate plate: error block |
| S8 | Request charging now or at a time | `UC-M3-01`, `UC-M3-02` | Implemented (M3 route) | Error block with M3's cause |
| S8 | Change, cancel charging | `UC-M3-03`, `UC-M3-05` | Implemented | No port free: other time, port or Hub |

## 2. Operator

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
```

*Operator flows.*

After login the operator lands on O1. The tab bar and the alert strip are on every screen, so each tab screen is one click from the others, and a Hub in `WARNING` or `CRITICAL` is always one click away (NFR-20). O2 is not a tab: it opens from a Hub card or the alert strip. In M5's flow the system restores a resource itself when the device is healthy again, so the dotted line from O5 to O2 is only for a manual override. Simulation never changes real state: a recommendation goes to the owning module only after the operator approves it, and that module can refuse it. O6 runs all five scenarios of M6.

| Screen | Commands | Use cases | Backend | If refused |
|---|---|---|---|---|
| O1, O2 | View, filter; change the state of a vehicle, point or Hub | `UC-M7-01`, `UC-M7-02`, `UC-M7-07` | Implemented (core commands) | Error block with core's cause and a link back to the Hub (e.g. VERSION_CONFLICT); a point in use cannot be set AVAILABLE |
| O3 | View the queue of a Hub | `UC-M7-03` | Implemented (M3 route) | Error block with M3's cause |
| O3 | Optimize the queue; start, finish, stop a session | `UC-M7-04` | Implemented | M3's cause |
| O4 | Plan, create a task ("Move vehicles yourself"), approve, pick-up, delivery, cancel | `UC-M7-05`, `UC-M7-06` | Implemented | Task `FAILED` or request refused, with the reason on the card |
| O4 | Reject, settings | `UC-M4-02`, `UC-M4-09` | Implemented | M4's cause |
| O5 | Acknowledge, escalate, resolve, close; show history | `UC-M7-08` | Implemented | Action hidden when the status does not allow it |
| O6 | Five scenarios on a copy, approve or reject a recommendation, export | `UC-M7-09`, `UC-M7-10` | Implemented (M6 route) | M6's message for an invalid input; M4 may refuse an approved recommendation |

## 3. Behaviour shared by the flows

- **Session.** The token is kept in a cookie and lasts 60 minutes by default. When it is no longer valid, any screen goes to S1; after login the user lands on the home screen of their role, not on the screen they were on.
- **Role.** A student cannot reach O1 to O6. After login each role goes to its own home screen.
- **Retries.** The pages call the modules inside the same process (D-026), so a command does not time out on a network. A repeated rental command is answered by M2 from its own records instead of acting twice (D-015). No timeout rule exists for the operator's commands.
- **Refresh.** O1 re-reads its Hub cards and the time of the data every 3 seconds, so a change appears there within 5 seconds (NFR-01). The other screens show the new state after an action or Refresh, and every screen shows the time of its data.
- **Empty, loading and error states.** Every list and form has them (M8 tests them).
- **Events.** The UI never talks to `iot_sim` and gets no push. `core` publishes events inside the process after a commit and does not store them, so the UI re-reads the state and shows `as_of`.
