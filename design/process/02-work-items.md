# 02. Work Items

## 1. Tracker

GitHub Issues in each repository is the tracker; cross-repository epics live in this hub's tracker (or the owner's
GitHub Project). Every pull request links exactly one issue. Work without an issue is not merged.

## 2. Issue types and templates

| Type | Template |
|---|---|
| Feature or change | [templates/issue-feature.md](templates/issue-feature.md) |
| Defect | [templates/issue-bug.md](templates/issue-bug.md) |
| Gap report | [templates/issue-gap.md](templates/issue-gap.md) |
| Spike | [templates/spike-report.md](templates/spike-report.md) (the issue states the question; the report closes it) |

Epics are issues labeled `type/epic` with a task list of child issues. An epic is decomposed into child issues that
are each one pull request in size.

## 3. Labels

| Group | Values |
|---|---|
| `type/` | `feature`, `change`, `bug`, `refactor`, `gap`, `spike`, `contract`, `clause`, `workflow`, `docs`, `chore`, `epic` |
| `size/` | `trivial`, `small`, `standard`, `large` |
| `risk/` | `r0`, `r1-engineering`, `r2-contract`, `r3-security` (several allowed) |
| `status/` | `triage`, `needs-info`, `ready`, `spec-review`, `plan-review`, `in-progress`, `in-review`, `acceptance`, `blocked`, `done` |
| `phase/` | `0` to `4` |
| `area/` | per repository, for example `tools`, `adapter`, `plugin`, `engine`, `ui`, `decisions` |
| `source/` | `tasklog` (filed at triage from a task-log need, §5) |

## 4. Definition of Ready and Definition of Done

**Ready** (an item may move to `in-progress` only when):

- [ ] The issue uses its template, is labeled, and is assigned to exactly one identity (the claim).
- [ ] Acceptance criteria are measurable (Given, When, Then), including failure cases.
- [ ] The spec is on `main` with `status: approved` (small: the issue's criteria serve as the light spec).
- [ ] The plan is on `main` with `status: approved` (except trivial).
- [ ] Dependencies (other issues, releases, spikes) are done or explicitly not needed.
- [ ] For R1: the engineering sources (clauses, worked examples, owner inputs) are identified.

**Done** (an item may close only when):

- [ ] All acceptance criteria are covered by passing tests.
- [ ] CI is green on the merged commit.
- [ ] Required reviews are recorded and every critical and high finding is resolved.
- [ ] Generated documents are current; human documents are updated.
- [ ] For host-touching changes: the live acceptance scripts cover the change (the record itself is produced before the
      next release, [05](05-testing-and-verification.md) §6).
- [ ] For R1: the engineering verification record is complete ([10](10-engineering-verification.md)).
- [ ] The changelog entry is written (for user-visible changes).

## 5. Gap reports (principle P12)

A gap report is filed whenever someone, a workflow or an agent, needs a capability that does not exist: a missing
tool, parameter, check, calc function, kind or host operation. During a live project, the project lane
([01](01-lifecycle.md) §9) builds the tool first and files the gap report as its record.

- In live work ([01](01-lifecycle.md) §10), a missing capability is a `not_found` record in the task log and the
  agent goes on with what is possible. The gap issue is filed at triage by a development session, labelled
  `source/tasklog`, citing need ids only, never log content (A24).
- Outside live work and the project lane, the person or agent that hits the gap stops the improvisation, files the
  report with the exact need, the workflow or task that needs it, and evidence (host API reference, example). An
  agent then reports `BLOCKED` and ends its work on the item; it does not switch to another item in the same session
  (A18).
- Triage outcome: `new spec` (it becomes a feature), `covered` (existing tools do it; the report explains how),
  `host limitation` (documented, alternative proposed), or `out of scope`; for a need from a task log also
  `duplicate` (of another need) or `defect` (a bug, filed as one).
- A gap is never closed by adding an escape hatch.
