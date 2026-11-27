# B-560 writer handoff

Status at checkpoint: writer DONE, independent review APPROVE, package gate PASS, task-branch push confirmed; PR/local CI/merge remain unverified or outstanding.

Branch: `docs/b560-engine-t23-collateral-test`
Worktree: `<worktrees>/b560`
Base: `2a2171ead9a727686afe671e7aec2209c61bd713` (`origin/build/v1` fetched before creation).
Head: `c4d0e56668d949a90fd9438203779a0a17025134`
Commit: `docs(eng-harness): scope T23 collateral preview test (B-560)`
Author and committer: agent identity. Only trailer: `Assisted-by: anthropic/claude`.

## Change and scope

Only `packages/eng-harness/docs/plans/0001-engine.md` changed: 6 additions and 1 deletion, 7 counted lines. Added exactly `packages/eng-harness/tests/unit/test_ctx_basis.py` to T23's files with a collateral note and a short explanation of the assertion in the implementation commit. T23's budget 30, session budget 1, AC72, tests_first and dependencies are unchanged. No spec, source, tests or state files changed. No engineering decision or constant was introduced. Risk r0: the only touched path matches no package or workspace risk-floor entry. Independent review is required under the owner's latest instruction; no mechanical exemption is claimed.

## Exact B-551 diagnosis and future edit

Read the full existing test file and the diff of `origin/feat/b551-harness-et23-model-keys` at `2361039ffb3623fbf104f00a2571c41f67bb38d0`. Its `Preview.models` changes from `tuple[ModelHandle, ...]` to `tuple[ModelHandle | str, ...]`. The existing `test_preview_and_approval` at `packages/eng-harness/tests/unit/test_ctx_basis.py:120` accesses `.revision` on the union, which mypy correctly rejects for `str`. This is a type-check failure; the handle case's intended runtime behavior is unchanged.

After B-560 merges and B-551 merges `origin/build/v1`, B-551 needs exactly:

```diff
-    assert preview.models[0].revision == 2
+    assert preview.models == (handle,)  # the handle, revision 2, as given
```

The test's handle is `ModelHandle(model_key="m", model_id=MODEL, revision=2)`. Equality to that supplied handle retains the revision assertion and checks the whole tuple. Keep this edit in the implementation commit; the existing test is already green at B-551's base and is not its failing-first test. The registry says the prior writer's trial with this exact edit produced `check: pass`; this session did not repeat a product-code trial or alter B-551. B-551 must rerun its package gate after applying it and receive its independent implementation review. Its code count remains 23 (test edits excluded); no budget increase is needed. Update B-551's PR body Collateral test edits and Verification sections with actual results.

## Verification

All uv commands used `UV_CACHE_DIR=<lead>/uv-cache` and `UV_PYTHON_INSTALL_DIR=<lead>/python`.

- `uv sync --all-packages --locked`: exit 0, run once in the new worktree.
- `git diff --check`: passed.
- `uv run eng-gate test-first --base origin/build/v1 --head HEAD --title 'docs(eng-harness): scope T23 collateral preview test (B-560)'`: exit 0, `test-first: skipped (exempt: type docs)` on final head.
- From the reference checkout, using its installed base gate: `uv run eng-gate --root <worktrees>/b560 --gate-root <build-v1> gate-check --event <lead>/pr/b560-event.json`: `gate-check: awaiting-owner`, only AW08 (identity approvals) and AW03 (G3 owner approvals), no scope or document errors. This is a local synthetic event, not a real PR or CI approval.
- Same command with `risk-floor`: `risk-floor: pass` on final head with Risk r0.
- Initial attempts from the worktree executable received CF009 (base-installed gate required, then executable location mismatch); corrected by using the reference checkout's gate as above. These rejected attempts did not change files or bypass checks.
- `uv run eng-gate check --package eng-harness --skip mutation`: exit 0, `check: pass` on the final committed tree; log `<lead>/logs/b560-gate.log`. The running command started before the unpublished identity correction; its working tree content remained identical throughout. Final HEAD is c4d0e56668d949a90fd9438203779a0a17025134. Output tail:

```text
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

The ratchet notice is existing unrelated bookkeeping, not a failing check; no ratchet edit made.
- No workspace-wide test run and no mutation run. The documents amendment changes no executable source or test.

## Left and risks

The task-branch push to origin is confirmed; independent review approved final head c4d0e566. This resumed session created no PR; current PR-list status is unverified, and local CI remains pending. The draft body used for review is in `b560-pr-body.md`. The pause marker was absent at start.
