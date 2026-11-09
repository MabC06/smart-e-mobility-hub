# UI Flow Diagrams

> Owner: M7 (Nguyễn Trung Kiên) · Date: 2026-11-09 · Reviewer: M5 (Đỗ Hoàng Việt)
> One diagram for each actor. Screens `S1` to `S9` are in `wireframes-student.md`, `O1` to `O6` in `wireframes-operator.md`.
> A box is a screen. A dashed box is a screen that is only in the requirements, not in the code yet. A line is a move from one screen to another. The commands on each screen and what happens when they are refused are in the tables. `iot_sim` has no screen.

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
    S4 -->|refused| S3
    S5 -->|after a return| S8
    S6 -->|also charge| S8

    classDef planned stroke-dasharray: 5 4
    class S6,S7,S8 planned
```

*Student flows.*

After login the student lands on S2. My bookings and Logout are in the header of every screen. The main path is S2, S3, S4, S5. After a return the student can go on to charging for that vehicle (`FR-06.1`). A parking booking with the charging box ticked continues in S8, because parking and charging are booked together (`BR-M2-12`).

| Screen | Commands | Use cases | Backend | If refused |
|---|---|---|---|---|
| S3, S4 | Search, `reserve` | `UC-M2-01`, `UC-M2-02` | `reserve` implemented; M2 search planned | Error with alternatives, back to S3 |
| S5 | Pick up | `UC-M2-04` | Implemented | Expired: make a new reservation |
| S5 | Return | `UC-M2-05` | Implemented | No space: nearby Hubs, the trip stays open |
| S5 | Cancel, hold a return space | `UC-M2-03`, `UC-M2-06` | Planned | Trip already started: return the vehicle |
| S6 | Reserve, arrive, leave, cancel parking | `UC-M2-06` to `UC-M2-08` | Planned | Hub full: other Hub or time |
| S7 | Register a private EV | `UC-M3-04` | `core` command implemented; M3 route planned | Duplicate plate: field message |
| S8 | Request, change, cancel charging | `UC-M3-01` to `UC-M3-03`, `UC-M3-05` | Planned | No port free: other time, port or Hub |

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

    classDef planned stroke-dasharray: 5 4
    class O3,O6 planned
```

*Operator flows.*

After login the operator lands on O1. The tab bar and the alert strip are on every screen, so each tab screen is one click from the others, and a Hub in `WARNING` or `CRITICAL` is always one click away (NFR-20). O2 is not a tab: it opens from a Hub card or the alert strip. In M5's flow the system restores a resource itself when the device is healthy again, so the dotted line from O5 to O2 is only for a manual override. Simulation never changes real state: a recommendation goes to the owning module only after the operator approves it, and that module can refuse it. O6 is Planned except the demand-surge scenario, which exists in M6's code.

| Screen | Commands | Use cases | Backend | If refused |
|---|---|---|---|---|
| O1, O2 | View; change the state of a vehicle, point or Hub | `UC-M7-01`, `UC-M7-02`, `UC-M7-07` | Reads implemented; actions and M5 alerts planned | Not allowed in this state: handle the reservation or trip first; changed by someone else: refreshed |
| O3 | Change slot, recalculate | `UC-M7-03`, `UC-M7-04` | Planned (M3) | Not offered by M3 |
| O4 | Plan, approve, pick-up, delivery, cancel, settings | `UC-M7-05`, `UC-M7-06`, `UC-M4-09` | Implemented | Task `FAILED` or request refused, with the reason on the card |
| O4 | Reject | `UC-M4-02` | Planned | |
| O5 | Acknowledge, resolve, close | `UC-M7-08` | Implemented (M5's code, not yet merged) | Action hidden when the status does not allow it |
| O6 | Run on a copy, approve a recommendation | `UC-M7-09`, `UC-M7-10` | Demand surge implemented; rest planned (M6) | Field message for invalid inputs; the owning module may refuse |

## 3. Behaviour shared by the flows

- **Session.** The token is kept in a cookie and lasts 60 minutes by default. When it is no longer valid, any screen goes to S1 and returns to the same screen after login.
- **Role.** A student cannot reach O1 to O6. After login each role goes to its own home screen.
- **Slow commands.** For rental commands M2 proposes that after 5 seconds without an answer the screen says "Outcome unknown, checking status" and reads the booking again before saying "failed". A retry reuses the same reservation ID. No timeout rule exists for the operator's commands.
- **Refresh.** Parts of a page are re-read by polling every 3 seconds, so a change appears within 5 seconds (NFR-01).
- **Empty, loading and error states.** Every list and form has them (M8 tests them).
- **Events.** The UI never talks to `iot_sim` and gets no push. `core` publishes events inside the process after a commit and does not store them, so the UI re-reads the state and shows `as_of`.
