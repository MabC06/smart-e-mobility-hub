# M2 Phase 1 - Review and delivery handoff

> Prepared 2026-10-11 (ICT) for 2452620 Đặng Tuấn Kiệt. **Draft; human review pending.**

## What is ready

The seven requested Markdown deliverables are present: M2 requirements, three behavioral design documents, M2-only report sections 02/05, and AI declaration. Supporting artifacts are ten editable PlantUML sources plus ten SVG exports (eight behavioral and two scoped use-case diagrams). This handoff is an additional review aid. No existing tracked file, other module, Core API or decision status was modified.

Start with [requirements](../requirements/fr-02-05-07-reservation.md), then [activity](../design/behavioral/reservation-activity-diagram.md), [sequence](../design/behavioral/reservation-sequence-diagram.md) and [state tables](../design/behavioral/reservation-state-machine.md). The report sections summarize the design for integration; they do not replace the canonical requirements/parameter register.

## Source and dependency status

Fetched source base: `46811d57f5f99cd026b29ddae42503d9744084ab`; `main` and `origin/develop` matched. PRs [#1](https://github.com/MabC06/smart-e-mobility-hub/pull/1) (M4), [#5](https://github.com/MabC06/smart-e-mobility-hub/pull/5) (M8), [#7](https://github.com/MabC06/smart-e-mobility-hub/pull/7) (M3), [#8](https://github.com/MabC06/smart-e-mobility-hub/pull/8) (M7), [#9](https://github.com/MabC06/smart-e-mobility-hub/pull/9) (M6), [#10](https://github.com/MabC06/smart-e-mobility-hub/pull/10) (M5) were all open. #1/#5 had M1 approval on the inspected head; others had no human approval. Exact paths/SHAs are in requirements §1. None was merged into the working tree.

Core API/class/Vehicle-state source documents were absent in all fetched refs. Do not treat the proposed transaction messages as published endpoints. Shared D-002/003/005/007 remain Proposed. No messages, review requests or PR comments have been sent by the assistant.

## Review decisions

| Owner(s) | Question | Recommended proposal |
|---|---|---|
| M1/M2/M7 | Can Core coordinate all resource and workflow writes? | One public unit of work with module-owned ports, command-result replay and invariant checks; no separately committed vehicle/booking calls |
| M1/M3/M7 | Can charging be scheduled without a bay? | No; non-null unique same-Hub bay for schedulable chargers; joint interval claim; one vehicle counts once |
| M1/M3/M4 | Can urgency take confirmed resources? | No; apply M4 class priority to uncommitted requests and M3 urgency within eligible waiting charging class |
| M1/M4/M7 | Is redistribution a student Reservation? | Keep separate RedistributionTask; share Core ResourceClaim with typed owner; no fake user or silent REBALANCE enum addition |
| M1/M3/M4/M5/M6 | Should all battery numbers become one threshold? | No; rental >=20%, pool lockout <=15%, critical incident <=10%, urgent charge <15%, simulation metric <20% |
| M2/M5/M7 | How is overdue computable? | Store planned duration and Trip expected_return_at at actual pickup; strict t > due+60 min; no fines/automatic trip end |
| M1/M2/M7 | How do deadlines/Pending work? | Ten-minute immediate rental, zero grace, Pending transient; preserve six names; exact expiry not eligible |
| M2/M3/M5/M7 | How do future parking and overstays work? | Private start within 24 h, 30..240 min, arrival before start+10; preserve real occupancy and reassign/reject following arrival |
| M1/M2/M4/M7 | Reserve destination automatically? | No; clear UI warning plus optional immediate ten-minute return hold on a space without future commitments |
| M1/M5/M7 | Does a fault end custody? | Pre-pickup cancel without freeing occupancy; in-trip remains Active until verified Hub return/recovery |
| M1/M6/M7 | Can simulation apply changes directly? | No; isolated state/clock/result namespace; separate operational confirmation and fresh checks |
| M2/M8/team | Are IDs final? | Provisional UC-M2/BR-M2 now; review suggested UC-20..27 and BR-20..35 mapping; M8 assigns official TC IDs |

## Verification record

- Both assignment PDFs were extracted and read in full (4 assignment pages, 7 rubric pages); local rules and all six listed PR documents were inspected.
- PlantUML 1.2026.2 `-checkonly` and SVG generation succeeded for all ten sources. PNG previews of all ten were inspected; revised R1/A3/S2 previews were inspected again after fixes. R1 overlapping self-event labels were replaced with state-internal text; A3 now allows departure before planned end. No remaining clipped text or ambiguous crossing labels were observed in the final previews.
- Requirements walkthrough covered 13 V-M2 scenario groups. Review clarified Available-at-search vs own-Reserved-at-pickup, and prevented future private commitments behind indefinite fleet-return occupancy.
- Final local checks passed: 28 new files (8 Markdown, 10 PlantUML, 10 SVG), 44 valid local links, parseable SVG XML/source pairs, 8 unique UC definitions, 16 unique BR definitions and 13 scenario definitions; zero undefined full M2-ID references, unbalanced fences, replacement characters or trailing whitespace. `git diff --check` also passed; it alone does not inspect untracked content. Tracked diff and staged diff were empty.
- No application implementation exists in this change; no application/unit/integration tests were run. V-M2 cases are planned test obligations, not TC execution results. No performance or runtime concurrency guarantees have been empirically verified.
- Limitations: Core/API and schema remain unapproved; browser-specific SVG behavior has not been checked; full Phase 0 system-wide actor/use-case consolidation is outstanding. Human review, personal AI-log verification and future M8 testing remain necessary.

Render commands and proposed Oct 12-25 review schedule are in [report 05](../report/05-behavioral-design.md). Repo deadlines are Oct 23 for M2 and Oct 25 for team review; Core API v1 is due Oct 19. Intermediate dates are proposals only.

## Safe Git handoff (commands for the student, not executed)

At handoff, the branch is still `main`, the index is untouched, and task files are untracked. Initial tree was clean; no pre-existing user changes needed preservation. Current Git identity was `kevindangpetrichor` / `kiet.dangcs@hcmut.edu.vn`, which does not follow the repository name/noreply recommendation. No Git configuration was changed.

Inspect before doing anything:

```powershell
git status --short --untracked-files=all
git branch --show-current
git config --get user.name
git config --get user.email
git diff
git diff --staged
git rev-parse HEAD origin/develop
```

If the two SHAs still match `46811d5...` and only the documented task files are present, create the working branch directly from the fetched integration ref. This does not require discarding or stashing these files:

```powershell
git switch --no-track -c docs/reservation-phase1-design origin/develop
```

Do not force the command if it reports a collision or if the branch already exists. If HEAD/develop changed or unrelated edits appeared, first **copy** all task and unrelated changed/untracked files to a separate backup folder preserving paths; verify the copies (a patch alone misses untracked files). A separate `git worktree add -b docs/reservation-phase1-design <new-empty-directory> origin/develop` then lets you copy only the reviewed M2 files into a fresh checkout, leaving the original work untouched. If target report/requirements files now exist, integrate the clearly marked M2 sections manually; do not overwrite teammates' content. No automatic stash/reset/delete is needed.

After creating the branch, set repo-local identity only if you want to follow the documented convention. Obtain the real noreply address from your own GitHub Settings -> Emails; the placeholder below must be replaced, not run literally:

```powershell
git config --local user.name "2452620 Đặng Tuấn Kiệt"
git config --local user.email "<YOUR_ACTUAL_GITHUB_NOREPLY_EMAIL>"
git config --get user.name
git config --get user.email
```

Recommended initial commit: M2 requirements/design/report/AI declaration and handoff together as one coherent traceable design change. Keeping parameters, diagrams and handoff together avoids intermediate broken links or conflicting policies. A meaningful second commit can later record human-review revisions or accepted parameter/interface changes together with their affected diagrams and AI log, using `docs(reservation): address M2 design review (FR-03, FR-05)`. Do not split source and generated SVG changes into separate commits. The explicit file lists below stage only this task; inspect all staged content first if you previously staged anything else.

```powershell
$m2DesignFiles = @(
  'docs/requirements/fr-02-05-07-reservation.md'
  'docs/requirements/use-case-diagrams/uc-m2-rental.puml'
  'docs/requirements/use-case-diagrams/uc-m2-rental.svg'
  'docs/requirements/use-case-diagrams/uc-m2-parking.puml'
  'docs/requirements/use-case-diagrams/uc-m2-parking.svg'
  'docs/design/behavioral/reservation-activity-diagram.md'
  'docs/design/behavioral/reservation-sequence-diagram.md'
  'docs/design/behavioral/reservation-state-machine.md'
  'docs/design/behavioral/reservation-diagrams/a1-rental.puml'
  'docs/design/behavioral/reservation-diagrams/a1-rental.svg'
  'docs/design/behavioral/reservation-diagrams/a2-release.puml'
  'docs/design/behavioral/reservation-diagrams/a2-release.svg'
  'docs/design/behavioral/reservation-diagrams/a3-parking.puml'
  'docs/design/behavioral/reservation-diagrams/a3-parking.svg'
  'docs/design/behavioral/reservation-diagrams/s1-reserve.puml'
  'docs/design/behavioral/reservation-diagrams/s1-reserve.svg'
  'docs/design/behavioral/reservation-diagrams/s2-pickup.puml'
  'docs/design/behavioral/reservation-diagrams/s2-pickup.svg'
  'docs/design/behavioral/reservation-diagrams/s3-return.puml'
  'docs/design/behavioral/reservation-diagrams/s3-return.svg'
  'docs/design/behavioral/reservation-diagrams/r1-rental.puml'
  'docs/design/behavioral/reservation-diagrams/r1-rental.svg'
  'docs/design/behavioral/reservation-diagrams/r2-parking.puml'
  'docs/design/behavioral/reservation-diagrams/r2-parking.svg'
  'docs/report/02-requirements-analysis.md'
  'docs/report/05-behavioral-design.md'
  'docs/ai-usage/2452620.md'
)
git add -- $m2DesignFiles
git add -- docs/reviews/m2-phase1-review.md
git diff --staged --stat
git diff --staged
git diff --staged --check
git diff --check
git commit -m "docs(reservation): define Phase 1 design (FR-02, FR-03, FR-04, FR-05, FR-07)"
```

Once your work is committed and the tree is clean, fetch and check the current integration base before pushing:

```powershell
git status --short
git fetch origin
git log --oneline HEAD..origin/develop
git diff --stat origin/develop...HEAD
```

If `origin/develop` has new commits, run `git merge origin/develop` on the M2 branch only. Resolve conflicts by preserving others' sections and integrating M2; regenerate affected diagrams and repeat checks. Then:

```powershell
git branch --show-current
git push -u origin docs/reservation-phase1-design
```

Open GitHub's new PR page with base `develop` and compare `docs/reservation-phase1-design`. Copy the draft below using `.github/pull_request_template.md`. Request **M7 Nguyễn Trung Kiên (`sharkin206`, author of PR #8)** as reviewer. Recheck the account before selection. Do not push directly to main/develop, force-push or merge your own PR. For this design-only PR mark runtime tests N/A; ask M8 to confirm documentation verification suffices for this phase rather than checking “all tests pass” without tests.

## Ready-to-copy PR draft

**Title:** `docs(reservation): define Phase 1 design (FR-02, FR-03, FR-04, FR-05, FR-07)`

### Problem

M2 had no requirements foundation or Phase 1 behavioral design on develop. Reservation, pickup/return and parking need explicit conflict, expiry, retry and shared-resource behavior before implementation.

### Changes

- Add M2 FR acceptance criteria, 8 full use cases, 16 provisional business rules, concrete parameter register and FR/UC/BR/diagram/scenario traceability.
- Add 3 UML activity, 3 sequence and 2 state-machine diagrams with editable PlantUML sources and SVG previews, plus 2 scoped M2 use-case diagrams.
- Add only M2 contributions to requirements/behavioral report sections, transparent AI declaration and review/Git handoff.
- Specify atomic Core-coordinated operations, exact deadline guards, replay-safe pickup/return, separate physical occupancy/calendar claims and coupled bay/charger admission.

### Assumptions

- All new shared policies are Proposed for team review. D-002/003/005/007 remain Proposed; no Core API or other owner's document is changed.
- Dependencies #1/#5/#7/#8/#9/#10 were open at inspection (exact head SHAs in requirements §1); #1/#5 approval does not approve all integration assumptions.
- Immediate ten-minute rental hold, no grace, 20% rental minimum, one live rental plus one parking per student; no automatic destination hold.
- Private parking start within 24 h, 30..240-minute stay; actual occupancy is never released merely by time/cancellation. M3 bay coordination and M4 typed dispatch claims require owner confirmation.
- Core API/state source is still absent; all sequence messages are a proposed interaction contract. M7 due-time/calendar fields and provisional UC/BR mapping need reconciliation.
- Proposals are localized in the M2 dependency/parameter tables. Adopted shared-interface decisions must later follow the repository DECISIONS/team-notice protocol.

### Related requirement

- FR-02, FR-03, FR-04, FR-05, FR-07 (parking); provisional UC-M2-01..08, BR-M2-01..16.
- NFR-06..09, NFR-12/13/16/18/21/22/25/26. V-M2 labels are planned scenarios, not official TC IDs.

### Verification

- PlantUML 1.2026.2 `-checkonly` and `-tsvg`: 10/10 sources successful; PNG visual inspection, including corrected R1/A3/S2.
- Local Markdown links, SVG source/export pairs, provisional-ID inventory and whitespace checked; 13 scenario groups reviewed for document consistency.
- [ ] Tests added/updated for this change - N/A, design-only documentation; implementation test obligations supplied for M8.
- [ ] All tests pass - N/A, no application test execution claimed.
- Re-run `git diff --staged --check` after staging and record the result before opening this PR.

### AI usage

- [ ] No substantial Generative AI use in this PR
- [ ] AI was used; I updated `docs/ai-usage/2452620.md`, reviewed the output, and can explain every change

Substantial Codex assistance is declared. The author should check the second box only after actual personal review and update the log with any revisions.

### Reviewer notes

- Primary reviewer: M7 (`sharkin206`). Check UI errors/unknown outcomes, parking/charging data, proposed Pending semantics and reservation-vs-trip lifecycle.
- M1/M3/M4/M5 input needed on atomicity, bay ownership, priorities, due-time/incident handling. No runtime API is approved by this PR alone.
- The two M2 use-case diagrams are not the missing system-wide Phase 0 consolidation.

### Checklist

- [ ] Synced with `develop` (target branch is `develop`)
- [ ] No secrets, `.env`, large files, build output or debug code (small SVGs are intentional diagram deliverables)
- [ ] Commit messages follow `CONTRIBUTING.md`
- [ ] If the `src/core/` interface changed: team notified and `docs/DECISIONS.md` updated - N/A, no implementation/interface file changed

## Personal review checklist

- [ ] Explain exact expiry, concurrent cancellation/pickup and replay behavior without reading AI output verbatim.
- [ ] Approve or revise parameters in the single canonical register and regenerate affected diagrams.
- [ ] Review dependency disagreements with owners; leave unapproved items Proposed.
- [ ] Confirm M2-only scope in shared reports and that unmerged source references still match PR heads.
- [ ] Confirm ID mapping with M8; do not claim executed TC results.
- [ ] Update personal AI verification, check staged files and real Git identity before commit.
