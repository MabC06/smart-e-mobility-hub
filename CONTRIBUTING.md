# Coding Rules & Contributing Guide

> Applies to the whole team. Rule changes need team agreement and a note in `docs/DECISIONS.md`.

---

## 1. General rules

1. Commit your own work under your own identity. Never commit on behalf of others, so that individual contributions stay traceable.
2. Code, reports and outputs must be reproducible from a clean clone.
3. Never hand-edit generated files or outputs to make results match the report.
4. Record assumptions and key decisions in `docs/DECISIONS.md` with date and owner.
5. **Using Generative AI must be declared (mandatory)** in `docs/ai-usage/<student-id>.md`, at the time of use. You must be able to explain every line of code or text you commit.
6. Never commit secrets, tokens, passwords or credentials (see section 11).
7. Never force-push to `main` or `develop`.

## 2. Git identity

Set your identity **per repo**, not `--global` on shared machines.

```bash
git config --local user.name  "<Student ID> <Full name>"
git config --local user.email "<your GitHub noreply email>"   # e.g. 12345678+username@users.noreply.github.com
git config --local --list | grep user      # verify
```

**How to get your GitHub noreply email:**

1. Click your profile picture → **Settings** → **Emails**.
2. Turn on **Keep my email addresses private**.
3. Copy the address GitHub shows under it: `<number>+<username>@users.noreply.github.com` (older accounts may show `<username>@users.noreply.github.com`).
4. Recommended: also turn on **Block command line pushes that expose my email**, so a commit made with your real email is rejected.

Commits made with this address are still linked to your GitHub profile, but your real email does not appear in the repo history. Commits made before you changed the setting keep the old email; do not rewrite shared history to fix that.

## 3. Branches

| Branch | Role |
|---|---|
| `main` | Always in a working state; used for demo/submission and tagged at milestones. Only receives `develop` via a PR merged by the Lead. |
| `develop` | Integration branch; all work merges here via PR. |
| `<type>/<module>-<short-desc>` | Short-lived working branches cut from `develop`. |

**Branch name:** `<type>/<module>-<short-desc>`

| type | Use for |
|---|---|
| `feat` | new feature |
| `fix` | bug fix |
| `docs` | documentation, diagrams, report |
| `test` | tests |
| `refactor` | refactoring without behavior change |
| `chore` | setup, config, dependencies |

**module** (also used as the commit scope): `core`, `reservation`, `charging`, `allocation`, `monitoring`, `simulation`, `iot-sim`, `ui`, `docs`, `test`, `repo`.

Examples: `feat/reservation-booking-flow`, `fix/charging-queue-overflow`, `docs/core-state-machine`, `feat/iot-sim-battery-drain`

Rules:

- One concern per branch; keep it short-lived and regularly bring the latest `develop` into it.
- No vague names such as `test`, `new-branch` or `final`; never reuse a merged branch for another task.
- Do not edit another module's files without discussing it first.
- **Changing a shared interface or the `core` API contract requires telling the whole team first and a note in `docs/DECISIONS.md`.**

## 4. Commits

```
<type>(<scope>): <summary> (<ID>)
```

- `type`: as in the table in section 3.
- `scope`: module name (section 3).
- `summary`: at most 72 characters, imperative mood, no trailing period.
- `ID`: related requirement / use-case / issue ID, if any (section 5).

```
feat(reservation): add double-booking check (FR-03, BR-02)
fix(charging): reject charging request below minimum battery (FR-06)
docs(core): add vehicle state machine diagram
test(allocation): cover no-available-hub case (FR-10, TC-041)
chore(repo): add .gitignore and .env.example
```

- Each commit is one complete, working logical change.
- No broken code, debug leftovers or temp files.
- Already pushed? Fix it with a new commit; do not rewrite history.
- Before committing, check `git status` and `git diff --staged`.

## 5. Requirement IDs & Traceability

The report is graded on consistency between requirements, design, code and tests. Everything therefore gets an ID that is reused in commits, PRs and tests.

| ID | Stands for | Meaning | Example |
|---|---|---|---|
| `FR-xx` | Functional Requirement | What the system must do. | `FR-03` Reserve rental electric vehicles |
| `NFR-xx` | Non-Functional Requirement | Measurable quality attributes: performance, reliability, data consistency, etc. | `NFR-01` Hub status updates are visible within N seconds |
| `BR-xx` | Business Rule | Rules constraining behavior and shared resources: reservation conflicts, capacity limits, valid state transitions. | `BR-02` A vehicle cannot have two overlapping active reservations |
| `UC-xx` | Use Case | An actor–system interaction scenario. | `UC-05` Student reserves a vehicle |
| `TC-xxx` | Test Case | A test linked to the FR/UC it verifies. | `TC-041` Allocation with no available hub |

- Actual numbers are defined in `docs/requirements/`; the examples above are illustrative.
- This is a team naming convention, not a GitHub feature.

## 6. Pull Requests & Review

- PRs target `develop` (except the Lead's `develop` → `main` PR).
- Use `.github/pull_request_template.md` (GitHub fills it in automatically).
- At least **1 approval** from someone else is required before merging; authors never approve their own PR.
- A PR is only "Done" with its tests. PRs touching important business logic (`core`, `reservation`, `charging`, `allocation`, `simulation`) need M8's sign-off that the tests exist and pass.
- Authors address feedback with new commits on the same branch and resolve all conversations before merging.

**Primary reviewer per module** (adjust by team agreement):

| Module (author) | Primary reviewer | Reason |
|---|---|---|
| M1 Core | M5 | M5 consumes core state. |
| M2 Reservation | M7 | Student UI flows. |
| M3 Charging | M6 | Simulation depends on charging logic. |
| M4 Allocation | M2 and M3 | Integrates with reservation and charging. |
| M5 Monitoring | M1 | Built on core. |
| M6 Simulation | M1 | Simulates core state. |
| M7 UI / Data design | M5 | Operator dashboard. |
| M8 Tests | M4 | Allocation / conflict tests. |
| M8 IoT simulator (`iot-sim`) | M7 | Checks generated data against the ERD and class diagram. |

PRs by non-M1 members that change `src/core/` also need M1's approval.

## 7. Sync & Merge

**Start of each work session:**

```bash
git switch develop
git pull --ff-only origin develop
git switch <your-branch>
git merge develop               # bring the latest develop into your branch
```

**Push:**

```bash
git push -u origin <your-branch>     # first time
git push                              # afterwards
```

**After the PR is merged:**

```bash
git switch develop
git pull --ff-only origin develop
git branch -d <your-branch>
```

**`develop` → `main`:** done **only by the Lead**, via PR, when tests pass and at each sprint/milestone. Tag demo and submission milestones.

**Never use** on `main`, `develop` or shared branches:

```bash
git push --force
git reset --hard
git rebase      # on pushed branches that others rely on
```

On conflicts: resolve carefully, re-run tests, and never blindly "accept all".

## 8. Branch protection (for the Lead)

In Settings → Branches (or Rulesets), apply to both `main` and `develop` (option names may vary by UI):

- Require a pull request before merging, with 1 required approval.
- Dismiss stale approvals when new commits are pushed.
- Require conversation resolution before merging.
- Block force pushes; restrict deletions.
- Require status checks to pass: enable once CI exists.

## 9. Code rules

> The tech stack is not final. These rules are language-neutral; once the stack is chosen, add the formatter/linter here and in `docs/DECISIONS.md`.

1. One clear responsibility per function/class; business logic lives in its module, not in one big file.
2. Modules communicate through the `core` interface/API contract, not by reaching into each other's internals.
3. No hard-coded absolute paths, secrets, seeds or magic numbers; use named constants or config.
4. No global mutable state; hub/vehicle/charger state goes through `core`'s state management.
5. What-if simulation state must be isolated from the real operational state.
6. State transitions (vehicle, reservation, charging session, incident) follow only the valid transitions in the designed state machines.
7. Invalid data/input must raise clear errors; never silently ignore it or swallow exceptions.
8. Reproducible outputs must be deterministic: sort before output and pass seeds as parameters.
9. Text files in UTF-8; identifiers in clear English.
10. Public functions have explicit types (where the language supports them) and documentation of inputs, outputs and important errors.
11. Remove dead code, debug logs and commented-out code before opening a PR.
12. Pin dependency versions in the dependency file.
13. The IoT simulator (`iot-sim`) is the only component that fabricates sensor/event data. It feeds state only through the state-update interface of `core` (never by writing to storage directly), and its output must be reproducible from a seed passed as a parameter.

## 10. Testing rules

- Write tests alongside the code, not at the end.
- Module unit tests live in `tests/<module>/` and are written by the module owner; integration tests live in `tests/integration/` and are owned by M8.
- Derive test cases with course techniques (equivalence partitioning, boundary-value analysis, decision tables, state-transition testing, etc.) and link them to `FR`/`UC` IDs.
- Cover: normal operation, invalid input, boundary/capacity conditions, resource conflicts, state transitions, equipment failures, What-if scenarios, integration.
- Tests must run with one command and pass before opening a PR.

## 11. Security & repo hygiene

### 11.1 Secrets

- **Never** commit passwords, API keys, tokens, private keys, `.env` files, or database connection strings with passwords.
- Keep secrets in environment variables or an ignored `.env`; commit only `.env.example` with variable names and no real values.

### 11.2 If a secret is committed

1. **Revoke/rotate the secret immediately.** Treat it as leaked even in a private repo.
2. Tell the team.
3. Remove it from history with `git filter-repo` or BFG (this needs team coordination because history is rewritten). Deleting the file in a new commit is **not enough**.

### 11.3 `.gitignore`

Create `.gitignore` in the first commit and adapt it to the chosen stack. Minimal template:

```gitignore
# Secrets
.env
*.pem
*.key
secrets/

# Dependencies / virtual environments (adjust to the stack)
node_modules/
.venv/
venv/
__pycache__/

# Build, logs, local databases
dist/
build/
*.log
*.db
*.sqlite

# IDE / OS
.vscode/
.idea/
.DS_Store
Thumbs.db
```

- Do not commit build output, large binaries or logs. **Do not commit the demo video**; link it in the README.
- Small seed/simulated data may be committed; for large data, document how to regenerate it in the README.

### 11.4 Repo & accounts

- Keep the repo **private**; invite only team members and instructors.
- Enable 2FA on your GitHub account.
- Enable secret scanning / push protection if available (Settings → Code security).
- Install dependencies only from trusted sources and record them in the dependency file.

## 12. Required docs

| File | Content |
|---|---|
| `README.md` | Overview, scope, setup, run, test, team. |
| `CONTRIBUTING.md` | This file. |
| `docs/DECISIONS.md` | Assumptions and decisions with date and owner. |
| `docs/ai-usage/<student-id>.md` | Per-member AI declaration: tool, purpose, and what was generated/revised/verified. |
| `.env.example` | Environment variable names only. |
| `.gitignore` | See 11.3. |

## 13. Pre-PR checklist

- [ ] Synced with `develop` (`git pull --ff-only origin develop`, then merged into the branch).
- [ ] Tests run and pass; the change is covered by tests.
- [ ] No debug logs, dead code or temp files.
- [ ] Clean `git status`; no secrets, large files or build output.
- [ ] Commit messages follow section 4 and include relevant `FR`/`UC`/`BR` IDs.
- [ ] AI usage declared in `docs/ai-usage/<student-id>.md` if used, and I can explain every change.
- [ ] PR template fully filled in.
