> Writer-stage evidence. Integration completed in PR #418. See [the integration report](b556-b562-integration.md).

# B-562 writer handoff

Candidate `cd9d190ae7ee3f2cc1e5a9ea71de379ae2c9e818`, tree `ea15394ca9236387494de597e86a7ef5cde939fa`, from reference `cf56035beba8bf1cb0447a22dd4846fc1b7e9011`. Branch `docs/b562-original-open-content-capability`. Risk `r1, r2, r3`. Documents stage, one writer session. Subject `docs(eng-harness): record the original-open content guarantee (B-562)` and sole trailer `Assisted-by: anthropic/claude`.

## Owner decision and scope

The owner approved an explicit, conservative opt-in on 2026-11-17. `ToolInfo.opens_model_without_writing(args)` defaults to false. The CSI adapter has the existing unchanged-content guarantee for its own pathless original open. The engine records a qualifying opt-in in the write-open attempt so old and unmarked journals retain conservative interpretation. Binding, units, approvals and in-flight recovery follow the write effect. The distinct change in model-content checks preserves earlier dirty state and actual writes. A matching completed EC1 copy and historical save are required before the original can leave the host-state check. Pending opens on lost or reopened bindings still use host-state recovery.

The tracked diff is exactly three files under `packages/eng-harness/docs`:

- `specs/0001-engine.md` specifies the port capability, journal compatibility, write-effect controls, host-state evidence and post-open lifecycle.
- `specs/0002-servers-and-adapters.md` pins the CSI behavior in AC52 and clarifies AC36's engineer outcomes and existing AC34 baseline choice.
- `plans/0002-servers-and-adapters.md` adds twelve files to T19a and records the implementation regressions. The arrangement preserves test-first commit `eeae76fe`, its named list, dependencies and the three-session allocation. The 380-line plan estimate is informational and predates the added scope.

Counted diff is 128 lines (113 additions and 15 deletions). No product source, tests, dependencies, engineering values, release artefacts or shared state files changed. The implementation scope came from the B-138 writer's source review and direct confirmation, including the private `Modes` replay seam. The B-138 implementation awaits integration of this amendment.

## Verification

- `uv sync --all-packages --locked` exited 0. It emitted two non-blocking `uv-build` range warnings. The shared environment uses CPython 3.14.10 and uv 0.13.6.
- The package gate `uv run eng-gate check --package eng-harness --skip mutation` exited 0 with `check: pass`. The output reports `tests: pass`, `docs-fresh: pass`, `licenses: pass` and `workflows: pass`. It reports an informational existing RT001 decrease in the gate package's noqa count. The gate started with the documents diff in the worktree. Source and tests were identical throughout, and the final docs were committed before the suite finished and `docs-fresh` ran. Log `<lead>/logs/b562-gate.log`.
- The gate front-matter parser accepted both spec/plan pairs. Criterion coverage passed, and T19a's only added criterion is AC52. Programmatic comparison checked the twelve exact file additions and the unchanged list of original files, `tests_first`, dependencies and session count.
- On exact candidate head, the base-installed documents gate reported `gate-check: awaiting-owner`, listing AW08 and AW03 only. The risk floor returned `risk-floor: pass`. Both used a local synthetic event, distinct from a GitHub pull request or a CI run.
- `git diff --check HEAD^ HEAD` passed. The tree is clean. Independent lead review approved the exact candidate in `<lead>/reports/b562-review.md`.
- Documents-only test-first exemption applies. Mutation, local CI, product trials and live host checks were outside this writer run.

## Handoff

Status `DONE` for the writer stage. Early task-branch push succeeded from a clean worktree. The remote ref `refs/heads/docs/b562-original-open-content-capability` resolves to `cd9d190ae7ee3f2cc1e5a9ea71de379ae2c9e818`. The PR body is `<lead>/pr/b562-body.md`. The registry title is `docs(eng-harness): define the conservative original-open capability and completion scope (B-562)`. Integration, local CI and merge remain with the lead.
