# M2 Phase 1 review handoff

> Owner: M2 - 2452620. Updated 2026-10-22. Design proposals require human review.

## Submission and deadlines

Branch: `docs/reservation-phase1-design`; [PR #11](https://github.com/MabC06/smart-e-mobility-hub/pull/11), target `develop`. Initial submission was commit `69312c2` on Oct 11. The branch is now synced with develop `57c064d`. This supersedes the original unexecuted Git handoff: the PR already exists. M7 (`sharkin206`) was requested as reviewer. No merge or human approval is claimed.

M2 own design is due **Oct 23**. Team design review is **Oct 25**. M1's open [timeline PR #15](https://github.com/MabC06/smart-e-mobility-hub/pull/15) places the final overview and updated actor list on Oct 25, after module diagrams arrive. No deadline hour is specified. The former five consolidated Phase 0 diagrams are replaced by module-owned diagrams plus M2's overview under that proposal and M1's PR feedback.

## What to review

- [Requirements baseline](../requirements/fr-02-05-07-reservation.md): FR acceptance criteria, 8 use cases, 16 business rules with upward Trace, parameters, dependency decisions and 13 planned verification scenarios.
- [Actor analysis](../requirements/stakeholder-actor-analysis.md): stakeholders, actor participation, M7 UI overlap, source SHAs and diagram coverage.
- [Draft overview](../requirements/use-case-diagrams/uc-overview.svg): seven goal groups; individual IDs remain in module documents. Available M2/M4 diagrams and M3/M5/M6 tables are the inputs.
- [Activity](../design/behavioral/reservation-activity-diagram.md), [sequence](../design/behavioral/reservation-sequence-diagram.md) and [state machine](../design/behavioral/reservation-state-machine.md): 8 behavioral diagrams plus 2 M2 use-case diagrams, with source/export pairs.
- [Requirements report](../report/02-requirements-analysis.md), [behavioral report](../report/05-behavioral-design.md) and [AI declaration](../ai-usage/2452620.md).

## Response to M1 review

| PR #11 feedback | Revision |
|---|---|
| Add FR/NFR Trace to BRs, no reverse UC list | All 16 BR rows have Trace; UC Trace lines use complete identifiers for M8 extraction |
| Shared FR-07 sub-IDs must be module-scoped | Retain one parking row; require FR-07.M2.n if later split, distinct from FR-07.M3.n |
| Actor analysis missing; diagram responsibility changed | Added actor analysis and draft uc-overview source/SVG; removed obsolete five-diagram gap wording |
| UC-M2/BR-M2 IDs are final, no flat mapping | Stable module-scoped IDs retained throughout; removed flat mapping and provisional-ID wording. D-011 decision-log status is untouched |

These revisions address the comments in documents. The reviewer determines acceptance; review threads are not automatically resolved.

## Dependency findings and M2 response

| Module | What was collected | Effect on M2 / remaining decision |
|---|---|---|
| M1 | CONTRIBUTING, D-011, Accepted D-012 and timeline PR #15 | Stable IDs; M3 owns charging failure, M4 cross-Hub lookup. Core API/class/Vehicle-state source remains absent; sequence messages are proposed ports |
| M3 | UC-M3-01..08, BR-M3-01..03, private profile, joint bay/charger requirements | One bay per charging vehicle and atomic claims; urgency is now <=15%, not the older <15%. Numeric policies require review |
| M4 | PR #16 allocation algorithm, interaction design and two UC sources | Atomic claims/read-only alternatives align. REBALANCE reservation conflicts with typed task-owned claims: no Student pickup or student Trip for dispatch. Preserve custody/destination protection after pickup even on timeout |
| M5 | UC-M5-01/02, BR-M5-01..05, incident/overdue requirements | Pool lockout <=15%, critical incident <=10%, overdue >due+60 min. Time/cancellation never removes actual occupancy |
| M6 | UC-M6-01, isolated simulation and metrics | Clone bookings/trips/claims/clock/results; recommendation application needs fresh operational checks. Analytics <20% differs from rental eligibility >=20% |
| M7 | Operator views and schema draft | Separate UI views from business UCs; flag stale UC-12 references. Due-time/calendar fields and typed claims need M1/M7 agreement |
| M8 | Current test-plan/traceability branch and naming convention | Upward traces and planned scenarios; no invented TC results or reverse FR/BR catalog |

Exact revisions and paths are in the actor analysis. The requirements' original Oct 11 source table remains historical evidence.

## Verification and remaining work

The Oct 11 package passed ten PlantUML renders, visual review and local link/ID checks. Oct 22 validation passed: 52 local Markdown links (including the new actor index), 16 BR Trace rows, 8 UC definitions and 11 SVG/source pairs. Visual checks covered all changed diagrams and the four-page Vietnamese PDF. PlantUML syntax checking covers eleven PlantUML sources including the overview, regenerated changed use-case exports, local links, SVG XML, 16 BR Trace rows, 8 UC definitions and whitespace. No application/unit/integration or concurrency tests are claimed: this is design documentation.

Before final cross-module sign-off on Oct 25: obtain M3/M5/M6 final diagrams, M4 SVG exports and M1 Core contract; reconcile the overview and agree dispatch-claim/custody interfaces. Current draft covers available evidence and does not claim these external deliverables exist.

## Personal reading checklist

- [ ] Read the Vietnamese PDF review, then parameter and dependency registers.
- [ ] Explain exact expiry, atomicity, retries and occupancy versus scheduled claims.
- [ ] Review distinct battery thresholds and the M4 dispatch disagreement.
- [ ] Confirm/revise numeric proposals with owners; update the AI log after personal review.
- [ ] Read reviewer feedback and attend the Oct 25 team design review.
