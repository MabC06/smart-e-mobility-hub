# Module M3: Charging Request & Smart Scheduling — Requirements & Business Rules

**Owner:** Võ Thanh An (M3)

---

## 1. Functional Requirements (FR)

### FR-06: Charging Request & Scheduling (Student Rental Fleet)

- **FR-06.1 – Immediate Charging Request:** The system shall allow students to submit an immediate charging request for a rental electric vehicle currently in use or returned at a Mobility Hub, initiating an instant check for available charging ports.
- **FR-06.2 – Future Charging Session Scheduling:** The system shall enable students to schedule a future charging session by selecting a target Mobility Hub, specific time slot, and estimated duration based on upcoming travel needs.
- **FR-06.3 – Charging Reservation Modification & Cancellation:** The system shall allow students to modify or cancel their active charging reservations or scheduled sessions up to a defined time threshold before the slot starts.

### FR-07: Private Electric Vehicle Charging Support

- **FR-07.M3.1 – Private Electric Vehicle Registration & Parameter Validation:** The system shall support private electric vehicle owners in registering their vehicle specifications (battery capacity, connector type, current state of charge) to ensure compatibility with Hub charging infrastructure.
- **FR-07.M3.2 – Private Electric Vehicle Charging Slot Reservation:** The system shall enable private electric vehicle users to reserve dedicated charging slots at selected Mobility Hubs in advance, factoring in parking and power capacity constraints.

### FR-11: Charging Priority & Schedule Coordination

- **FR-11.M3.1 – Dynamic Priority Computation:** The system shall automatically compute real-time priority scores for all vehicles in the charging queue based on state of charge urgency and proximity to scheduled trip usage.
- **FR-11.M3.2 – Automated Smart Schedule Optimization:** The system shall dynamically generate, adjust, and optimize charging schedules across all Hubs to prevent power overload, reduce peak-hour congestion, and minimize vehicle waiting times.
- **FR-11.M3.3 – Conflict Resolution & Re-queueing:** The system shall automatically detect resource conflicts or equipment failures (e.g., port breakdown) and reassign or re-queue affected vehicles to alternative ports or optimal time slots.

---

## 2. Use Cases

### Charging Requests & Slot Scheduling

- **UC-M3-01 – Request Immediate Charging:**
  - **Primary Actor:** Student
  - **Flow Summary:** The student selects an available charging port at a Hub for immediate plugin. The system validates vehicle connection status, locks the port, and starts the charging session.
  - **Trace:** FR-06.1; BR-M3-01
- **UC-M3-02 – Schedule Future Charging:**
  - **Primary Actor:** Student
  - **Flow Summary:** The student picks a future time window and Hub for charging. The system checks port availability, confirms the reservation, and places the session into the queue.
  - **Trace:** FR-06.2; BR-M3-01
- **UC-M3-03 – Cancel / Modify Charging Schedule:**
  - **Primary Actor:** Student
  - **Flow Summary:** The student accesses their active or scheduled charging list, updates the time slot or cancels the booking, freeing up the port for other users.
  - **Trace:** FR-06.3

### Private Electric Vehicle Services

- **UC-M3-04 – Register Private Electric Vehicle Profile:**
  - **Primary Actor:** Private Electric Vehicle Owner
  - **Flow Summary:** The student inputs private vehicle specs (battery size, connector type). The system saves the profile for future charging reservations.
  - **Trace:** FR-07.M3.1
- **UC-M3-05 – Reserve Private Electric Vehicle Charging Slot:**
  - **Primary Actor:** Private Electric Vehicle Owner
  - **Flow Summary:** The student selects a private electric vehicle charging slot at a target Hub. The system validates compatibility and confirms the advance reservation.
  - **Trace:** FR-07.M3.2; BR-M3-01

### Smart Priority & Conflict Scheduling

- **UC-M3-06 – Compute Charging Priority Queue:**
  - **Primary Actor:** System Scheduler / Operator
  - **Flow Summary:** The background service continuously calculates priority scores based on low battery levels and imminent reservations, sorting the active charging queue.
  - **Trace:** FR-11.M3.1; BR-M3-03
- **UC-M3-07 – Execute Automated Smart Scheduling:**
  - **Primary Actor:** System Scheduler / Operator
  - **Flow Summary:** The system maps prioritized vehicles to available charging ports, generating an optimized charging schedule for the network.
  - **Trace:** FR-11.M3.2; BR-M3-03
- **UC-M3-08 – Handle Charging Point Failure & Schedule Conflicts:**
  - **Primary Actor:** System Scheduler / Operator
  - **Flow Summary:** When a charging point fails or a conflict occurs, the system reassigns the session to another available port within the same Hub or re-queues the vehicle. If no free port is available at the current Hub, the system delegates to M4's alternative lookup step (`UC-M4-07`) to find a suitable nearby Hub.
  - **Trace:** FR-11.M3.3; BR-M3-02

---

## 3. Business Rules (BR)

### BR-M3-01: Charging-Point Capacity & Availability Limits

- **Trace:** FR-06.1, FR-06.2, FR-07.M3.2
- **Rule Statement:** A Mobility Hub can only allocate active charging points up to its physical maximum capacity (`max_charging_ports`).
- **Validation & Constraints:**
  1. A charging request must be rejected or placed in a waiting queue if all charging ports at the requested Mobility Hub are fully occupied or reserved for the requested time window.
  2. Charging ports marked with status `OUT_OF_SERVICE` or under maintenance are strictly excluded from allocation.

### BR-M3-02: Charging Schedule Conflict Resolution & Overlap Prevention

- **Trace:** FR-11.M3.3
- **Rule Statement:** A single charging port cannot be assigned to multiple vehicles simultaneously during overlapping time intervals.
- **Validation & Constraints:**
  1. A proposed charging schedule for a vehicle at a specific port must not overlap with any existing confirmed reservation or active charging session on that port.
  2. If a time overlap or resource conflict occurs, the system shall prompt the user to select an alternative time slot or reassign the charging session to another available port within the same Hub or delegate to cross-Hub lookup (`UC-M4-07`).

### BR-M3-03: Smart Charging Priority Scoring & Dynamic Scheduling

- **Trace:** FR-11.M3.1, FR-11.M3.2; BR-M4-01
- **Rule Statement:** Charging priority within the charging class is dynamically calculated based on a combination of the vehicle's remaining battery level and its proximity to upcoming usage requirements or trip reservations. The order between groups (reservation, charging, rebalancing) is decided by BR-M4-01, and BR-M4-01 uses this rule for its charging levels (4–6).
- **Priority Logic & Conditions:**
  - **Battery Urgency Factor:** Vehicles with lower current state of charge percentages receive higher priority weights to ensure depleted vehicles get serviced promptly.
  - **Schedule Proximity Factor:** Vehicles linked to upcoming student trip reservations within a close time window are prioritized to prevent travel disruption.
  - **Low Battery Override:** Vehicles with a battery level at or below the threshold (LOW_BATTERY_THRESHOLD = 15%) receive a high-priority override flag, granting them immediate access to the next available charging port regardless of standard queue order.
