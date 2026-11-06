# FR-08 and FR-09: System Monitoring & Operational Incident Handling Specifications

**Owner:** M5 — Đỗ Hoàng Việt (2453413)  
**Status:** Final v1.1 · 2026-11-06 (Phase 1 — System Design)  
**Related Design Documents:**
- Activity Diagram: [`docs/design/behavioral/incident-activity-diagram.md`](../design/behavioral/incident-activity-diagram.md)
- Sequence Diagram: [`docs/design/behavioral/monitoring-sequence-diagram.md`](../design/behavioral/monitoring-sequence-diagram.md)
- Incident Data Model: [`docs/design/structural/incident-data-model.md`](../design/structural/incident-data-model.md)
- Use Case Diagram: [`docs/requirements/use-case-diagrams/uc-m5-monitoring.puml`](use-case-diagrams/uc-m5-monitoring.puml)

---

## 1. Document Overview

This document specifies the software requirements for **FR-08 (System Monitoring)** and **FR-09 (Incident Handling)** of the **Smart E-Mobility Hub** system for the VNU-HCM Urban Area. It breaks down the high-level capabilities into granular sub-requirements, defines the operational incident taxonomy, outlines system escalation rules, and provides structured Use-Case tables.

---

## 2. Functional Requirements

### FR-08: System Monitoring

- **FR-08.1 – Real-Time Hub Resource Tracking:** The system shall continuously ingest live telemetry data (`src/iot_sim/`) covering vehicle states, battery levels ($SoC\%$), parking slot occupancy, and charging port statuses across all Mobility Hubs in the VNU-HCM network.
- **FR-08.2 – Utilization & Metrics Computation:** The system shall automatically compute real-time capacity utilization percentages and fleet readiness metrics for each individual Mobility Hub and display them on the operator dashboard.
- **FR-08.3 – Capacity Warning & Threshold Alerting:** The system shall flag and visually highlight Mobility Hubs that approach or exceed predefined operational warning thresholds (e.g., parking occupancy $\ge 90\%$) on the operator console.
- **FR-08.4 – Network State Synchronization:** The system shall synchronize all real-time aggregated metrics and telemetry logs with the core domain state management module (`src/core/`) using `set_hub_status()`.

### FR-09: Incident Handling

- **FR-09.1 – Automated Incident Detection:** The system shall automatically detect operational failures, such as charging hardware faults, IoT communication dropouts, or parking capacity overflows, based on incoming error codes and sensor timeouts.
- **FR-09.2 – Incident Classification & Ticket Generation:** The system shall categorize detected incidents by type and severity level (Low, Medium, High, Critical) and automatically generate structured incident tickets into the operator work queue.
- **FR-09.3 – Automated Safety Interlocks:** The system shall execute automated safety responses upon incident detection, such as isolating a faulty charging port or locking out critically low-battery vehicles from the active rental pool.
- **FR-09.4 – Incident Lifecycle Tracking:** The system shall track and update incident ticket statuses through their complete operational lifecycle (`OPEN` $\rightarrow$ `IN_PROGRESS` $\rightarrow$ `ESCALATED` $\rightarrow$ `RESOLVED` $\rightarrow$ `CLOSED`) with complete audit logs (`NFR-25`).

---

## 3. Incident Type List (Taxonomy)

| Incident ID     | Category            | Description                                                       | Severity | Default Trigger Condition                                                               |
| :-------------- | :------------------ | :---------------------------------------------------------------- | :------- | :-------------------------------------------------------------------------------------- |
| **INC-HW-01**   | Hardware / Charger  | Charging point hardware fault or power supply failure.            | Critical | Fault code received or power failure detected.                                          |
| **INC-HW-02**   | Hardware / Sensor   | Parking slot sensor failure or state mismatch.                    | Medium   | Sensor signal lost or state conflict $> 5$ mins.                                        |
| **INC-CAP-01**  | Capacity / Parking  | Hub reaches $100\%$ parking capacity, blocking vehicle returns.   | High     | Occupied slot counter equals total Hub capacity.                                        |
| **INC-CAP-02**  | Capacity / Vehicle  | High vehicle deficit at critical locations (e.g., Metro Station). | Medium   | Available rental vehicle count $< 2$ units at Hub.                                      |
| **INC-BAT-01**  | Vehicle / Battery   | Vehicle battery drops below the low battery threshold.            | High     | Telemetry reports battery level $\le \text{LOW\_BATTERY\_THRESHOLD}$ (default: $15\%$). |
| **INC-COMM-01** | Network / Telemetry | Loss of telemetry stream from a Mobility Hub gateway.             | Critical | No telemetry received from Hub for $> 30$ seconds.                                      |
| **INC-USR-01**  | User / Operational  | Vehicle rental overdue beyond grace period without extension.     | Low      | Active rental duration exceeds reserved time by $> 60$ mins.                            |

---

## 4. Final Escalation Business Rules (BRs)

| Rule ID | Rule Name | Trigger Condition | System Action | Traceability |
|---|---|---|---|---|
| **BR-M5-01** | Capacity Warning Threshold | Parking space occupancy reaches $\ge 90\%$ at any Hub. | Transition Hub status to `WARNING` via `core.set_hub_status()`; render warning badge on Operator Dashboard. | `FR-08.3`, `NFR-01`, `NFR-20` |
| **BR-M5-02** | Critical Capacity Overflow | Parking space occupancy reaches $100\%$ (`INC-CAP-01`). | Transition Hub status to `CRITICAL` via `core.set_hub_status()`; temporarily block new return reservations for this Hub; trigger alert for M4 vehicle dispatching. | `FR-08.3`, `FR-09.1`, `FR-10.6`, `BR-M1-02` |
| **BR-M5-03** | Charger Fault Isolation | Hardware fault code or power cut reported (`INC-HW-01`). | Immediately cut electrical relay; set ChargingPoint state to `OUT_OF_SERVICE`; generate critical incident ticket; notify M3 (`UC-M3-08`) to reschedule interrupted charging sessions. | `FR-09.1`, `FR-09.3`, `BR-M3-02`, `NFR-10` |
| **BR-M5-04** | Unacknowledged Escalation | Ticket with severity `HIGH` or `CRITICAL` remains in status `OPEN` for $> 5$ minutes (300 s) without operator acknowledgement. | Automatically update ticket status from `OPEN` to `ESCALATED`; log `escalated_at` timestamp; dispatch high-priority notification to Duty Supervisor. | `FR-09.2`, `FR-09.4`, `NFR-25` |
| **BR-M5-05** | Low Battery Lockout | Vehicle telemetry reports battery $\le \text{LOW\_BATTERY\_THRESHOLD}$ ($15\%$). | Automatically remove vehicle from active student rental pool; trigger low-battery incident `INC-BAT-01`; push vehicle to low-battery override priority queue in M3 (`BR-M3-03`). | `FR-09.3`, `BR-M3-03`, `BR-M1-03` |

---

## 5. Use-Case Tables for FR-08 and FR-09

### Use Case 1: UC-M5-01 — Monitor Hub Network Status

| Component             | Description |
| :-------------------- | :--- |
| **Use Case ID**       | `UC-M5-01` |
| **Use Case Name**     | Monitor Mobility Hub Network Status |
| **Primary Actor**     | System Operator |
| **Secondary Actor**   | IoT Sensor / Event Source (`src/iot_sim/` via `core`) |
| **Preconditions**     | Operator is authenticated with operator credentials (`A-06`). `core` state management engine is active. |
| **Main Flow**         | 1. Operator opens the Real-Time Monitoring Dashboard.<br>2. System fetches current network state and telemetry streams from `core`.<br>3. System computes utilization metrics and renders an interactive map/cards of all 10 Hubs with status indicators (`ACTIVE`, `WARNING`, `CRITICAL`).<br>4. Operator selects a specific Hub (e.g., "H01 - Metro") to view granular resource details.<br>5. System displays individual vehicle battery levels, charging port states, and active warnings.<br>6. Operator reviews information and navigates to dispatch or incident queues as needed. |
| **Alternative Flows** | **A1. Telemetry Data Stale/Interrupted:** If telemetry data from a Hub is delayed $> 30$ seconds, the system displays a "STALE DATA" warning icon and creates an `INC-COMM-01` ticket.<br>**A2. Capacity Warning ($\ge 90\%$):** System renders amber badge per `BR-M5-01`.<br>**A3. Full Capacity ($100\%$):** System renders red pulsing badge per `BR-M5-02`. |
| **Postconditions**    | Operator possesses an accurate, real-time overview of network health without mutating underlying operational data. |
| **Trace**             | **FRs:** `FR-08.1`, `FR-08.2`, `FR-08.3`, `FR-08.4` <br> **BRs:** `BR-M5-01`, `BR-M5-02` |

---

### Use Case 2: UC-M5-02 — Handle Operational Incident

| Component             | Description |
| :-------------------- | :--- |
| **Use Case ID**       | `UC-M5-02` |
| **Use Case Name**     | Process and Resolve Operational Incident |
| **Primary Actor**     | System Operator |
| **Secondary Actors**  | Field Technician, Duty Supervisor |
| **Preconditions**     | An operational anomaly (`INC-*`) has been detected or reported. |
| **Main Flow**         | 1. System detects anomaly, classifies severity, instantiates ticket (`Status = OPEN`), and starts 5-minute escalation timer.<br>2. System immediately executes automated safety interlocks (`BR-M5-03`, `BR-M5-05`).<br>3. System pushes alert to operator active work queue.<br>4. Operator selects ticket to review diagnostic context (`hub_id`, `entity_id`, error code, timestamp).<br>5. Operator clicks "Acknowledge" $\rightarrow$ Ticket transitions to `IN_PROGRESS` (cancelling 5-minute escalation timer).<br>6. Operator executes remote soft-reset command.<br>7. System validates that telemetry returns healthy state.<br>8. System restores resource operational state in `core` (`Available`).<br>9. Operator enters resolution notes; system marks ticket `RESOLVED`, then `CLOSED`. |
| **Alternative Flows** | **A1. Remote Reset Fails:** Operator assigns ticket to on-site Field Technician. Technician repairs hardware, runs diagnostic self-test, and notifies Operator.<br>**A2. Escalation Timeout ($> 5$ mins):** Operator does not acknowledge ticket within 5 minutes. System applies `BR-M5-04`, transitioning status to `ESCALATED` and notifying Duty Supervisor. |
| **Postconditions**    | Incident resolved, affected resource returned to service in `core`, full lifecycle committed to `TicketAuditLog` (`NFR-25`). |
| **Trace**             | **FRs:** `FR-09.1`, `FR-09.2`, `FR-09.3`, `FR-09.4` <br> **BRs:** `BR-M5-03`, `BR-M5-04`, `BR-M5-05` |
