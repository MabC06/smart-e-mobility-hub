# Allocation and Dispatching — Requirements 

2412466 Huỳnh Minh Nhật
## 1. Main problems

This module decides "where limited resources go":

1. It moves rental vehicles between Hubs, so no Hub runs out of vehicles or out of parking spaces (FR-10).
2. It decides who gets a parking space or charging bay when several requests want the same one (FR-11, allocation side).

## 2. Stakeholders

| Actor | What they do with this module |
|---|---|
| **Operator** | Sees recommendations, approves or rejects tasks, confirms pick-up and return, changes settings. |
| **Student** | Does not call it directly. The reservation module asks for alternative Hubs for the student. |
| **System / Scheduler** | Settles conflicts and re-plans automatically. |
| **Sensor / event source** | Reports movements and failures. Simulated by `iot_sim`. |

## 3. Functional requirements


### FR-10 — Redistribute rental vehicles between Hubs

| ID | The system must... | UC | BR |
|---|---|---|---|
| FR-10.1 | Show how balanced each Hub is: available vehicles, free spaces, free charging bays, expected demand soon. | UC-M4-01 | BR-M4-03, BR-M4-05 |
| FR-10.2 | Find Hubs that are short of vehicles, and Hubs with too many vehicles or almost no free space. | UC-M4-01 | BR-M4-05 |
| FR-10.3 | Propose a plan: dispatch tasks with source, destination, quantity, priority and reason. | UC-M4-01 | BR-M4-03, BR-M4-06 |
| FR-10.4 | Let the operator approve, reject, or reduce a task. Check the conditions again at approval. | UC-M4-02 | BR-M4-02, BR-M4-04, BR-M4-07, BR-M4-08 |
| FR-10.5 | When a task is approved: hold the vehicles and a destination space, confirm pick-up and return, or cancel and release everything. | UC-M4-02, UC-M4-03, UC-M4-04 | BR-M4-04, BR-M4-07, BR-M4-09 |
| FR-10.6 | Suggest alternative Hubs when the requested Hub has no vehicle or no space. | UC-M4-05 | BR-M4-10 |
| FR-10.7 | Re-plan when something changes (Hub full, task failed, incident). Do not create duplicate tasks. | UC-M4-08 | BR-M4-06 |

### FR-11 — Charging priority (allocation side)

| ID | The system must... | UC | BR |
|---|---|---|---|
| FR-11.M4.1 | Decide who gets a space or charging bay when requests compete, using the priority order. | UC-M4-06 | BR-M4-01, BR-M4-02 |
| FR-11.M4.2 | Find an alternative charging point or Hub for the displaced charging requests when the Hub has no free bay. Called from M3's flow (M3 owns failed-charging-point handling, D-012). | UC-M4-07 | BR-M4-11 |
| FR-11.M4.3 | Never go over a Hub's capacity. | UC-M4-02, UC-M4-03 | BR-M4-04, BR-M4-09 |

## 4. Business rules

| ID | Rule | Trace |
|---|---|---|
| BR-M4-01 | **Priority when requests compete** (highest first): 1) operator order for an incident, 2) confirmed reservation starting soon, 3) vehicle in use that needs a space to return, 4) charging for a vehicle with a reservation soon, 5) charging for a low-battery rental vehicle, 6) charging for a private vehicle, 7) rebalancing move, 8) walk-in. Same level: the earlier request wins; then the lower ID. Between charging requests of the same level (4 to 6), BR-M3-03 decides (D-012). | FR-11.M4.1; BR-M3-03 |
| BR-M4-02 | Never cancel a confirmed or active reservation to serve a lower priority. | FR-10.4, FR-11.M4.1 |
| BR-M4-03 | Only move a vehicle that is `Available`, has no reservation soon, and has enough battery. | FR-10.1, FR-10.3 |
| BR-M4-04 | Hold a free space at the destination before the move starts. Never send vehicles to a Hub with no free space left. | FR-10.4, FR-10.5, FR-11.M4.3 |
| BR-M4-05 | The source Hub must keep a minimum stock of available vehicles after the move. | FR-10.1, FR-10.2 |
| BR-M4-06 | Limit the number of active tasks going in or out of one Hub. | FR-10.3, FR-10.7 |
| BR-M4-07 | One vehicle can be in at most one active task. | FR-10.4, FR-10.5 |
| BR-M4-08 | A task changes state only in this order: `Recommended → Approved → InProgress → Completed`. It can also end as `Rejected`, `Cancelled` or `Failed`. A wrong change gives an error and changes nothing. | FR-10.4 |
| BR-M4-09 | A charging vehicle uses exactly one space. Do not move it until charging has stopped. | FR-10.5, FR-11.M4.3 |
| BR-M4-10 | If nothing is available, refuse with a reason (`NO_VEHICLE`, `NO_PARKING`, `NO_CHARGER`, `ALL_HUBS_FULL`) and suggest other Hubs if any. | FR-10.6 |
| BR-M4-11 | When M3 asks for an alternative for requests displaced by a failed charging point or a Hub with no free bay, offer another charging point or Hub that has a free bay. If none exists, answer `NO_CHARGER`. No vehicle may be left without a space. | FR-11.M4.2 |
| BR-M4-12 | Log every decision and state change: what, when, why. | — (general rule, NFR-25) |

Thresholds (minimum stock, minimum battery, time window, task limit) are settings, not fixed numbers in code.

## 5. Use cases

| ID | Name | Actor |
|---|---|---|
| UC-M4-01 | View redistribution recommendations | Operator |
| UC-M4-02 | Approve, reject or adjust a task | Operator |
| UC-M4-03 | Carry out a dispatch task | Operator, Sensor |
| UC-M4-04 | Cancel a dispatch task | Operator |
| UC-M4-05 | Suggest alternative Hubs | Student (via M2), System |
| UC-M4-06 | Settle competing requests | System |
| UC-M4-07 | Find an alternative charging point for displaced requests | M3 (charging module), System |
| UC-M4-08 | Re-plan after an event | System, Sensor |
| UC-M4-09 | Change allocation settings | Operator |

### UC-M4-01 — View redistribution recommendations
- **Actor:** Operator
- **Before:** The operator is logged in.
- **Steps:**
  1. The operator opens the dispatch screen.
  2. The system checks every Hub and the expected demand.
  3. The system shows a list of tasks with quantity, priority and reason.
- **If not normal:** Network is balanced → show "no task needed". Data is old → show its time with a warning.
- **After:** Tasks are saved as `Recommended`. Nothing else changes.
- Trace: FR-10.1, FR-10.2, FR-10.3; BR-M4-03, BR-M4-05, BR-M4-06

### UC-M4-02 — Approve, reject or adjust a task
- **Actor:** Operator
- **Before:** The task is `Recommended`.
- **Steps:**
  1. The operator chooses *Approve*, and may lower the quantity.
  2. The system checks the rules again (BR-M4-02 to BR-M4-07).
  3. The system holds the vehicles and a destination space in one step (all or nothing).
  4. The task becomes `Approved`.
- **If not normal:** Conditions changed, or another request took the resource → nothing is held, the task becomes `Failed` with a reason. The operator chooses *Reject* → `Rejected`.
- **After:** Resources are held, or nothing changed.
- Trace: FR-10.4, FR-10.5, FR-11.M4.3; BR-M4-02, BR-M4-04, BR-M4-07, BR-M4-08, BR-M4-09

### UC-M4-03 — Carry out a dispatch task
- **Actor:** Operator (confirms), Sensor (reports, simulated)
- **Before:** The task is `Approved`.
- **Steps:**
  1. Pick-up at the source Hub is confirmed → task `InProgress`.
  2. Return at the destination Hub is confirmed.
  3. The system updates vehicle location and both Hubs' space counts → task `Completed`.
- **If not normal:** Vehicle missing or broken, or the task takes too long → `Failed`, held resources are released, and a re-plan starts (UC-M4-08).
- **After:** Capacity limits still hold. Every change is logged.
- Trace: FR-10.5, FR-11.M4.3; BR-M4-04, BR-M4-07, BR-M4-09

### UC-M4-04 — Cancel a dispatch task
- **Actor:** Operator
- **Before:** The task is `Approved` or `InProgress`.
- **Steps:**
  1. The operator cancels and gives a reason.
  2. The system releases the held vehicles and spaces.
  3. The task becomes `Cancelled`.
- **If not normal:** A vehicle already reached the destination → it is completed there, not moved back.
- **After:** Nothing stays held.
- Trace: FR-10.5; BR-M4-04, BR-M4-07, BR-M4-09

### UC-M4-05 — Suggest alternative Hubs
- **Actor:** Student (through the reservation module), System
- **Before:** The reservation module cannot serve a request at the requested Hub.
- **Steps:**
  1. The reservation module asks for alternatives.
  2. The system keeps the Hubs that still have what is needed.
  3. The system ranks them: closer first, then more resources, then better battery.
  4. The system returns the top few.
- **If not normal:** No Hub qualifies → return a reason code (BR-M4-10).
- **After:** Nothing changes. Holding a resource is done later by the reservation module.
- Trace: FR-10.6; BR-M4-10

### UC-M4-06 — Settle competing requests
- **Actor:** System
- **Before:** Two or more requests want the same vehicle, space or charging bay.
- **Steps:**
  1. The system orders the requests by BR-M4-01.
  2. The first request gets the resource.
  3. The others get a "conflict" answer with a reason and, if possible, an alternative.
- **If not normal:** Requests arrive at the same moment → exactly one succeeds.
- **After:** No resource is given twice.
- Trace: FR-11.M4.1; BR-M4-01, BR-M4-02

### UC-M4-07 — Find an alternative charging point for displaced requests
- **Actor:** M3 (charging module) calls it from UC-M3-08; System
- **Before:** In UC-M3-08, M3 has charging requests that lost their charging point and finds no free charging point at the current Hub.
- **Steps:**
  1. M3 asks the allocation module for an alternative for each displaced request.
  2. The system looks for a free charging point in another Hub (closer first).
  3. The system returns the best alternative for each request.
  4. M3 moves or re-queues the sessions. M3 owns the failure handling (UC-M3-08).
- **If not normal:** No free charging point anywhere → return `NO_CHARGER`. M3 puts the requests back in its queue.
- **After:** Nothing changes in the allocation module. No vehicle is left without a space (BR-M4-11).
- Trace: FR-11.M4.2; BR-M4-11

### UC-M4-08 — Re-plan after an event
- **Actor:** System, Sensor
- **Before:** A Hub became full, a task failed, or an incident affects a Hub.
- **Steps:**
  1. The system recalculates the affected Hubs.
  2. It creates new tasks and withdraws old `Recommended` tasks that no longer make sense.
- **If not normal:** The same event arrives twice → no duplicate tasks.
- **After:** The task list matches the current state.
- Trace: FR-10.7; BR-M4-06

### UC-M4-09 — Change allocation settings
- **Actor:** Operator
- **Before:** The operator is logged in.
- **Steps:**
  1. The operator opens the settings.
  2. The operator changes a value (for example the minimum stock).
  3. The system checks the range and saves it.
- **If not normal:** Value out of range → error with a clear message.
- **After:** New plans use the new value. Approved tasks keep their quantities.
- Trace: (no FR, supporting use case); BR-M4-03, BR-M4-05, BR-M4-06

## 6. Open points

Each question has an assumption used in this version, so the document is valid now. If the answer is different, only the listed parts change.

| # | Question | Assumed now | Parts to change if different | Ask |
|---|---|---|---|---|
| 1 | Is the FR-11 split with M3 acceptable? | **Decided:** D-012 (Accepted) gives failed-charging-point handling to M3 and the cross-Hub lookup to M4 | Only if M3 or M4 objects in Phase 1: FR-11.M4.1 to FR-11.M4.3, BR-M4-01, BR-M4-11, UC-M4-06, UC-M4-07 | M3 |
| 2 | Is a dispatch a system-made reservation (purpose `REBALANCE`), so the vehicle states need no new state? | Yes | BR-M4-08, BR-M4-09, UC-M4-02, UC-M4-03 | M1, M2 |
| 3 | Which public interface does M4 use to read upcoming reservations and charging plans? | A public interface from M2 and M3, defined in Core API spec v1 | Design phase only | M1 |
| 4 | Do low-battery and near-full limits use the same values as M3 and M5? | Yes | Settings list | M3, M5 |
| 5 | Does the operator approve every task, or is there an automatic mode for demos? | Operator approves every task | UC-M4-02 | M5, M7 |
| 6 | Is a fixed "closeness between Hubs" table acceptable (no route planning)? | Yes | Design phase only | M1, M6 |
