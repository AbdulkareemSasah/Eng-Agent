Round 1 (c4d0e566)

Reviewed the full diff `origin/build/v1...HEAD` in `<worktrees>/b560` against T23 in plan 0001 and the original B551 implementation branch (`origin/feat/b551-harness-et23-model-keys`). The diff changes only `packages/eng-harness/docs/plans/0001-engine.md`: it adds the existing `packages/eng-harness/tests/unit/test_ctx_basis.py` to T23's `files` list and records the collateral test and reason in the T23 narrative. The T23 budget (30), AC72, and test-first entry are unchanged. `git diff --check` is clean.

The amendment is justified: B551 widens `Preview.models` to `tuple[ModelHandle | str, ...]`, while the already-existing `test_preview_and_approval` reads `preview.models[0].revision` at line 120. The union no longer guarantees that member is a `ModelHandle`, so the test file is part of the necessary implementation scope; the plan note accurately describes retaining the supplied revision-2 handle check. This does not weaken or alter a test, add product scope, or change acceptance criteria.

Findings: none (author or lead).

Verdict: APPROVE.
