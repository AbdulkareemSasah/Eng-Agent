# B-551 resumed writer handoff

Status: DONE for this resumed writer; ready for lead-scheduled mutation and integration. Package gate and test-first passed, lead independent review approved, task branch pushed.

Branch: `feat/b551-harness-et23-model-keys`
Worktree: `<worktrees>/b551`
Head: `b55b965b0d979b57d1751c07a4403bc74493047d`
Merged base: `d9c19fbddf59078bcd44ed4f7eee5f0806e70697` (`origin/build/v1`; includes B-560 #413 and B-552 #412).

## Change and history

The original implementation at published `2361039ffb3623fbf104f00a2571c41f67bb38d0` is preserved, including its failing-first test commit `bfafa63b753fff48d499b38e15bde820a0ae5c67`. This continuation fetched main/build/v1/task refs, restored the original branch in its task worktree, merged build/v1 at `611ac3be`, and kept both sides of the only conflict, the package changelog. No rebase, history rewrite or force push.

The follow-up at `b55b965b` changes only the B-560-authorized assertion in `tests/unit/test_ctx_basis.py`: compare `preview.models == (handle,)` rather than reading `.revision` on `ModelHandle | str`. The supplied revision-2 handle remains checked; the full tuple is now checked. No new source feature, contract decision, suppression, skipped test or engineering value was added. The existing B-551 changelog entry is kept once. New commits use Claude <noreply@anthropic.com> and only the `Assisted-by: anthropic/claude` trailer.

## Scope and budget

Full implementation diff reviewed before acting. Exactly seven task-scoped paths changed:

| Path under packages/eng-harness | Added | Deleted | Counted |
|---|---:|---:|---:|
| CHANGELOG.md | 1 | 0 | 1 |
| src/eng_harness/ctx.py | 1 | 1 | 2 |
| src/eng_harness/engine/_approvals.py | 7 | 2 | 9 |
| src/eng_harness/engine/_ctx_impl.py | 5 | 4 | 9 |
| src/eng_harness/engine/_modes.py | 1 | 1 | 2 |
| tests/unit/test_ctx_basis.py | 1 | 1 | 0 |
| tests/workflow/test_model_keys.py | 54 | 0 | 0 |

Counted additions plus deletions: **23 of 30**. Tests excluded under the playbook counting rule. T23's amended file list explicitly includes the collateral test. No state/ops files edited. Original plan session budget is one; this resumes the earlier writer following its documents blocker. Pause marker absent at start and before verification.

## Verification

Every uv command uses `UV_CACHE_DIR=<lead>/uv-cache` and `UV_PYTHON_INSTALL_DIR=<lead>/python`.

- `uv sync --all-packages --locked`: exit 0, once in resumed worktree; `<lead>/logs/b551-sync.log`.
- `uv run pytest packages/eng-harness/tests/workflow/test_model_keys.py packages/eng-harness/tests/unit/test_ctx_basis.py packages/eng-harness/tests/unit/test_promote.py -q`: exit 0, 14 passed (`.............. [100%]`); `<lead>/logs/b551-focused.log`.
- `git diff --check`: exit 0; working tree clean after committing the assertion.
- `uv run eng-gate check --package eng-harness --skip mutation`: exit 0, `check: pass` on head b55b965b; `<lead>/logs/b551-gate.log`. All steps passed. Existing unrelated RT001 notice: tools/eng-dev-gate noqa count fell 19 to 18; no ratchet edit made.
- `uv run eng-gate test-first --base $(git merge-base origin/build/v1 HEAD) --head HEAD --title 'feat(eng-harness): Preview.models and ctx.promote take a model key (B-551)'`: exit 0, `test-first: pass`; `<lead>/logs/b551-test-first.log`.
- `git push -u origin feat/b551-harness-et23-model-keys`: exit 0, fast-forward `2361039f..b55b965b`; exact pushed head is `b55b965b0d979b57d1751c07a4403bc74493047d`.

## Review and remaining work

Lead independently reviewed the full diff at b55b965b against AC72/T23/B-560 and reported APPROVE without findings: `<lead>/reports/b551-review.md`. This writer did not self-review for approval or integrate. No code changes requested by the lead; no redundant gate rerun scheduled.

Mutation has deliberately NOT run: the lead requested deferral while periodic mutation holds `gate.lock`, and will schedule the per-change mutation separately. No PR, local CI run, merge or state-file edit has been made by this continuation. Complete PR body: `<lead>/pr/b551-body.md`.

Package gate output tail:

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

Test-first output:

```text
mode: bootstrap
test-first: pass
  test-first: pass
```
