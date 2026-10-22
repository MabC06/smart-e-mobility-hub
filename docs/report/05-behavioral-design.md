# 3.3 Behavioral and Interaction Design

<!-- BEGIN M4: Resource Allocation & Dispatching -->
## M4 contribution - Resource Allocation & Dispatching

> Author: 2412466 Huỳnh Minh Nhật. Date: 2026-10-22. **Proposed for team review**.

### Design overview

The allocation module works in two steps. First it **plans** on a read-only snapshot: it finds Hubs that will run short of vehicles and Hubs with surplus, and proposes dispatch tasks. Planning is a pure function, so M6 can reuse it on a copy of the state. Then, after the operator approves a task, it **commits** through Core in one atomic unit of work: the vehicles and one destination space are held together as a system reservation (purpose `REBALANCE`) owned by M2, or nothing is held. Pick-up, return, cancel and failure each release or complete what was held.

Two further flows are read-only lookups called through Core: alternative Hubs for a reservation request (M2) and an alternative charging point for requests displaced when a Hub has no free port (M3, UC-M3-08, D-012). Competing requests are ordered by class level, then time, then ID (BR-M4-01), and the winner claims the resource atomically.

### UML diagram index

| Artifact | IDs and intent | Detailed source and discussion |
|---|---|---|
| Sequence | S1 plan; S2 approve or reject; S3 carry out or cancel; S4 alternative Hubs for M2; S5 alternative charging for M3 | [Sequence document](../design/behavioral/allocation-sequence-diagram.md) |
| Activity | A1 plan redistribution; A2 approve and execute; A3 settle competing requests | [Activity document](../design/behavioral/allocation-activity-diagram.md) |
| State machine | T1 DispatchTask life cycle with a complete transition table | [State document](../design/behavioral/allocation-state-machine.md) |

All eleven diagrams of this contribution (nine behavioral and two use-case diagrams) have editable `.puml` sources and generated `.svg` previews.

### Key design decisions

The algorithm was chosen among four approaches (threshold rules with greedy matching, min-cost flow, integer programming, reactive only). Threshold rules with greedy matching were chosen because they are fast, repeatable and explainable to an operator; the price is a plan that may not be globally optimal. The comparison, the formulas and a worked example on DS-STD Hubs are in the [algorithm design](../design/architecture/allocation-algorithm-design.md).

Allocation never writes state directly and never calls another module directly; every write and every read of another module's data goes through Core (D-003, NFR-22).

### Not decided yet

1. M1: public ports for the snapshot and for the demand of M2 and M3 (Core API spec v1).
2. M2: use of normal pick-up and return for a system reservation with purpose `REBALANCE`.
3. M3: request and answer shape of UC-M4-07.
4. M6: reuse of the pure planning function on a state copy.
<!-- END M4: Resource Allocation & Dispatching -->
