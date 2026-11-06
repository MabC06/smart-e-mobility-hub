# 2. Requirements Analysis

> **Status:** Draft v1.0 · **Lead Consolidator:** M2 · **Contributors:** Whole Team  
> This document compiles the stakeholders, functional requirements (`FR-01` to `FR-12`), non-functional requirements (`NFR`), business rules (`BR`), and use-case specifications for the Smart E-Mobility Hub system.

---

## 2.1 Stakeholders and System Actors

*(Consolidated by M2 from module specifications)*

---

## 2.2 Functional Requirements

### 2.2.5 Monitoring & Incident Handling (Module M5 — Đỗ Hoàng Việt)

- **FR-08: System Monitoring**
  - **FR-08.1 (Real-Time Resource Tracking):** Ingests live telemetry streams from `iot_sim` covering vehicle states, battery percentages ($SoC\%$), space occupancy, and charger operational health.
  - **FR-08.2 (Utilization & Metrics Computation):** Computes real-time capacity ratios (parking occupancy %, charger utilization %) and fleet availability metrics per Hub.
  - **FR-08.3 (Capacity Warning & Alerting):** Automatically flags Hubs approaching or exceeding warning thresholds ($\ge 90\%$) and raises visual alerts on the Operator Dashboard.
  - **FR-08.4 (Network State Synchronization):** Evaluates Hub operational health and records state changes into the core domain store using `core.set_hub_status()`.

- **FR-09: Operational Incident Handling**
  - **FR-09.1 (Automated Incident Detection):** Identifies equipment malfunctions, telemetry timeouts, and resource capacity overflows from error codes and sensor signals.
  - **FR-09.2 (Classification & Ticket Instantiation):** Maps incidents to standardized taxonomy codes (`INC-HW-01`, `INC-CAP-01`, `INC-BAT-01`, etc.), assesses severity (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), and creates tickets with status `OPEN`.
  - **FR-09.3 (Automated Safety Interlocks):** Executes immediate protective interlocks (cuts power to faulty charging sockets, locks out depleted vehicles $\le 15\%$ from the rental pool).
  - **FR-09.4 (Incident Lifecycle Tracking):** Manages ticket transitions through `OPEN` $\rightarrow$ `IN_PROGRESS` $\rightarrow$ `ESCALATED` $\rightarrow$ `RESOLVED` $\rightarrow$ `CLOSED` with complete audit trail logging (`NFR-25`).

---

## 2.3 Non-Functional Requirements

*(Consolidated by M1 in `docs/requirements/nfr.md`)*

---

## 2.4 Business Rules & Constraints

### 2.4.5 Monitoring & Escalation Rules (Module M5)

- **`BR-M5-01` (Capacity Warning Threshold):** When a Hub's parking occupancy reaches $\ge 90\%$, the system sets the Hub status to `WARNING` and dispatches a notification to the operator console.  
  *Trace: FR-08.3, NFR-01, NFR-20*
- **`BR-M5-02` (Critical Capacity Overflow):** When a Hub reaches $100\%$ capacity (`INC-CAP-01`), the system sets Hub status to `CRITICAL`, blocks incoming return bookings, and suggests nearby alternative Hubs.  
  *Trace: FR-08.3, FR-09.1, BR-M1-02*
- **`BR-M5-03` (Charger Fault Isolation):** Upon detecting a charger electrical or hardware fault (`INC-HW-01`), the system immediately trips the socket relay, sets port state to `OUT_OF_SERVICE`, generates a critical ticket, and notifies M3 (`UC-M3-08`) to reassign interrupted charging sessions.  
  *Trace: FR-09.1, FR-09.3, BR-M3-02, NFR-10*
- **`BR-M5-04` (Unacknowledged Incident Escalation):** If an incident with severity `HIGH` or `CRITICAL` remains unacknowledged (`Status = OPEN`) by an operator for $> 5$ minutes, the system automatically transitions the ticket to `ESCALATED` and alerts the Duty Supervisor.  
  *Trace: FR-09.2, FR-09.4, NFR-25*
- **`BR-M5-05` (Low Battery Lockout):** Any vehicle reporting battery level $\le 15\%$ is immediately removed from the active rental pool and given top priority in the smart charging queue.  
  *Trace: FR-09.3, BR-M3-03, BR-M1-03*

---

## 2.5 Use-Case Modeling

### 2.5.5 Module M5 Use Cases

#### UC-M5-01: Monitor Mobility Hub Network Status
- **Actor:** System Operator (Primary), IoT Sensor (Secondary)
- **Description:** Allows operators to oversee network-wide resource utilization, inspect granular Hub metrics, and monitor capacity alerts.
- **Trace:** `FR-08.1`, `FR-08.2`, `FR-08.3`, `FR-08.4`; `BR-M5-01`, `BR-M5-02`

#### UC-M5-02: Process and Resolve Operational Incident
- **Actor:** System Operator (Primary), Duty Supervisor, Field Technician
- **Description:** Manages the full incident lifecycle from automated detection and safety isolation to operator triage, remote soft-reset or technician dispatch, and verified ticket closure.
- **Trace:** `FR-09.1`, `FR-09.2`, `FR-09.3`, `FR-09.4`; `BR-M5-03`, `BR-M5-04`, `BR-M5-05`

