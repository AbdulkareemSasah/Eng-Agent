# B-553 writer handoff

Status: DONE_WITH_CONCERNS (writer stage). Required package gate and test-first pass at current HEAD; integration is blocked by RF001, assigned to separate documents amendment B-561.

Worktree: `<worktrees>/b553`
Branch: `fix/b553-gate-gc009-notice`
Base: `d9c19fbddf59078bcd44ed4f7eee5f0806e70697` (B-552 #412 and B-560 #413 merged)
HEAD: `5d2b2549a4b9f5fd2303fde31f17366e572e0d40`
Pushed: origin/fix/b553-gate-gc009-notice at `5d2b2549a4b9f5fd2303fde31f17366e572e0d40` (fast-forward task-branch creation; no PR).
Sessions used: 1 of T40's 1.

## Scope and implementation

T40 only: GC009 always reports the count, estimate and largest three files as a notice; binary notices stay. `parse_plan(text)` has no size cap; the removed argument is removed from every production and test call site. `Limits.max_task_lines` and root `.gate/gate.yml`'s field/comment are removed. Strict positive integers, schema validation, dependencies, scope GC008, risk floor, max_sessions, test-first, other checks remain.

Applied `docs/build/b552-t40-documents-trial.patch`, including ADR-0035 and the hub process/template copies. Updated five agent configurations to template version `sha256:7a1a12af2a76`; ran official agent renders and supported drift command successfully. The patch preserves A23/A25 and existing document statuses. No dependencies, lock file, spec/plan, root state files, ops, suppressions or unrelated changes.

Owner authorized the changed-line limit removal and protected root gate configuration edit on 2026-11-17; PR body records this explicitly. Written by the delegated writer. Every commit is authored `Claude <noreply@anthropic.com>` and carries only `Assisted-by: anthropic/claude` as trailer.

Counted scope: **182 lines** against old-base enforced estimate **260**, cap **400**; **46 files**, every path matches T40. Measured with base `git diff --numstat -M`, using the base gate's test/generated/spike globs. Documents account for 117 counted lines; code/config/changelog account for 65. Largest counted files: ADR-0035 (39), gate_check.py (32), process/01 and agent template (13 each). Generated AGENTS and tests are excluded by unchanged base rules. Raw diff: 243 additions, 156 deletions. No hidden exclusion/bypass.

## Commits and red proof

- `75b5e8a97366df91bb2a556e16b2a41ce9b28aa4` — tests only: the two named T40 tests (four GC009 cases at 0,9,10,11 vs estimate 10; estimate parsing at 401 and 10000). All six failed on unchanged base production for the intended reasons: missing/error GC009 or `FrontMatterError` on estimates over 400. Log `<lead>/logs/b553-red.log`.
- `7d9e169e3c0c9ef3488cb7af6d82c8e6723fdddb` — implementation/documents and explicit updated expectations required by merged AC11/AC13.
- `5d2b2549a4b9f5fd2303fde31f17366e572e0d40` — shorten docstrings and retain normal-mode approval checks alongside the new GC009 notice.

Formal `uv run -q eng-gate test-first --base $(git merge-base origin/build/v1 HEAD) --head HEAD --title "fix(eng-dev-gate): GC009 reports the changed-line count as a notice; no cap on max_changed_lines (B-553)"` passed at current HEAD. Log `<lead>/logs/b553-test-first.log`:

```text
mode: bootstrap
test-first: pass
  test-first: pass
```

## Verification observed so far

`uv sync --all-packages --locked`: passed once in worktree with the prescribed UV cache/Python paths.

`uv run eng-gate agents render --all`: wrote all five managed AGENTS files.
`uv run eng-gate agents drift`: pass. Initial `agents drift --all` was rejected (unsupported option); corrected supported command passed.

Scoped integration gate-check/docs/risk-floor/test-first-selection and unit frontmatter/config run: 245 passed, 2 failed on old exact finding lists. Both were updated to include mandatory GC009 without weakening protected-path assertions; focused rerun 2 passed. Logs `<lead>/logs/b553-scoped.log`, `<lead>/logs/b553-scoped-fix.log`.

Initial required package gate at `7d9e169e` failed on two E501 docstrings and `test_normal_mode_never_awaits_in_gate_check` assuming errors only (776 passed, 1 failed). Fixed in `5d2b2549`; full-package ruff and that focused test pass (1 passed). Failure retained in `<lead>/logs/b553-check-initial-failed.log`. Required full `uv run eng-gate check --package eng-dev-gate --skip mutation` rerun **passed** at `5d2b2549a4b9f5fd2303fde31f17366e572e0d40`; `<lead>/logs/b553-check.log`:

```text
mode: bootstrap
check: pass
  lock: pass
  config: pass
  format: pass
  lint: pass
  types: pass
  forbidden: pass
  imports: pass
  ratchet: pass
    [notice] .gate/ratchet.json: RT001 tools/eng-dev-gate: noqa count fell from 19 to 18; run `ratchet --update`
  secrets: pass
  tests: pass
  docs-fresh: pass
  licenses: pass
  workflows: pass
```

The ratchet decrease is an informational notice; no baseline edit or suppression was added.

Old base enforcement at `d9c19fbd` using its own running gate package and `--gate-root .` against head `7d9e169e`:
- `gate-check`: success / awaiting owner, AW01/AW02/AW08/AW03 only. Complete count/scope accepted, no GC008/GC009/GC010 error. `<lead>/logs/b553-base-gate-check.log`.
- `risk-floor`: **FAIL RF001** floor `['r2', 'r3']` vs recorded `['r3']`; r2 is raised by `packages/eng-contract/.gate/agents.yml` and `packages/eng-contract/AGENTS.md`. `<lead>/logs/b553-base-risk-floor.log`.

## Mutation and remaining work

Mutation not run, as directed while the periodic primary gate owns the machine mutation lane. The unchanged eng-dev-gate package configuration has no `r1_modules` or `r2_modules`; standard per-change mutation selection is empty and no score is claimed. Changed production modules are `checks/gate_check.py`, `checks/gate_check_docs.py`, `checks/risk_floor.py`, `checks/test_first.py`, `config/gate_config.py`, `frontmatter.py`. Additional targeted mutation coverage requires a lead-selected scope; no package setting or dependency was changed to force it.

The lead reserved B-561 for a separate documents-only amendment adding r2 to gate plan 0001 and the mirrored spec risk set. Risk-floor is unchanged. After B-561 merges, merge latest build/v1 into this branch, set PR body `Risk: r2, r3`, rerun affected base metadata checks. Do not duplicate the package gate unless source changes or another required check exposes a problem. Independent lead review and enforcement verification, then actual PR/local CI/integration remain. Writer opens no PR and does not self-merge.

PR body: `<lead>/pr/b553-body.md` (complete template facts, explicit RF001 blocker, no Review/Local CI placeholders).
