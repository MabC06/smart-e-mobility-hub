# NFR Measurement Report

> **Owner:** M8 — Testing, QA & Report Integration Lead  
> **Repository baseline:** `bb5c622` (snapshot supplied on 2026-11-18)  
> **Measurement date:** 2026-11-20  
> **Status:** Partial evidence; Remaining NFRs are open.

## 1. Method

NFR-02 and NFR-03 follow D-024: at least 100 **sequential** in-process API requests/operations against DS-STD. No concurrent load test is used. The reproducible runner is `tests/performance/measure_nfr02_03.py`; raw timings are stored in `evidence/nfr02-03-python312-rerun.json`.

Environment recorded by the run:

- Python 3.12.10
- FastAPI `TestClient`
- Isolated in-memory SQLite repository
- DS-STD generated with seed 2026: 10 Hubs, 400 parking spaces, 61 charging points, 250 fleet + 100 private vehicles, 1,005 users
- 100 sequential samples per operation; no concurrency

## 2. NFR-02 — Read API Performance

**Result: PASS (for the four tested endpoints)**

Performance testing was conducted using 100 sequential requests per endpoint on the DS-STD dataset.

| Endpoint | Samples | p95 (ms) | Max (ms) | Result |
|---|---:|---:|---:|---|
| GET /hubs | 100 | 27.830 | 74.016 | PASS |
| GET /hubs/H01/vehicles | 100 | 39.059 | 66.605 | PASS |
| GET /api/v1/monitoring/metrics/hubs | 100 | 28.043 | 94.486 | PASS |
| GET /charging/queue | 100 | 9.067 | 13.263 | PASS |

All tested endpoints satisfied the specified thresholds of p95 ≤ 500 ms and max ≤ 2,000 ms.

## 3. NFR-03 — Write API Performance

**Result: PASS (for the tested operation)**

The `POST /charging/requests/immediate` endpoint was tested using 100 sequential operations.

| Metric | Measured value | Target |
|---|---:|---:|
| p50 | 26.428 ms | Informational |
| p95 | 33.610 ms | ≤ 1,000 ms |
| Max | 45.727 ms | Informational |
| Successful operations | 100/100 | 100% |

All 100 operations returned HTTP 200, with zero recorded write errors.

## Test Environment

- Python 3.12.10
- Commit: `bb5c622`
- FastAPI TestClient
- In-memory SQLite
- Sequential execution without concurrency
- DS-STD seed: 2026
- 10 hubs, 400 parking spaces, 61 charging points, 350 vehicles, and 1,005 users.

**Limitation:** These results represent measurements in the local test environment and do not constitute production performance guarantees. The conclusions apply only to the endpoints and operation tested above.

## 4. Remaining NFR evidence

| NFR | Required evidence | Status |
|---|---|---|
| NFR-01 | State update followed by read visibility; UI refresh timing | Not measured in this run |
| NFR-04 | Charging schedule ≤3 s/Hub; network redistribution ≤5 s | Not measured in this run |
| NFR-05 | Each of five standard simulation scenarios ≤30 s | Not measured in this run |
| NFR-06 | 20–50 simultaneous requests, 100 repeated runs | Not measured here; separate concurrency test required |
| NFR-07 | Invariant checker after integration and simulation runs | Partially asserted by existing module tests; consolidated evidence pending |
| NFR-10 | Malformed sensor event and equipment-failure response | Existing Core/IoT tests cover parts; system-level timing evidence pending |
| NFR-12 | Operational-state hash unchanged and write guard | Requires explicit system-level evidence for all five scenarios |
| NFR-13 | Same seed/event order gives identical state hash/output | Existing dataset/event tests cover deterministic generation; consolidated simulation evidence pending |
| NFR-14 | Fresh clone by a different member, ≤15 min and ≤5 commands | Not performed by M8 author; assign an independent team member |
| NFR-16 | Authorization test for every endpoint | New integration tests cover selected endpoints only; endpoint inventory/sign-off pending |
| NFR-24 | Per-module coverage thresholds from current CI artifacts | Not verified against the current snapshot's CI artifact |
| NFR-25 | State-change audit evidence | Existing Core tests cover audit behavior; consolidated integration evidence pending |
| NFR-26 | Every FR/BR/UC linked to TC; zero orphan IDs | Not complete; module-owned BR/UC/test-case links must be confirmed |

## 5. Reproduction

From the repository root, using the project's Python 3.12 environment:

```powershell
python tests/performance/measure_nfr02_03.py `
    --output docs/testing/evidence/nfr02-03-python312-rerun.json `
    --count 100
```
