<!-- BEGIN M3: Charging & Smart Scheduling -->

# 02: Requirements Analysis

## Module M3 (Charging & Smart Scheduling)

> **Author:** Võ Thanh An (M3)  
> **Date:** 2026-11-06  
> **Status:** Phase 1 Draft for Integration Review

---

## 2.1 Problem Analysis & Operational Needs

The charging infrastructure at Mobility Hubs faces two primary engineering challenges: **operational disruptions caused by resource contention** and **the risk of local electrical grid overload** during peak hours. The requirements analysis for Module M3 addresses these technical bottlenecks through three core dimensions:

1. **User Demographics & Access Control (Fleet vs. Private):**
   Internal rental electric vehicles serving students require immediate, plug-and-play charging (`FR-06.1`) to optimize vehicle turnaround time. Conversely, private EV owners (`FR-07.M3`) demand guaranteed access and reserved power slots (`FR-07.M3.2`). Failing to separate these user models creates queuing congestion that disrupts fleet availability.

2. **Hardware Interoperability & Safety Interlocks:**
   Private EVs feature diverse connector standards (CCS2, Type 2), battery capacities, and maximum C-rates. Without a registration and parameter validation mechanism (`FR-07.M3.1`), connecting an incompatible vehicle risks equipment damage or circuit breaker trips. Parameter verification prior to energy transfer is therefore a mandatory system constraint.

3. **Grid Capacity Limits & Dynamic Scheduling Algorithms:**
   Traditional First-Come, First-Served (FCFS) queuing fails in EV charging environments: a vehicle at 80% SoC should not block a port required by a vehicle at 5% SoC needed for an upcoming trip. Consequently, requirements `FR-11.M3.1` and `FR-11.M3.2` replace FCFS with dynamic priority scoring.

---

## 2.2 Requirements Rationale & Structural Mapping

### 1. Session Control Requirements (`FR-06`, `FR-07`)

- **Risk of Omission:** Allowing users to occupy charging bays indefinitely without validation or time bounds leads to stalled sessions (fully charged vehicles remaining plugged in).
- **Analytical Resolution:** `FR-06.3` enforces strict reservation modification and cancellation thresholds, immediately releasing unused capacity back to the available Hub pool (`AVAILABLE`).

### 2. Planning & Conflict Resolution Requirements (`FR-11`)

- **Risk of Omission:** When a charging port faults (`FAULTED`), failing to trigger automated reassignment (`FR-11.M3.3`) stalls active sessions and breaks the downstream travel schedule.
- **Analytical Resolution:** A 3-tiered fault resolution cascade is established (local port reallocation $\rightarrow$ time-window shifting $\rightarrow$ cross-Hub routing via M4).

---

## 2.3 Requirements Traceability & Behavioral Mapping

Functional requirements are systematically mapped to the system's Use-Case architecture to ensure complete coverage:

![M3 Use-Case Diagram](../requirements/use-case-diagrams/uc-m3-charging.svg)

- **Traceability Matrix:**

| Requirement (FR) | Solved Technical Problem                                        | Mapped Use Case | Enforced Business Rule (BR)                         |
| :--------------- | :-------------------------------------------------------------- | :-------------- | :-------------------------------------------------- |
| **FR-06.1**      | Immediate session initialization for returned rental EVs.       | `UC-M3-01`      | `BR-M3-01` (Port availability verification)         |
| **FR-06.2**      | Mitigating peak-hour station congestion via advance scheduling. | `UC-M3-02`      | `BR-M3-01` (Future capacity reservation)            |
| **FR-06.3**      | Preventing power capacity waste when travel plans change.       | `UC-M3-03`      | N/A (Releasing allocated capacity)                  |
| **FR-07.M3.1**   | Preventing voltage and connector mismatch for private EVs.      | `UC-M3-04`      | N/A (Persisting hardware specs)                     |
| **FR-07.M3.2**   | Segmenting dedicated charging ports for private EV users.       | `UC-M3-05`      | `BR-M3-01` (Securing private bay allocation)        |
| **FR-11.M3.1**   | Overcoming FCFS limitations; prioritizing depleted batteries.   | `UC-M3-06`      | `BR-M3-03` (Dynamic priority scoring)               |
| **FR-11.M3.2**   | Preventing voltage sags and transformer overloads at Hubs.      | `UC-M3-07`      | `BR-M3-03` (Load regulation and schedule smoothing) |
| **FR-11.M3.3**   | Ensuring high availability during hardware point failures.      | `UC-M3-08`      | `BR-M3-02` (3-tier flexible reallocation)           |

---

## 2.4 Analysis of Business Rules Rationale

### BR-M3-01: Port Approval & Faulty Equipment Isolation

- **Analytical Rationale:** From an electrical safety standpoint, closing high-power relays when a charging bay reports thermal warnings or ground faults can cause severe equipment damage. `BR-M3-01` forces the system to isolate ports flagged as `OUT_OF_SERVICE` or `FAULTED` directly at the database query level, excluding them from scheduler allocation pools.

### BR-M3-02: Three-Tiered Conflict Resolution Strategy (Fallback Cascade)

- **Analytical Rationale:** Station overload cannot be resolved through outright service rejection. The fallback mechanism escalates operational costs progressively:
  1. _Local Port Swap (Zero transit cost):_ Reassigning to an idle port of matching rating within the same Hub.
  2. _Time Window Shift (Low operational impact):_ Adjusting the charging start time if the vehicle has no immediate departure requirement.
  3. _M4 Delegation (High cost - physical vehicle relocation):_ Invoking `UC-M4-07` to route the vehicle to an adjacent Hub when the current station reaches maximum capacity.

### BR-M3-03: Dynamic Priority Scoring & Low Battery Override

- **Analytical Rationale:** Priority weighting evaluates remaining State of Charge (% SoC) alongside proximity to scheduled trip departures.
- **Emergency Override Threshold:** The rule defines a critical threshold at $\text{SoC} \le 15\%$ (`LOW_BATTERY_THRESHOLD`). When battery levels drop below this boundary, deep discharge risks escalate sharply, triggering an immediate priority override flag that places the vehicle at the front of the active charging queue.

---

## 2.5 Quality Attribute Trade-offs

- **Performance vs. Complexity (NFR-04):** Recalculating queue rankings within **5 seconds** requires priority algorithms to maintain low computational complexity ($\mathcal{O}(N \log N)$), preventing database table lock contention during peak concurrent requests.
- **Safety vs. Availability (NFR-08/09):** Tripping high-voltage power relays within **100 ms** upon detecting electrical or thermal faults (`FAULTED`) may interrupt user charging sessions, but this is a mandatory trade-off to ensure absolute infrastructure and vehicle safety.
<!-- END M3: Charging & Smart Scheduling -->
