# FR-12: What-if Simulation & Coordination Design
**Owner:** M6 – Thân Ngô Tuấn  
**Phase:** Phase 0 — Requirements Analysis  
**Status:** Draft v1 — ready for review

---

## 1. Functional Requirements (FR-12 Specifications)

- **FR-12.1 – State Snapshot & Isolation:**
  - The system shall capture an in-memory snapshot of operational entities (Hubs, Vehicles, Charging Points, Parking Spaces) from the `core` domain (M1).
  - All simulation execution shall run in a strictly isolated sandbox environment, leaving the live operational state completely unaffected.

- **FR-12.2 – Scenario Configuration:**
  - The system shall allow operators to select from 5 standard predefined scenarios or configure custom parameters (duration, surge multiplier, target hubs, failed units).

- **FR-12.3 – Discrete-Event State Evolution:**
  - The system shall simulate system state transitions over discrete time steps across a configured time window (e.g., 15-minute steps over 1 to 6 hours).

- **FR-12.4 – Impact Assessment & Metrics Calculation:**
  - The system shall compute operational impact indicators:
    - Vehicle Shortage Rate (unmet rental requests per hub)
    - Hub Overflow / Return Rejection Rate (parking space deficit)
    - Average Charging Queue Time & Station Utilization
    - Fleet Battery Depletion Rate (vehicles with SoC < 20%)
    - Total Unfulfilled Trip Request Count

- **FR-12.5 – Coordination Recommendation Generation:**
  - The system shall automatically evaluate simulation outcomes and synthesize actionable coordination proposals:
    - Fleet Rebalancing / Dispatch orders (transferred to M4)
    - Suggest reserving or returning at a neighbouring Hub (transferred to M2/M4)
    - Charging queue shifting and throttle policies (transferred to M3)

- **FR-12.6 – Comparative Analytics & Output:**
  - The system shall present comparative metrics between the Baseline (do-nothing / current policy) and the Mitigated Scenario (recommended coordination plan).

---

## 2. List of 5 Standard Scenarios & Configurable Inputs

### Scenario 1: Peak-Hour Demand Surge
- **Description:** Sudden surge in vehicle rental requests during peak class dismissal or university events at VNU-HCM.
- **Configurable Inputs:**
  - `target_hub_ids` (List[String]): List of hubs experiencing demand surge.
  - `demand_multiplier` (Float): Scaling factor (e.g., 1.5x, 2.0x, 3.0x).
  - `duration_minutes` (Integer): Surge duration (default: 60 minutes).
  - `destination_distribution` (Map[HubId, Float]): Probability split of return destinations.

### Scenario 2: Hub at Capacity / Parking Space Overflow
- **Description:** High inflow of incoming vehicles at a destination hub exceeding available parking spaces.
- **Configurable Inputs:**
  - `target_hub_id` (String): Target destination hub.
  - `incoming_return_rate` (Integer): Expected vehicle return arrivals per 10 minutes.
  - `buffer_capacity_threshold` (Float): Warning threshold (default: 90%).
  - `neighboring_hub_radius_km` (Float): Search radius for alternative drop-off locations.

### Scenario 3: Fleet Charging Demand Surge
- **Description:** Rapid battery depletion across multiple operational hubs requiring simultaneous charging sessions.
- **Configurable Inputs:**
  - `soc_threshold_trigger` (Float): State-of-Charge threshold triggering charging (default: < 20%).
  - `initial_drained_vehicle_count` (Integer): Number of low-battery vehicles per hub.
  - `charging_speed_kw` (Float): Charging rate per charging point.
  - `max_queue_size_per_station` (Integer): Warning threshold for charging queues.

### Scenario 4: Charging Point Hardware Failure
- **Description:** Hardware or power breakdown causing one or more charging stations to become inoperative.
- **Configurable Inputs:**
  - `failed_charging_point_ids` (List[String]): Offline charging point identifiers.
  - `failure_start_time_offset` (Integer): Onset time offset in minutes.
  - `estimated_mttr_minutes` (Integer): Mean Time To Repair / offline duration.
  - `charging_priority_policy` (Enum): `FLEET_FIRST` | `FCFS`.

### Scenario 5: Vehicle Imbalance / Local Shortage
- **Description:** Asymmetric vehicle distribution (surplus at residential dormitories, severe deficit at academic lecture halls).
- **Configurable Inputs:**
  - `source_hub_ids` (List[String]): Hubs with excess idle vehicles.
  - `destination_hub_ids` (List[String]): Hubs facing severe shortages.
  - `dispatch_truck_capacity` (Integer): Max capacity per relocation batch.
  - `dispatch_transit_delay_minutes` (Integer): Lead time required for vehicle relocation.

---

## 3. Use-Case Table for FR-12

| Field | Specification |
| :--- | :--- |
| **Use Case ID** | **UC-M6-01** |
| **Use Case Name** | Run What-if Simulation and Generate Coordination Recommendations |
| **Trace** | FR-12, NFR-05, NFR-12, NFR-13; BR-M6-01, BR-M6-02, BR-M6-03 |
| **Actor** | Operator |
| **Description** | Operator configures and executes a simulation scenario on an isolated state snapshot to predict bottlenecks and obtain actionable coordination recommendations. |
| **Preconditions** | 1. Operator is authenticated with operator privileges.<br>2. Core domain service provides an accessible point-in-time state snapshot. |
| **Postconditions** | 1. Simulation metrics and impact analyses are stored in the temporary session.<br>2. Actionable mitigation recommendations are generated.<br>3. Production/real-time operational state remains untouched. |
| **Main Flow** | 1. Operator navigates to the **What-if Simulation** dashboard.<br>2. System clones a point-in-time snapshot from Core domain into sandbox memory.<br>3. Operator selects one of the 5 standard scenarios (or compound scenario).<br>4. Operator customizes the scenario parameters (duration, multiplier, target hubs).<br>5. Operator clicks **Run Simulation**.<br>6. Simulation engine executes state transitions over discrete time steps.<br>7. System evaluates performance indicators (shortage rate, overflow rate, queue times).<br>8. Engine synthesizes coordination recommendations (dispatching, rerouting, charging shift).<br>9. System displays comparative dashboard (Baseline vs. Mitigated).<br>10. Operator reviews and exports or saves the simulation session. |
| **Alternative Flows** | **3a. Custom Scenario:** Operator combines multiple scenarios (e.g., Demand Surge + Station Failure).<br>**10a. Dispatch Trigger:** Operator approves recommendations; system formats and forwards orders to M4 (Dispatch) / M5 (Incident). |
| **Exception Flows** | **2a. Snapshot Unavailable:** Core domain unreachable; system alerts operator and aborts session.<br>**4a. Invalid Input Parameter:** Input outside bounds (e.g., multiplier $\le 0$); system displays inline validation error and prevents execution.<br>**6a. Simulation Timeout:** Computation exceeds configured threshold ($> 60$s by default, configurable for larger datasets); system safely terminates job and reports execution error. |
| **Business Rules** | • **BR-M6-01 (Strict Isolation):** Read-only snapshot access; zero write-back to production database. (Trace: FR-12.1, NFR-12)<br>• **BR-M6-02 (Determinism):** Identical seeds and parameters must yield reproducible outcomes. (Trace: FR-12.3, NFR-13)<br>• **BR-M6-03 (Feasibility Check):** Generated dispatch recommendations must respect truck capacities and physical transit delays. (Trace: FR-12.5, NFR-05) |
