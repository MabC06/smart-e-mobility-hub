# Design Review Checklist — M8

> Use this checklist during Phase 1 design review and again before code freeze.  
> Reviewers: M4 for M8 test deliverables; M7 for IoT simulator output/ERD alignment.

## A. Requirements and traceability

- [ ] Every design element maps to an active FR, NFR, BR, UC, or an explicit project decision.
- [ ] No withdrawn NFR is treated as an acceptance criterion.
- [ ] IDs are stable and follow `CONTRIBUTING.md` section 5.
- [ ] No duplicate or orphan FR/BR/UC/TC IDs.
- [ ] Each test case states `Verifies:` and `Technique:`.
- [ ] Expected results are observable and measurable.

## B. Architecture and module boundaries

- [ ] Modules call Core only through the documented public interface.
- [ ] No feature module imports another feature module's internals.
- [ ] No module writes Core-owned operational tables directly.
- [ ] Shared provider Protocols and DTOs are defined in `core.providers` by the port owner and reviewed by callers (D-020).
- [ ] Transactions spanning Core and module records use `core.unit_of_work()`.
- [ ] API and event names match `core-api-spec.md` v1.1.

## C. Data model and DS-STD

- [ ] 10 Hubs, 400 spaces, 61 charging points, 250 fleet vehicles.
- [ ] 1,000 students, 5 operators, 100 private EVs.
- [ ] Fleet battery bands and vehicle-type distributions match `reference-dataset.md`.
- [ ] Each charging point maps to its charging-bay parking space.
- [ ] Fleet vehicles are placed in non-charging spaces before bays.
- [ ] Private vehicles have an existing owner and connector type.
- [ ] IDs are unique, stable, and deterministic from the seed.
- [ ] No real passwords, tokens, or personal data are included.

## D. IoT event contract

- [ ] Event type is one of `BATTERY_LEVEL`, `SPACE_OCCUPIED`, `SPACE_FREED`, `CHARGER_FAULT`, `VEHICLE_FAULT`, `HEARTBEAT`.
- [ ] `event_id`, `source`, `entity_id`, and timezone-aware `at` are populated.
- [ ] `BATTERY_LEVEL` is numeric, finite, and within 0–100.
- [ ] `SPACE_OCCUPIED` refers to a private EV and a genuinely free space.
- [ ] `SPACE_FREED` does not attempt to move a fleet vehicle or a charging vehicle.
- [ ] Charger failure/recovery is emitted through Core sensor intake.
- [ ] Malformed or contradictory events are retained as failed results and not silently ignored.
- [ ] No direct repository, SQL, or database write exists in `src/iot_sim/`.

## E. Testability and quality

- [ ] Seed and clock are explicit inputs; no global random state.
- [ ] Same seed and event ordering reproduce identical output.
- [ ] Unit tests cover normal, invalid, boundary, and deterministic behavior.
- [ ] Integration tests assert Core state and invariants after event application.
- [ ] Ruff, Ruff format, mypy (configured scope), and pytest pass.
- [ ] Coverage is reported per module against NFR-24.
- [ ] No secrets, generated caches, temporary files, or large binaries are committed.
- [ ] AI usage is declared in `docs/ai-usage/<student-id>.md`; author can explain every line.

## F. Sign-off

| Review item | Reviewer | Result | Evidence / comment |
|---|---|---|---|
| M8 test deliverables | M4 | Pending | |
| IoT simulator data / ERD alignment | M7 | Pending | |
| Core interface compatibility | M1 | Pending if API changes | |
| M8 self-check / CI | M8 | Pending | |
