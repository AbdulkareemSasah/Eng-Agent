## Summary
Work-Item: B-560
Plan-Task: none (spec and plan)
Risk: r0

Add the existing `packages/eng-harness/tests/unit/test_ctx_basis.py` to engine plan 0001 T23 for the single assertion affected by widening `Preview.models` to `ModelHandle | str`. The plan explains that comparison with the supplied handle preserves the revision-2 check. T23's 30 counted-line budget, acceptance criteria and test-first entry remain unchanged.

## Acceptance criteria covered
| Criterion | Verification |
|---|---|
| Authorize the exact existing test needed by B-551 | T23 lists `packages/eng-harness/tests/unit/test_ctx_basis.py` and explains the assertion change. |
| Preserve existing scope constraints | Budget 30, max_sessions 1, covers AC72, tests_first and dependencies unchanged. |

## Verification
- `uv sync --all-packages --locked`: passed once, using the shared cache and Python installation directories.
- `uv run eng-gate check --package eng-harness --skip mutation`: exit 0, `check: pass` on the final committed tree (types, tests, docs-fresh and all other steps passed).
- Base-installed documents gate: `gate-check: awaiting-owner` (only bootstrap AW08/AW03); `risk-floor: pass`; `test-first: skipped (exempt: type docs)`.
- `git diff --check`: passed.
- No mutation run: documents-only change with no source or test edits.
- Independent review APPROVE and task-branch push confirmed at c4d0e566. This resumed session did not create a PR or run local CI; the current PR list could not be refreshed.
- Live acceptance needed before the next release: no additional live acceptance for this plan amendment.

## Engineering impact (R1)
No output change. No engineering constants, specifications, golden data or verification records changed.

## Version impact
No package version change. Changelog entry not needed for this documents-only scope amendment.

## Self-review checklist
- [x] Only the engine plan changed: 7 counted lines (6 additions, 1 deletion); T23 budget remains 30.
- [x] Test-first exemption: documents-only `Plan-Task: none (spec and plan)`; no code or tests changed.
- [x] Principles P1 to P12 respected; no escape hatches or forbidden tools introduced.
- [x] Units, suffixes, bounds and error codes unchanged.
- [x] No engineering constant introduced.
- [x] Human plan updated; no generated document affected.
- [x] No secrets, vendor binaries, client data or personal paths added to the tracked diff.
- [x] Commit c4d0e566 carries only `Assisted-by: anthropic/claude`.

## Review

Round 1 (c4d0e566)

Reviewed the full diff `origin/build/v1...HEAD` in `<worktrees>/b560` against T23 in plan 0001 and the original B551 implementation branch (`origin/feat/b551-harness-et23-model-keys`). The diff changes only `packages/eng-harness/docs/plans/0001-engine.md`: it adds the existing `packages/eng-harness/tests/unit/test_ctx_basis.py` to T23's `files` list and records the collateral test and reason in the T23 narrative. The T23 budget (30), AC72, and test-first entry are unchanged. `git diff --check` is clean.

The amendment is justified: B551 widens `Preview.models` to `tuple[ModelHandle | str, ...]`, while the already-existing `test_preview_and_approval` reads `preview.models[0].revision` at line 120. The union no longer guarantees that member is a `ModelHandle`, so the test file is part of the necessary implementation scope; the plan note accurately describes retaining the supplied revision-2 handle check. This does not weaken or alter a test, add product scope, or change acceptance criteria.

Findings: none (author or lead).

Verdict: APPROVE.

Branch pushed to origin at c4d0e566; local CI has not run.
