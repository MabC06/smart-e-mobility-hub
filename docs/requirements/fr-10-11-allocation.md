# Allocation and Dispatching — Requirements 

2412466 Huỳnh Minh Nhật
## 1.Main problems

This module decides "where limited resources go":

1. It moves rental vehicles between Hubs, so no Hub runs out of vehicles or out of parking spaces (FR-10).
2. It decides who gets a parking space or charging bay when several requests want the same one (FR-11, allocation side).

## 2. Skateholders

| Actor | What they do with this module |
| **Operator** | Sees recommendations, approves or rejects tasks, confirms pick-up and return, changes settings. |
| **Student** | Does not call it directly. The reservation module asks for alternative Hubs for the student. |
| **System / Scheduler** | Settles conflicts and re-plans automatically. |
| **Sensor / event source** | Reports movements and failures. Simulated by `iot_sim`. |

## 3. Functional requirements


1)FR-10 — Redistribute rental vehicles between Hubs

| ID | The system must... | UC | BR |
|---|---|---|---|
| FR-10(a) | Show how balanced each Hub is: available vehicles, free spaces, free charging bays, expected demand soon. | UC-A01 | BR A03, A05 |
| FR-10(b) | Find Hubs that are short of vehicles, and Hubs with too many vehicles or almost no free space. | UC-A01 | BR A05 |
| FR-10(c) | Propose a plan: dispatch tasks with source, destination, quantity, priority and reason. | UC-A01 | BR A03, A06 |
| FR-10(d) | Let the operator approve, reject, or reduce a task. Check the conditions again at approval. | UC-A02 | BR A02, A04, A07, A08 |
| FR-10(e) | When a task is approved: hold the vehicles and a destination space, confirm pick-up and return, or cancel and release everything. | UC-A02, A03, A04 |BR  A04, A07, A09 |
| FR-10(f) | Suggest alternative Hubs when the requested Hub has no vehicle or no space. | UC-A05 | BR A10 |
| FR-10(g) | Re-plan when something changes (Hub full, task failed, incident). Do not create duplicate tasks. | UC-A08 | BR A06 |

### FR-11 — Charging priority (allocation side)

| ID | The system must... | UC | BR |
| FR-11(a) | Decide who gets a space or charging bay when requests compete, using the priority order. | UC-A06 | BR A01, A02 |
| FR-11(b) | Move charging requests to another point, another Hub, or the queue when a charging point fails or a Hub has no free bay. | UC-A07 | BR A11 |
| FR-11(c) | Never go over a Hub's capacity. | UC-A02, A03 | BR A04, A09 |

## 4. Business rules

| ID | Rule |
|---|---|
| BR-A01 | **Priority when requests compete** (highest first): 1) operator order for an incident, 2) confirmed reservation starting soon, 3) vehicle in use that needs a space to return, 4) charging for a vehicle with a reservation soon, 5) charging for a low-battery rental vehicle, 6) charging for a private vehicle, 7) rebalancing move, 8) walk-in. Same level: the earlier request wins; then the lower ID. |
| BR-A02 | Never cancel a confirmed or active reservation to serve a lower priority. |
| BR-A03 | Only move a vehicle that is `Available`, has no reservation soon, and has enough battery. |
| BR-A04 | Hold a free space at the destination before the move starts. Never send vehicles to a Hub with no free space left. |
| BR-A05 | The source Hub must keep a minimum stock of available vehicles after the move. |
| BR-A06 | Limit the number of active tasks going in or out of one Hub. |
| BR-A07 | One vehicle can be in at most one active task. |
| BR-A08 | A task changes state only in this order: `Recommended → Approved → InProgress → Completed`. It can also end as `Rejected`, `Cancelled` or `Failed`. A wrong change gives an error and changes nothing. |
| BR-A09 | A charging vehicle uses exactly one space. Do not move it until charging has stopped. |
| BR-A10 | If nothing is available, refuse with a reason (`NO_VEHICLE`, `NO_PARKING`, `NO_CHARGER`, `ALL_HUBS_FULL`) and suggest other Hubs if any. |
| BR-A11 | If a charging point fails, move its sessions elsewhere or back to the queue. No vehicle may be left without a space. |
| BR-A12 | Log every decision and state change: what, when, why. |

Thresholds (minimum stock, minimum battery, time window, task limit) are settings, not fixed numbers in code.

## 5. Use cases

![Use-case diagram of the allocation module](diagrams/allocation-use-cases.png)

*UC-A04 (cancel) and UC-A08 (re-plan after a failure) extend UC-A03.*

| ID     | Name |                  Actor |
| UC-A01 | View redistribution recommendations | Operator |
| UC-A02 | Approve, reject or adjust a task | Operator |
| UC-A03 | Carry out a dispatch task | Operator, Sensor |
| UC-A04 | Cancel a dispatch task | Operator |
| UC-A05 | Suggest alternative Hubs | Student (via M2), System |
| UC-A06 | Settle competing requests | System |
| UC-A07 | Handle a failed charging point | Sensor, System |
| UC-A08 | Re-plan after an event | System, Sensor |
| UC-A09 | Change allocation settings | Operator |

### UC-A01 — View redistribution recommendations
- **Actor:** Operator
- **Before:** The operator is logged in.
- **Steps:**
  1. The operator opens the dispatch screen.
  2. The system checks every Hub and the expected demand.
  3. The system shows a list of tasks with quantity, priority and reason.
- **If not normal:** Network is balanced → show "no task needed". Data is old → show its time with a warning.
- **After:** Tasks are saved as `Recommended`. Nothing else changes.

### UC-A02 — Approve, reject or adjust a task
- **Actor:** Operator
- **Before:** The task is `Recommended`.
- **Steps:**
  1. The operator chooses *Approve*, and may lower the quantity.
  2. The system checks the rules again (BR-A02 to A07).
  3. The system holds the vehicles and a destination space in one step (all or nothing).
  4. The task becomes `Approved`.
- **If not normal:** Conditions changed, or another request took the resource → nothing is held, the task becomes `Failed` with a reason. The operator chooses *Reject* → `Rejected`.
- **After:** Resources are held, or nothing changed.

### UC-A03 — Carry out a dispatch task
- **Actor:** Operator (confirms), Sensor (reports, simulated)
- **Before:** The task is `Approved`.
- **Steps:**
  1. Pick-up at the source Hub is confirmed → task `InProgress`.
  2. Return at the destination Hub is confirmed.
  3. The system updates vehicle location and both Hubs' space counts → task `Completed`.
- **If not normal:** Vehicle missing or broken, or the task takes too long → `Failed`, held resources are released, and a re-plan starts (UC-A08).
- **After:** Capacity limits still hold. Every change is logged.

### UC-A04 — Cancel a dispatch task
- **Actor:** Operator
- **Before:** The task is `Approved` or `InProgress`.
- **Steps:**
  1. The operator cancels and gives a reason.
  2. The system releases the held vehicles and spaces.
  3. The task becomes `Cancelled`.
- **If not normal:** A vehicle already reached the destination → it is completed there, not moved back.
- **After:** Nothing stays held.

### UC-A05 — Suggest alternative Hubs
- **Actor:** Student (through the reservation module), System
- **Before:** The reservation module cannot serve a request at the requested Hub.
- **Steps:**
  1. The reservation module asks for alternatives.
  2. The system keeps the Hubs that still have what is needed.
  3. The system ranks them: closer first, then more resources, then better battery.
  4. The system returns the top few.
- **If not normal:** No Hub qualifies → return a reason code (BR-A10).
- **After:** Nothing changes. Holding a resource is done later by the reservation module.

### UC-A06 — Settle competing requests
- **Actor:** System
- **Before:** Two or more requests want the same vehicle, space or charging bay.
- **Steps:**
  1. The system orders the requests by BR-A01.
  2. The first request gets the resource.
  3. The others get a "conflict" answer with a reason and, if possible, an alternative.
- **If not normal:** Requests arrive at the same moment → exactly one succeeds.
- **After:** No resource is given twice.

### UC-A07 — Handle a failed charging point
- **Actor:** Sensor (reports the failure), System
- **Before:** A charging-point failure event was accepted by `core`.
- **Steps:**
  1. The system finds the sessions and queued requests of that point.
  2. For each one it looks for a free point in the same Hub, then in another Hub.
  3. Requests are moved or put back in the queue, together with M3.
  4. The operator can see which sessions were affected.
- **If not normal:** No free point anywhere → requests go back to the queue with reason `NO_CHARGER`, and the operator is told.
- **After:** No vehicle is left without a space (BR-A11).

### UC-A08 — Re-plan after an event
- **Actor:** System, Sensor
- **Before:** A Hub became full, a task failed, or an incident affects a Hub.
- **Steps:**
  1. The system recalculates the affected Hubs.
  2. It creates new tasks and withdraws old `Recommended` tasks that no longer make sense.
- **If not normal:** The same event arrives twice → no duplicate tasks.
- **After:** The task list matches the current state.

### UC-A09 — Change allocation settings
- **Actor:** Operator
- **Before:** The operator is logged in.
- **Steps:**
  1. The operator opens the settings.
  2. The operator changes a value (for example the minimum stock).
  3. The system checks the range and saves it.
- **If not normal:** Value out of range → error with a clear message.
- **After:** New plans use the new value. Approved tasks keep their quantities.

## 6. Open points(Not decision yet)

Each question has an assumption used in this version, so the document is valid now. If the answer is different, only the listed parts change.

| # | Question | Assumed now | Parts to change if different | Ask |
|---|---|---|---|---|
| 1 | Is the FR-11 split with M3 acceptable? | Yes (section 3) | FR-11, BR-A01 levels 4–6, BR-A11, UC-A06, UC-A07 | M3 |
| 2 | Is a dispatch a system-made reservation (purpose `REBALANCE`), so the vehicle states need no new state? | Yes | BR-A08, BR-A09, UC-A02, UC-A03 | M1, M2 |
| 3 | Which public interface does M4 use to read upcoming reservations and charging plans? | A public interface from M2 and M3, defined in Core API spec v1 | Design phase only | M1 |
| 4 | Do low-battery and near-full limits use the same values as M3 and M5? | Yes | Settings list | M3, M5 |
| 5 | Does the operator approve every task, or is there an automatic mode for demos? | Operator approves every task | UC-A02 | M5, M7 |
| 6 | Is a fixed "closeness between Hubs" table acceptable (no route planning)? | Yes | Design phase only | M1, M6 |
