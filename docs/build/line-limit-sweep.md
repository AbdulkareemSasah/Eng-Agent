# Line-limit removal: leftovers found by the completeness sweep (2026-11-17)

The hub ADR collision (item 1 of the hub part) is fixed: the hub ADR is now 0035 (hub commit 49f43e0).

Leftovers: places that still treat the changed-line count as a limit, cap, failure, BLOCKED condition or NEEDS_PLAN_AMENDMENT reason. Nothing was edited.

Branch heads checked: hub origin/claude/pensive-volta-gcx0y9 at 83264cc, build/v1 at 1f2fbac, B-552 branch origin/docs/b552-gate-line-count-estimate at 48420c1 (not merged).

Not counted as leftovers:
- The per-task estimates and amendment notes in plan front matter.
- History: BUILD-STATUS P-entries and the registry table, lane-results, lead-findings, the CHANGELOG history lines, the HANDOFF history tables, and the bodies of ADR-0021 and ADR-0034.
- The `trivial` tier threshold, "at most 10 changed lines" (process/01 §2 and `TRIVIAL_MAX_LINES` in gate_check_docs.py:19). It sorts a change into a tier and is not a task limit, so it stays.
- `limits.diff_lines`. It only cuts the length of drift output, so it stays.

## HUB (origin/claude/pensive-volta-gcx0y9)

The wording is clean. No remaining statement treats changed lines as a limit. One blocking issue and one optional item remain:

1. **ADR number collision (blocking).** The hub ADR is `docs/adr/0028-no-changed-line-limit.md`, but build/v1 `design/docs/adr/` already uses 0028 to 0034. 0028 there is "build v1 in this repository". B-552's spec already links to 0035. Rename it to `docs/adr/0035-no-changed-line-limit.md` and fix every reference:
   - `docs/adr/0028-no-changed-line-limit.md:1`: "# ADR-0028: ..." → "# ADR-0035: No changed-line limit per task"
   - `docs/adr/README.md:30`: "amended by ADR-0026 and ADR-0028" → "amended by ADR-0026 and ADR-0035"
   - `docs/adr/README.md:37`: change the row to `[0035](0035-no-changed-line-limit.md)`. The hub's table has no rows for 0028 to 0034, so this is a gap in the index; the owner decides whether to copy them in.
   - `docs/adr/0021-agent-agnostic-ci-enforced-process.md:3` (status line): "ADR-0028 (no changed-line limit)" → "ADR-0035 (no changed-line limit)"
   - `process/04-implementation-rules.md:37`: "[ADR-0028](../docs/adr/0028-no-changed-line-limit.md)" → "[ADR-0035](../docs/adr/0035-no-changed-line-limit.md)"
   - `00-OVERVIEW-AR.md:348` and `00-OVERVIEW-AR.md:382`: "`adr/0028`" → "`adr/0035`"
2. **Optional.** `process/06-review-and-merge.md` §2 has no "reviewable size" item. That is consistent with hub rule 5, because process/04 §4 is the single source. No change is needed.

## BUILD/V1 (origin/build/v1)

### A. Gate spec and plan

Every item below is fixed on B-552 (48420c1), which is not merged yet:
- `tools/eng-dev-gate/docs/specs/0001-eng-dev-gate-0.1.md`
  - :87 (AC11) "above `max_changed_lines` gives GC009" → GC009 is a notice with the sum, the estimate and the largest files, never a failure.
  - :98 "diff budget" → "counted lines".
  - :100 (AC13): remove "a task exceeds the size cap" from the GC005 list.
  - :377 (step 7): "is GC009 ("BLOCKED, propose a plan change", rule A22)" → notice, never a failure.
  - :381 (step 8): remove "the size cap `limits.max_task_lines` (initially 400 ...)".
  - :839: remove `max_task_lines` from `limits.{...}`.
  - :857 code table: "009 budget" → "009 notice: counted lines".
- `tools/eng-dev-gate/docs/plans/0001-eng-dev-gate-0.1.md:717` "one pull request of at most about 400 changed lines" → the estimate is never a limit.

Still open on B-552:
- `docs/plans/0001-eng-dev-gate-0.1.md:763` (prose describing T13), "scope globs and the budget" → "scope globs and the counted-lines notice". Optional.
- Spec traceability row (:915 on B-552) still names `::test_budget_counting`. Add or rename it to T40's `test_counted_lines_above_estimate_is_a_notice`.

### B. Gate code (B-553 / T40)

- `tools/eng-dev-gate/src/eng_dev_gate/checks/gate_check.py`
  - :1 docstring "file scope and diff budget" → "file scope and the counted-lines notice".
  - :225-252 `_budget`: the error branch `if total > task.max_changed_lines: ... _error("GC009", "... exceed max_changed_lines ... (BLOCKED: propose a plan change) ...")` → always emit `Finding(code="GC009", severity=Severity.NOTICE, message=f"{total} counted lines (estimate max_changed_lines {task.max_changed_lines} of task {task.id}); largest: {names}")`. Rename it to `_counted`.
  - :226 docstring "exceed the task limit" → "report the counted lines".
  - :233 "notice, not a budget failure: binary file counts zero" → "binary file counts zero".
  - :256 docstring "scope and budget" → "scope and counted lines".
  - :272: `parse_plan(text, config.limits.max_task_lines)` → `parse_plan(text)`.
- `tools/eng-dev-gate/src/eng_dev_gate/frontmatter.py`
  - :118 `def parse_plan(text: str, max_task_lines: int)` → `def parse_plan(text: str)`.
  - :123: remove the `max_task_lines` argument from the docstring.
  - :133-134: remove the "max_changed_lines ... exceeds {max_task_lines}" problem.
  - :56 docstring: "``max_changed_lines`` counts lines" → "``max_changed_lines`` is an estimate in lines".
- `tools/eng-dev-gate/src/eng_dev_gate/config/gate_config.py:74,78`: remove `max_task_lines` from the `Limits` docstring and the field.
- `tools/eng-dev-gate/src/eng_dev_gate/checks/gate_check_docs.py`
  - :130: `parse_plan(t, config.limits.max_task_lines)` → `parse_plan(t)`.
  - :32 docstring "count against a budget" → "are counted".
- `tools/eng-dev-gate/src/eng_dev_gate/checks/risk_floor.py`
  - :132, :149, :163: remove the second `parse_plan` argument.
  - :187 docstring "(globs, line cap)" → "(globs)".
- `tools/eng-dev-gate/src/eng_dev_gate/checks/test_first.py:221`: remove the second `parse_plan` argument.
- `.gate/gate.yml:19-21`: remove `max_task_lines: 400` and the comment "max_task_lines: process/04 section 4." This is a protected path; the owner approval goes in the pull request body, as B-524 did.

### C. Gate tests (B-553 / T40)

- `tests/integration/test_gate_check.py:245-269` `test_budget_counting`: "over the limit is GC009" plus `assert (result.code, set(errors)) == (1, {"GC009"})` → expect exit 0, with GC009 as a notice that carries "11", "10" and the largest files.
- `tests/unit/test_frontmatter.py:15` (`CAP = 400`) and `:123-126` (`match="400"` for 401): remove; a task estimate of 401 or more parses.
- **`tests/integration/test_gate_check_docs.py:64`**: `({PLAN_PATH: plan_text(max_changed_lines=401)}, DOCS, "GC005", "401")` → remove the case or turn it into an "accepted" case. B-552's concerns list (item 4) misses this file. It sits under `tests/**`, so T40's globs already cover it, but T40's prose list should name it.
- Remove `max_task_lines: 400` from every fixture that has it:
  - `tests/unit/test_config.py:138` (assertion)
  - `tests/support/pullrequest.py:35`
  - `tests/support/toy.py:23`
  - `tests/integration/test_agents_drift.py:23`
  - `tests/integration/test_gate_root.py:35`
  - `tests/unit/test_gate_root.py:19`
  - `tests/unit/test_modes.py:30`
  - `tests/unit/test_review.py:24`
  - `tests/unit/test_workspace.py:14`

### D. Rendered AGENTS.md and the gate's purpose line (B-553 / T40, from the hub template)

- `AGENTS.md`, `packages/eng-contract/AGENTS.md`, `packages/eng-harness/AGENTS.md`, `packages/structural-codes/AGENTS.md`, `tools/eng-dev-gate/AGENTS.md`:
  - :44 "its files, its line budget, its session budget." → "its files and its session budget."
  - :55 "your file scope, your diff budget and the risk floor." → "your file scope and the risk floor; diff size is reported, never failed."
  - :72 "A22 exceeding the task budget." → "A22 exceeding the task's `max_sessions`."
  - :83-84 "(files, budget, tests) ... task, budget and \"done\"" → "(files, session budget, tests) ... task, session budget and \"done\"".
  - :86 "budget used" → "sessions used".
- `tools/eng-dev-gate/.gate/agents.yml:7` purpose, and the rendered `tools/eng-dev-gate/AGENTS.md:9`: "file scope and diff budget" → "file scope".
- `template-version` in `.gate/agents.yml:5`, `packages/eng-contract/.gate/agents.yml:5`, `packages/eng-harness/.gate/agents.yml:5`, `packages/structural-codes/.gate/agents.yml:5` and `tools/eng-dev-gate/.gate/agents.yml:5`: "sha256:3681a65820bf" → the new template hash. B-552 measured sha256:7a1a12af2a76.

### E. design/ copies of the hub (B-553 / T40)

Copy the hub text:
- `design/process/01-lifecycle.md`
  - :19 "files and budget" → "files, size estimate and session budget".
  - :60 → "`max_changed_lines` (an estimate, [04](04-implementation-rules.md) §4) and `max_sessions`".
  - :64-65 "and the diff stays within `max_changed_lines`." → "every changed file matches the task's globs. Diff size is reported, never failed ([04] §4)."
  - :101-102 "Each plan task has a budget (`max_changed_lines`, `max_sessions`). Exceeding it means `BLOCKED`..." → "Each plan task has a session budget (`max_sessions`). Exceeding it means `BLOCKED` and a plan update, never \"keep going\". Changed lines have no limit ([04] §4)."
- `design/process/04-implementation-rules.md:41` "At most about 400 changed lines ... Larger work is split by the plan." → the hub's §4 bullets: no limit (ADR-0035); the estimate is never a failure, never a reason to stop and never needs a plan amendment; reviewers may ask for a split as a finding, and size alone never blocks; a file outside `files` still needs an amendment.
- `design/process/08-agent-operating-rules.md`
  - :24 "budget (`max_changed_lines`, `max_sessions`)" → "session budget (`max_sessions`)".
  - :26 "budget" → "session budget".
  - :53 A22 → "Exceed the task's `max_sessions`. When it is reached, stop and report `BLOCKED` with a plan change proposal. Changed lines have no limit ([04] §4)".
  - :99 "budget used" → "sessions used".
- `design/process/11-repository-standard.md:77` "diff within budget" → "diff size reported as a notice, never failed".
- `design/process/README.md:25` "its files, its size budget, its session budget" → "its files and its session budget".
- `design/process/03-specs-and-design-review.md:23` "files and budgets" → "files, size estimates and session budgets".
- `design/process/09-tooling-map.md:17` "tasks, files, budgets" → "tasks, files, size estimates, session budgets".
- `design/process/templates/AGENTS.template.md:44, 55, 72, 83-84, 86`: same replacements as in D.
- `design/process/templates/implementation-plan.md:12`: add the comment "# estimate only; exceeding it is never a failure".
- `design/process/templates/pull-request.md:23` and `.github/pull_request_template.md:23`: delete "; within `max_changed_lines`" and add a Verification line: "Changed lines: {{counted}} (plan estimate `max_changed_lines`: {{n}}; informational)".
- `design/00-OVERVIEW-AR.md:358` "وأن حجم التعديل ضمن الميزانية | العمل خارج الخطة أو تقسيم التعديلات للتحايل" → "ويعرض عدد الأسطر المعدّلة للعلم فقط دون حدّ (`adr/0035`) | العمل خارج الخطة".
- `design/00-OVERVIEW-AR.md:402` "لا يتجاوز ميزانية المهمة (عدد الأسطر وعدد الجلسات)." → "لا يتجاوز عدد الجلسات المحدد للمهمة. ولا حدّ لعدد الأسطر المعدّلة منذ 2026-11-17 (`adr/0035`)."
- `design/docs/adr/0021-agent-agnostic-ci-enforced-process.md:3`: status line only, "amended by ... and ADR-0035 (no changed-line limit)". The body at :20 stays.
- `design/docs/adr/README.md`: add the 0035 row and the 0021 "amended by ADR-0035". Add the new file `design/docs/adr/0035-no-changed-line-limit.md`.

### F. Lead state in build/v1 (the lead updates these)

- `HANDOFF.md:61-62` "Stay inside the plan task's `files` and `max_changed_lines` (gate GC008, GC009; the task cap is 400 lines, GC005). A task that cannot fit is split by a reviewed plan amendment (lead decision D-12), never stretched." → "Stay inside the plan task's `files` (gate GC008). `max_changed_lines` is an estimate; GC009 only reports the counted lines (ADR-0035)."
- `HANDOFF.md:23` "(scope, budget, test-first; ..." → "(scope, test-first; ...".
- `BUILD-STATUS.md:576` D-12 "A task over its line budget is split by a plan amendment ... not given a budget above the ~400-line cap" → mark it "Superseded 2026-11-17 by the owner decision (ADR-0035): no line limit; reviewers may ask for a split as a finding."
- `docs/build/lead-playbook.md`: the copy of <lead>/PLAYBOOK.md, same line numbers. Apply the same edits as in the lead tooling section below, at lines 32, 37, 70, 78, 133-134, 230, 236, 240 and 321.
- `docs/build/build-lane-v35.workflow.js:80` "the gate rules GC005, GC008, GC009, GC016, TF008, RF001" → "the gate rules GC005, GC008, GC016, TF008, RF001 (GC009 is a notice)".
- `docs/build/build-lane-tail.workflow.js:92` "inside the task scope and budget" → "inside the task scope".
- `docs/build/plan-audit.workflow.js`
  - :5 "file lists, budgets, tests-first" → "file lists, tests-first".
  - :25: remove `'budget'` from the `kind` enum.
  - :28: remove "the new budget with the measurement behind it".
  - :57: remove criterion "(2) BUDGET ... A task above 380 expected counted lines must be split (the cap is 400) ...", or reword it to "estimates may be refreshed; never a split reason".
- `docs/build/build-lane-v34.workflow.js`: a historical copy; v35 replaces it. `docs/build/HANDOFF.md:35-37` says to keep v34 until B-553 merges. That is true for now, because the base gate fails GC009, but it is temporary and can be dropped once B-553 merges.

### G. Timing risks (code paths, not text)

- Per spec §4.16 and AC65, T40/B-553 is judged by the gate of its base commit. The old `_budget` still fails GC009 above T40's estimate of 260, and the old cap of 400 still applies to the plan.
- Expected T40 size is about 117 documents lines plus 60 to 90 code lines. Rendered AGENTS.md files are generated and do not count; design/ files do count. That leaves little room under 260. If the trial measures more, raise T40's estimate in B-552 before it merges, staying at 400 or below.
- Every other pull request opened before B-553 merges is still failed by GC009 above its estimate.

## LEAD TOOLING (list only, not edited)

### <lead>/PLAYBOOK.md

- :32 "Stay inside the plan task: only its `files` globs, at most its `max_changed_lines` counted lines. Counted lines = ..." → "Stay inside the plan task: only its `files` globs. Measure the counted lines (an estimate, never a limit: owner decision of 2026-11-17, ADR-0035). Counted lines = ..."
- :37 "If the task cannot fit its budget or needs a file outside its list, STOP and report `NEEDS_PLAN_AMENDMENT`" → "If the task needs a file outside its list (or more sessions than `max_sessions`), STOP and report `NEEDS_PLAN_AMENDMENT`".
- :55 "(`files`, `max_changed_lines`, ...)" → "(`files`, `max_changed_lines` as an estimate only, ...)". Optional.
- :70 "counted lines of budget" → "counted lines (and the plan estimate)".
- :78 "scope (files), budget (counted lines)," → "scope (files), the counted lines (information only: size is never a finding by itself, only a change that cannot be reviewed),".
- :133-134 "(counted lines of budget, the `test:` commit sha)" → "(counted lines with the plan estimate, informational; the `test:` commit sha)".
- :230 "stretch a task past its file list or its budget" → "stretch a task past its file list".
- :236 "every remaining task's `files`, budget, `tests_first` and `depends_on`" → "every remaining task's `files`, `tests_first` and `depends_on`".
- :240 "check the file list and the budget before writing everything, and stop early when the plan cannot hold the task" → "check the file list before writing everything, and stop early when the task needs a file outside it".
- :321 "a `max_changed_lines` number set from a measured count (never above 400)," → delete. An estimate no longer needs an amendment; if one is kept, write "an estimate refreshed from a measured count (optional)".
- Add a transitional sentence to section 1: "Until B-553 merges, the base gate still fails GC009 above the estimate; that is a gate defect being fixed, not a reason to split."

### <lead>/build-lane-v34.workflow.js

v35 already carries the replacements except :80, which still lists GC009 among the gate rules in v35 as well.
- :68 "measure the counted lines against the budget" → "measure the counted lines (an estimate only, never a limit: owner decision of 2026-11-17)".
- :69 "If the task cannot fit its budget or file list, return NEEDS_PLAN_AMENDMENT" → "If the task needs a file outside its file list, return NEEDS_PLAN_AMENDMENT".
- :80 "the gate rules GC005, GC008, GC009, GC016, TF008, RF001" → "GC005, GC008, GC016, TF008, RF001 (GC009 is a notice)". Also "inside its files and budget" → "inside its files".
- :81 "Check scope, counted lines against the budget," → "Check scope (the file list), the counted lines (information only: size is never a finding by itself, only a change that cannot be reviewed),".
- :89 "inside the task scope and budget" → "inside the task scope".
- :129 "inside the task scope and budget:" → "inside the task scope:". Also "cannot be fixed inside the task's files and budget" → "cannot be fixed inside the task's files".
- :137 "for correctness, scope and budget." → "for correctness and scope."
- :160 "inside the task scope and budget" → "inside the task scope".

### Other lead files with the same issue

- <lead>/build-lane-v35.workflow.js:80: GC009 is still in the gate-rules list; fix as in v34 :80.
- <lead>/build-lane-tail.workflow.js:92: "scope and budget" → "scope".
- <lead>/plan-audit.workflow.js
  - :3 "file lists, budgets," → "file lists,".
  - :23: remove the enum value 'budget'.
  - :26: remove "the new budget with the measurement behind it".
  - :55: remove "(2) BUDGET ... A task above 380 expected counted lines must be split (the cap is 400) ...".
- <lead>/tools/*: nothing to change. The 14400 there is a lock timeout.
