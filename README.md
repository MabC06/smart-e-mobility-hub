# Smart E-Mobility Hub

A coordination system for shared electric mobility resources (e-bikes/e-scooters) across the VNU-HCM Urban Area. Course project for **Software Engineering — HK261**.

The system manages Mobility Hubs consisting of parking spaces, charging points, and vehicles, serving two main actor groups: **students** (rent vehicles, reserve, charge) and **operators** (monitor, handle incidents, coordinate, run What-if Simulations).

---

## Table of Contents

- [Key Files](#key-files)
- [Scope](#scope)
- [Team](#team)
- [Repository Structure](#repository-structure)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
- [Running the Demo on a Phone](#running-the-demo-on-a-phone)
- [Troubleshooting](#troubleshooting)
- [Testing](#testing)
- [Generative AI Usage Declaration](#generative-ai-usage-declaration)
- [Demo](#demo)

---

## Key Files

Start here before reading the rest of the repo:

| File | Content |
|---|---|
| `README.md` | Project overview, scope, setup, team — this file. |
| `CONTRIBUTING.md` | Workflow & coding rules: branching, commits, PR review, code style, testing, security. |
| `docs/DECISIONS.md` | Assumptions and decisions, with date and owner. |
| `docs/ai-usage/<student-id>.md` | Per-member AI declaration: tool, purpose, what was generated/revised/verified. |
| `.env.example` | Environment variable names only. |
| `.gitignore` | What's excluded from the repo (secrets, build output, caches). |

## Scope

Per the assignment specification, the system supports at least the following 12 core capabilities. Each has an ID (`FR-xx`) used in commits, pull requests, test cases and the report for traceability.

| ID    | Functional capability                                                           | Main module(s) |
| ----- | ------------------------------------------------------------------------------- | -------------- |
| FR-01 | View Mobility Hubs and their current resource status                            | M1             |
| FR-02 | Find suitable rental electric vehicles; view availability & battery information | M2             |
| FR-03 | Reserve rental electric vehicles                                                | M2             |
| FR-04 | Pick up and return rental electric vehicles                                     | M2             |
| FR-05 | Reserve parking spaces                                                          | M2             |
| FR-06 | Request or schedule charging services                                           | M3             |
| FR-07 | Support private-vehicle users in reserving parking and charging resources       | M2, M3         |
| FR-08 | Monitor vehicles, parking capacity, charging points, and Hub utilization        | M5             |
| FR-09 | Handle operational incidents (unavailable vehicles, failed charging points)     | M5             |
| FR-10 | Coordinate/redistribute rental vehicles among Mobility Hubs                     | M4             |
| FR-11 | Coordinate charging priorities and schedules                                    | M3, M4         |
| FR-12 | Run What-if Simulation scenarios and generate coordination recommendations      | M6             |

> `NFR-xx` (non-functional requirements), `BR-xx` (business rules), `UC-xx` (use cases) and `TC-xxx` (test cases) are defined in `docs/requirements/`. ID conventions: [CONTRIBUTING.md, section 5](CONTRIBUTING.md#5-requirement-ids--traceability).

**Out of scope** (per the assignment): physical hardware development and sophisticated 3D map interfaces. Vehicle, parking and charging state may come from simulated data.

## Team

| Member | Module                                                     | Name              | Student ID |
| ------ | ---------------------------------------------------------- | ----------------- | ---------- |
| M1     | Core Domain, State Management & System Architecture (Lead) | Đoàn Nhật Minh    | 2452738    |
| M2     | Reservation & Trip (Student)                               | Đặng Tuấn Kiệt    | 2452620    |
| M3     | Charging Request & Smart Scheduling                        | Võ Thanh An       | 2452030    |
| M4     | Resource Allocation & Vehicle Dispatching                  | Huỳnh Minh Nhật   | 2412466    |
| M5     | Operator Monitoring & Incident Handling                    | Đỗ Hoàng Việt     | 2453413    |
| M6     | What-if Simulation & Coordination Design                   | Thân Ngô Tuấn     | 2453366    |
| M7     | UI/UX Design & Structural-Data Design                      | Nguyễn Trung Kiên | 2452615    |
| M8     | Testing, QA & Report Integration Lead; IoT data simulator  | Lý Thành Tín      | 2453252    |

Task breakdown, deliverables per member and the team timeline: [docs/task-assignment-timeline.md](docs/task-assignment-timeline.md).

## Repository Structure

This tree is also the map of **where every deliverable lives** — each folder's comment says what goes there, so there is only one place to look.

```
smart-e-mobility-hub/
├── docs/
│   ├── requirements/          # assignment spec, rubric, FR/NFR/BR, reference dataset, use-case diagrams & tables
│   ├── design/
│   │   ├── architecture/      # architecture diagram + justification, tech-stack proposal
│   │   ├── structural/        # class diagram, ERD
│   │   ├── behavioral/        # activity, sequence, state machine diagrams
│   │   ├── ui/                # wireframes, UI flow
│   │   └── simulation/        # What-if scenario & recommendation design
│   ├── testing/                # test plan, test cases, execution report, defect log
│   ├── report/                 # integrated final report (one file per rubric section)
│   ├── ai-usage/               # one declaration file per member: <student-id>.md
│   ├── DECISIONS.md            # assumptions & key decisions, with date/owner/status
│   └── task-assignment-timeline.md
├── src/
│   ├── core/                  # M1 — domain model & state management
│   ├── reservation/           # M2 — reserve, pick up/return
│   ├── charging/               # M3 — charging request & scheduling
│   ├── allocation/            # M4 — resource allocation & dispatching
│   ├── monitoring/             # M5 — operator monitoring & incident handling
│   ├── simulation/             # M6 — what-if simulation
│   ├── iot_sim/                # M8 — simulated sensor/event feed & seed data
│   └── ui/                     # M7 — student & operator interfaces
├── tests/
│   ├── <module>/               # unit tests, written by each module's owner
│   ├── integration/            # integration tests, owned by M8
│   └── performance/            # NFR measurement scripts (M8), results in docs/testing/
├── .github/                    # pull_request_template.md, CODEOWNERS, workflows/ci.yml (CI)
├── .env.example                 # required environment variables (names only)
├── .gitignore
├── CONTRIBUTING.md              # workflow & coding rules — read before your first PR
└── README.md
```

No hardware is used, so vehicle, parking and charging-point state comes from simulated data. `src/iot_sim/` (owner: M8) generates the seed data and a simulated sensor/event feed (battery drain/charge, parking occupancy changes, charging-point failures, peak-hour demand) and pushes it into the system through the state-update interface of `core`. It is separate from the What-if Simulation (`src/simulation/`, M6), which runs hypothetical scenarios on a copy of the state.

## Tech Stack

Decided in D-002 (details and reasons: [`docs/design/architecture/tech-stack-proposal.md`](docs/design/architecture/tech-stack-proposal.md)).

- Backend language/framework: Python 3.12, FastAPI with Pydantic
- Frontend: server-rendered pages with Jinja2 + HTMX, served by the same application; the pages call the module routes in-process with `httpx` (D-026); student pages also fit phone screens (D-027)
- Database: SQLite through SQLAlchemy 2.x
- UML/wireframing tools: Mermaid in the Markdown files; draw.io or PlantUML where Mermaid is not enough
- Test framework / test-case management: pytest with pytest-cov; test cases as Markdown tables in `docs/testing/`, linked to pytest by `TC-M<n>-###` markers
- Quality checks: ruff (lint and format), mypy (strict on `core`, `reservation` and `main.py`), coverage per module (D-025), run by CI on every PR

## Getting Started

These steps take a fresh clone to the running demo in about 10 minutes. They use **Windows PowerShell**; the differences for macOS and Linux are listed after step 7.

**You need:** Git, and **Python 3.12 or newer**. Check with `python --version`. Nothing else has to be installed.

**1. Clone the repository**

```powershell
git clone https://github.com/MabC06/smart-e-mobility-hub.git
cd smart-e-mobility-hub
```

**2. Create the virtual environment and activate it**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

The prompt now starts with `(.venv)`. If PowerShell says that running scripts is disabled, allow it for this window only and activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

**3. Install the pinned dependencies**

```powershell
pip install -r requirements-dev.txt
```

**4. Create your `.env` from the template**

```powershell
Copy-Item .env.example .env
```

The application reads only `.env`. `.env.example` is the committed template with names and no values: never put a value in it. `.env` is ignored by Git: never commit it (CONTRIBUTING 11.1).

**5. Fill in four lines of `.env`**

Make a secret key for your machine (a random text; it signs the login tokens):

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Open `.env` (`notepad .env`) and set these lines; leave every other line empty:

```
SECRET_KEY=<the text printed above>
SEED_ON_START=true
DEMO_PASSWORD=<a password of at least 8 characters, chosen by you>
DATABASE_URL=
```

- `SECRET_KEY`: at least 16 characters, no default. Each member makes their own; do not share it.
- `SEED_ON_START=true` loads the demo network from the simulator (`src/iot_sim`, M8): 10 Hubs, 350 vehicles, 1,005 accounts.
- `DEMO_PASSWORD` is the password of every demo account (D-028). If your `.env` was made before 25 Nov 2026, the line is missing: add it.
- `DATABASE_URL` empty keeps the data in memory, so every start begins with a fresh demo network. With a file (`sqlite:///data/hub.db`) the data stays, and the password is set only when the file is first filled: delete the file to change it.

**6. Start the server**

```powershell
python -m uvicorn --app-dir src main:create_app --factory --port 8000
```

Wait for `Application startup complete`. A line `demo network loaded` shows that the demo data is in. Keep this window open; `Ctrl+C` stops the server. After changing `.env`, stop and start the server again.

**7. Open the screens**

Open http://127.0.0.1:8000 and log in with an account code and your `DEMO_PASSWORD`:

| Account | Code | Screens |
|---|---|---|
| Student | `STU-0001` to `STU-1000` | Hubs, vehicle search and rental, my bookings, parking, charging (S1 to S9) |
| Operator | `OPS-01` to `OPS-05` | Network overview, Hub detail, charging queues, dispatch, incidents, What-if Simulation (O1 to O6) |

Operator screens are made for a desktop screen (from 1280 px wide).

To charge a student's own EV: **Parking** → book a stay at a Hub → **Arrive**, then **Charging** → **Now**. Charging needs the EV parked in a charging bay of that Hub; the first spaces of each Hub are its bays. **Finish charging** ends the session, then **Depart** on the Parking page. The API documentation is at http://127.0.0.1:8000/docs (hidden when `APP_ENV=production-demo`).

**Next time** only two commands are needed, in the project folder: `.venv\Scripts\Activate.ps1`, then the command of step 6.

**macOS and Linux:** use `python3` instead of `python` in step 2, `source .venv/bin/activate` to activate, and `cp .env.example .env` in step 4. In Git Bash on Windows, activate with `source .venv/Scripts/activate`.

## Running the Demo on a Phone

The student screens also fit a phone (D-027). The phone and the laptop must be on the same Wi-Fi.

1. Start the server on every network interface of the laptop, not only `127.0.0.1`:

   ```powershell
   python -m uvicorn --app-dir src main:create_app --factory --host 0.0.0.0 --port 8000
   ```

2. Find the laptop's address: `ipconfig` on Windows (IPv4 Address of the Wi-Fi adapter, for example `192.168.1.23`), `ipconfig getifaddr en0` on macOS, `hostname -I` on Linux.
3. On the phone open `http://<that address>:8000` and log in as a student.

- On Windows, the first start shows a firewall prompt for Python: allow it on **private** networks only. If the page does not open, check that the Wi-Fi is set as a private network.
- Some campus or public Wi-Fi networks block devices from reaching each other. Then turn on the phone's hotspot, connect the laptop to it and use the laptop's address on that network.
- `--host 0.0.0.0` lets anyone on the same network reach the server: use it only on a network you trust, choose a `DEMO_PASSWORD` that is not easy to guess, and stop the server after the demo.

## Troubleshooting

| What you see | Cause and fix |
|---|---|
| `No module named uvicorn` (or `fastapi`) | The virtual environment is not active or the dependencies are not installed: step 2 (activate), then step 3. |
| `Activate.ps1 cannot be loaded because running scripts is disabled` | Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, then activate again (step 2). |
| `Configuration error: SECRET_KEY is not set` or `SECRET_KEY must be at least 16 characters` | Step 5: put a key of at least 16 characters in `.env`. |
| `Configuration error: DEMO_PASSWORD must be at least 8 characters` | Choose a longer password in `.env`. |
| Log line `DEMO_PASSWORD is not set: the seeded accounts cannot log in`, and the login page says "The code or the password is wrong" | `DEMO_PASSWORD` is missing from `.env` (a value in `.env.example` is not read). Add it to `.env` and restart the server. With a database file, delete the file first. |
| Login fails although `DEMO_PASSWORD` is set | Restart the server after editing `.env`; check the code (`STU-0001`, `OPS-01`); with a database file, delete it so the new password is applied. |
| No Hubs or vehicles on the screens | `SEED_ON_START=true` is missing, or the database file was created without it: set it and delete the file. |
| `error while attempting to bind on address` | Port 8000 is used by another program or another server window. Stop it, or use `--port 8001` and open that port. |
| A change to `.env` has no effect | `.env` is read only at start: stop the server (`Ctrl+C`) and start it again. |

## Testing

Each module owner writes and owns the unit tests for their module in `tests/<module>/`. M8 owns the Test Plan, the standardized test cases (linked to `FR`/`UC` IDs), integration tests in `tests/integration/`, and the execution/defect report.

Full testing process, required coverage categories and the PR sign-off rule: [CONTRIBUTING.md, section 10](CONTRIBUTING.md#10-testing-rules). Artifacts: `docs/testing/`.

## Generative AI Usage Declaration

Per course requirements, any use of Generative AI (analysis, design, coding, report writing, etc.) must be transparently declared — tool, purpose, and which parts were AI-generated, revised, or verified. Students remain responsible for understanding and defending everything they submit.

Each member records their own usage in `docs/ai-usage/<student-id>.md` **at the time of use**, not at the end — see [CONTRIBUTING.md, section 1](CONTRIBUTING.md#1-general-rules). M8 consolidates the final declaration before submission.

## Demo

A pre-recorded demo (≈3 minutes within the ≈20-minute presentation; live demos are not permitted). The video file is **not** committed to the repo — linked here instead.

*Link to the recorded demo video: TBD.*
