# 7. Simulation Design

## 7.1. Overview

The M6 --- What-if Simulation & Coordination module enables system
operators to evaluate hypothetical operational situations before making
operational decisions.

The module simulates changes in vehicle demand, parking occupancy,
charging workload, charging-point availability, and vehicle distribution
across Mobility Hubs in the VNU-HCM Urban Area.

M6 provides simulation results, operational impact metrics, and
coordination recommendations to support operator decision-making.

All simulation operations are performed in an isolated environment. The
simulation does not directly modify the real operational state of the
system.

The detailed technical specification is documented in [M6 What-if
Simulation & Coordination Design
Specification](../design/simulation/m6-simulation-design.md).

## 7.2. Simulation Scenarios

M6 supports five standard simulation scenarios:

### SC-01. Peak-Hour Demand Surge

This scenario evaluates whether the available vehicle fleet can satisfy
a sudden increase in student rental demand.

-   Increases rental demand at selected Mobility Hubs.
-   Uses a configurable demand multiplier and simulation duration.
-   Records fulfilled and unmet rental requests.
-   Identifies hubs experiencing vehicle shortages and hubs with
    eligible surplus vehicles.

**Expected outcome:** Identify vehicle shortages and recommend feasible
vehicle redistribution from surplus hubs to shortage hubs.

### SC-02. Hub at Capacity

This scenario evaluates parking-capacity risks and rejected vehicle
returns.

-   Simulates incoming vehicle return attempts.
-   Monitors parking occupancy against the configured warning threshold.
-   Records accepted and rejected return attempts.
-   Identifies alternative hubs with available parking capacity.

**Expected outcome:** Recommend alternative return hubs or feasible
vehicle redistribution to reduce parking congestion.

### SC-03. Charging Surge

This scenario evaluates charging congestion, queue waiting time, and
low-battery risks.

-   Generates additional charging demand.
-   Identifies vehicles requiring charging.
-   Assigns requests to compatible available charging points.
-   Monitors queue length, waiting time, and critical battery
    conditions.

**Expected outcome:** Recommend charging prioritization, rescheduling,
or redirection to alternative charging points.

### SC-04. Charging-Point Failure

This scenario evaluates the impact of charging-point failures on
charging capacity and vehicle readiness.

-   Simulates failures at selected charging points.
-   Prevents new charging sessions from starting at failed points.
-   Evaluates the impact on ongoing charging sessions.
-   Considers recovery and reassignment to functioning charging points.

**Expected outcome:** Recommend alternative charging assignments and
identify vehicles at risk of charging delays.

### SC-05. Vehicle Imbalance

This scenario evaluates vehicle shortages and surpluses across Mobility
Hubs.

-   Identifies hubs with surplus and deficit vehicles.
-   Determines feasible source-destination pairs.
-   Considers vehicle eligibility, parking capacity, source reserves,
    and transportation constraints.
-   Simulates vehicle transfers and their completion times.

**Expected outcome:** Recommend feasible vehicle redistribution to
improve fleet balance without creating additional operational shortages.

## 7.3. Impact Metrics

M6 calculates four primary metrics to evaluate operational conditions.

### 1. Vehicle Shortage Rate

Measures the percentage of valid rental requests that cannot be
fulfilled because suitable vehicles are unavailable.

\[ S_r(h)=`\frac{U_h}{R_h}`{=tex}`\times100`{=tex}% \]

Where: - (U_h): Number of unmet valid rental requests at hub (h). -
(R_h): Total valid rental requests at hub (h).

A lower shortage rate indicates better demand fulfillment. If there are
no valid requests, the result is reported as N/A.

### 2. Hub Overflow / Return Rejection Rate

Measures the percentage of valid vehicle return attempts rejected
because the destination hub lacks available parking capacity.

\[ O_r(h)=`\frac{J_h}{A_h}`{=tex}`\times100`{=tex}% \]

Where: - (J_h): Number of rejected valid return attempts. - (A_h): Total
valid return attempts.

A lower rejection rate indicates better parking-capacity availability.
If there are no return attempts, the result is reported as N/A.

### 3. Average Charging Queue Waiting Time

Measures the average time between a charging request and the start of
its charging session.

\[ W\_{`\mathrm{avg}`{=tex}}= `\frac{1}{|V_s|}`{=tex}
`\sum`{=tex}*{v`\in `{=tex}V_s}
(t*{`\mathrm{start}`{=tex}}(v)-t\_{`\mathrm{request}`{=tex}}(v)) \]

Where: - (V_s): Set of vehicles whose charging sessions start during the
measurement period. - (t\_{`\mathrm{request}`{=tex}}(v)): Time when
vehicle (v) requests charging. - (t\_{`\mathrm{start}`{=tex}}(v)): Time
when its charging session starts.

The result is expressed in minutes. If no charging session starts during
the measurement period, the result is reported as N/A. Requests still
waiting at the end of the simulation are reported separately.

### 4. Critical Battery Depletion Count

Counts vehicles whose battery percentage is at or below the configured
critical threshold while not charging at the end of the simulation.

\[ N\_{`\mathrm{crit}`{=tex}}= `\left`{=tex}\|`\left`{=tex}{
v`\in `{=tex}V: battery_pct(v)`\leq `{=tex}LOW_BATTERY_THRESHOLD
`\land `{=tex}State(v)`\neq`{=tex}`\mathrm{Charging}`{=tex}
`\right`{=tex}}`\right`{=tex}\| \]

Where: - (V): Set of vehicles included in the simulation. -
(battery_pct(v)): Battery percentage of vehicle (v), represented on a
0--100 scale. - (LOW_BATTERY_THRESHOLD): Value obtained from Core
configuration through `get_config()`. Core defines this value as 15.0
(%). - (State(v)): Simulated vehicle state at the end of the measurement
period.

M6 must read the threshold from Core configuration at runtime rather
than defining an independent local constant.

### Baseline and Mitigated Comparison

M6 compares baseline results with mitigated simulation results when
feasible mitigation actions are available.

The comparison includes: - Baseline metric values. - Mitigated metric
values. - Absolute changes. - Interpretation of improvements or
deterioration.

For metrics where lower values are better:

\[
`\Delta `{=tex}M=M\_{`\mathrm{baseline}`{=tex}}-M\_{`\mathrm{mitigated}`{=tex}}
\]

A positive value indicates improvement.

## 7.4. Coordination Recommendation Rules

M6 uses explainable, rule-based logic to generate coordination
recommendations based on simulation results.

The recommendation process consists of: 1. Identifying operational
problems. 2. Generating candidate coordination actions. 3. Checking
resource availability and operational constraints. 4. Evaluating
feasible actions through a separate mitigated simulation. 5. Ranking
recommendations by operational priority. 6. Returning recommendations
with supporting metrics and explanations.

Five primary recommendation rules are defined:

### R1. Vehicle Redistribution

**Trigger:** A hub experiences unmet rental demand while another hub has
eligible surplus vehicles.

**Action:** Recommend transferring vehicles from surplus hubs to
shortage hubs.

**Constraints:** - Preserve the required source-hub vehicle reserve. -
Respect destination parking capacity. - Transfer only eligible
vehicles. - Respect transportation capacity and travel time where
modeled.

**Target module:** M4 --- Allocation & Dispatching.

### R2. Hub Capacity Relief

**Trigger:** Hub occupancy reaches the configured warning threshold.

**Action:** Recommend alternative hubs for incoming vehicle returns or
feasible vehicle redistribution.

**Constraints:** - Alternative hubs must have sufficient parking
capacity. - Operational eligibility must be checked. - Geographic
proximity alone is insufficient.

**Target module:** M2 --- Reservation & Trip, or M4 --- Allocation &
Dispatching, depending on the proposed action.

### R3. Charging Congestion

**Trigger:** Charging queue length exceeds the configured threshold or
available charging capacity becomes insufficient.

**Action:** Recommend charging request reassignment, prioritization,
rescheduling, or redirection to alternative charging points.

**Constraints:** - Respect charging-point availability and power
limits. - Respect vehicle and charging-point compatibility. - Consider
upcoming reservation requirements.

**Target module:** M3 --- Charging & Smart Scheduling.

### R4. Charging-Point Failure Recovery

**Trigger:** A charging-point failure causes charging sessions to become
unavailable, delayed, or infeasible.

**Action:** Recommend reassignment to functioning charging points and
prioritize vehicles required for upcoming trips.

**Constraints:** - Failed charging points must remain unavailable until
modeled recovery. - Alternative charging points must be compatible and
available. - Identify sessions at risk of delay.

**Target module:** M3 --- Charging & Smart Scheduling.

### R5. Fleet Balance Improvement

**Trigger:** Some hubs have surplus vehicles while other hubs experience
shortages relative to their target levels.

**Action:** Recommend feasible vehicle transfers between source and
destination hubs.

**Constraints:** - Respect vehicle eligibility. - Preserve source-hub
reserves. - Respect destination capacity. - Consider transportation and
transfer-time constraints.

**Target module:** M4 --- Allocation & Dispatching.

### Recommendation Priority

Recommendations are ranked according to the following priorities:

1.  Prevent operational constraint violations and protect critical
    vehicle readiness.
2.  Reduce unmet rental demand.
3.  Reduce parking-capacity problems.
4.  Reduce critical charging delays.
5.  Improve vehicle distribution.
6.  Minimize unnecessary transfers and operational changes.

All recommendations are advisory. Operator approval is required before
submission, and the receiving operational module must revalidate the
request against the current real operational state.

## 7.5. Operational Snapshot Integration with M1 Core

M6 requires an initial operational snapshot to create an isolated
simulation environment.

M1 --- Core remains the authoritative owner of the real operational
state and provides the snapshot through the `export_snapshot()`
interface.

The snapshot is obtained as an `OperationalSnapshot` object returned by
`core.snapshots.export_snapshot()`. M6 consumes the returned object
without importing internal types from `core.domain`.

The returned snapshot exposes: - `version` - `to_dict()` -
`to_repository()`

The snapshot contains operational information such as:

-   Mobility Hub identifiers, names, and parking capacities.
-   Vehicle identifiers, locations, states, and battery percentages.
-   Charging-point identifiers, statuses, and power ratings.

The snapshot uses Core field names, including: - `parking_capacity` for
hub capacity. - `vehicle_type` for vehicle type. - `battery_pct` for
vehicle battery percentage. - `charging_point_id` for charging-point
identifiers. - `power_rate_kw` for charging-point power ratings.

Reservation demand and charging demand are obtained separately through
the `ReservationDemand` (M2) and `ChargingDemand` (M3) interfaces. They
are not embedded in the operational snapshot.

### Snapshot Processing Workflow

1.  M6 requests an operational snapshot from M1.
2.  M1 provides a consistent snapshot through `export_snapshot()`.
3.  M6 validates the snapshot identifier, timestamp, entity IDs,
    capacities, states, and relationships.
4.  M6 preserves the original snapshot as immutable input.
5.  M6 creates an isolated mutable simulation state.
6.  Separate baseline and mitigated states are created from the same
    initial snapshot when mitigation is applicable.
7.  Simulation results are returned as reports and recommendations
    without modifying the real operational state.

M6 must not directly modify Core state or bypass the responsible
operational modules.

## 7.6. Detailed Design Reference

This section provides a high-level overview of the M6 simulation design.

For detailed specifications, implementation considerations, mathematical
definitions, scenario parameters, simulation workflows, state-isolation
requirements, interface contracts, and testing strategies, refer to:

[**M6 What-if Simulation & Coordination Design
Specification**](../design/simulation/m6-simulation-design.md)

The detailed design document serves as the primary technical reference
for M6 implementation and integration.
