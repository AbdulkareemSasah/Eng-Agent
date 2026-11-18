# B-550 writer handoff

Status: DONE (writer scope). Early task-branch push completed after the lead lifted the hold. This resumed session created no PR, ran no local CI and performed no merge; current PR-list status is unverified. B-138 was not started.

- Task: plan 0002 T23, spec 0002 §4.5.9 / AC51; risk r1, r2, r3; frozen budget 80 counted lines.
- Worktree: `<worktrees>/b550`.
- Branch: `feat/b550-harness-st23-open-original-visible-launch`, tracking the actual published origin task branch.
- Final HEAD and actual pushed HEAD: `79302d00953686dea66e21d671cc17a0fc242553`.
- Push: fast-forward `e65e6080..79302d00` to the same task branch, exit 0; `.lead/logs/b550-push.log`.
- Compared base: `2a2171ead9a727686afe671e7aec2209c61bd713` (`origin/build/v1` merged, including B-554).
- First task test commit preserved: `260e1d0e`; published implementation `e65e6080` remains an ancestor.
- New continuation merge: `b5fdbb0c39c6f4bebbe1da5bf07b644aaa3cfad6`; final collateral test commit: `79302d00953686dea66e21d671cc17a0fc242553`. Both use agent author/committer and only `Assisted-by: anthropic/claude` trailer.

## Completed

Created the worktree from the published B-550 branch, merged the saved origin/build/v1 tip, preserved both sides of the sole CHANGELOG conflict, inspected and applied the saved collateral revision-test patch. No source changes to the published implementation were necessary. The in-scope collateral test now asserts the AC51 failure envelope for a named path, including INVALID_ARGUMENT, field=path and no send to the host. All other tests are preserved. Completed the PR body at `.lead/pr/b550-body.md` from the saved draft.

## Verification

All uv commands used `UV_CACHE_DIR=<lead>/uv-cache` and `UV_PYTHON_INSTALL_DIR=<lead>/python`. Synced once with `uv sync --all-packages --locked` (exit 0), no dependency or lock-file change.

1. Focused suite over `test_csi_open_original.py`, `test_csi_revisions.py`, `test_csi_session_ops.py`, `test_csi_reopened.py`: exit 0; 25 test progress dots, [100%]. Log: `.lead/logs/b550-focused-tests.log`.
2. `uv run eng-gate check --package eng-harness --skip mutation`: exit 0; `check: pass`, all 13 requested steps pass, including types, tests and their coverage enforcement. Only pre-existing RT001 notice: tools/eng-dev-gate noqa count fell 19 to 18; task did not edit the ratchet. Log: `.lead/logs/b550-gate.log`.
3. `uv run -q eng-gate test-first --base 2a2171ead9a727686afe671e7aec2209c61bd713 --head HEAD --title "feat(eng-harness): the CSI host port opens the original for the step 2 open and launches visible on request (B-550)"`: exit 0; `test-first: pass`. Log: `.lead/logs/b550-test-first.log`.
4. After those checks, fixed attribution on ONLY unpublished continuation commits at the lead's request. Package gate and test-first ran on `d032e673`; final `79302d00953686dea66e21d671cc17a0fc242553` has exactly the same tree `fa00da11223194644f8bc52b76cb01f6d4847c18`, proved by `git diff --exit-code` and `.lead/logs/b550-tree-equivalence.log`. No repeated full gate needed for attribution-only changes (lead instruction).
5. `uv run eng-gate check --package eng-harness --only mutation`: exit 0, `check: pass`, `mutation: pass`, run sequentially under `.lead/locks/gate.lock` on final HEAD. Changed R1/R2 module selection is empty. No mutants were generated, no numeric score applies, no MU003 was emitted. Logs: `.lead/logs/b550-mutation.log`, `.lead/logs/b550-mutation-scope.log`. One initial CLI invocation used unsupported `check --base`; corrected after reading help, preserving error log `b550-mutation-invocation-error.log` (exit 2, no test failure).
6. `git diff --check`: exit 0. Final working tree clean. No state files edited. No pause marker was present before starting each stage.

The complete relevant command ledger is `.lead/logs/b550-commands.md`; full saved diff `.lead/logs/b550-diff.patch`; measured numstat `.lead/logs/b550-numstat.log`.

## Scope and count

Six files, 258 additions and 26 deletions overall (284 changed lines), of which 207 changed lines are tests and excluded by the frozen gate. **77 counted lines / 80**.

| File | Additions | Deletions | Counted |
|---|---:|---:|---:|
| `packages/eng-harness/CHANGELOG.md` | 1 | 0 | 1 |
| `packages/eng-harness/src/eng_harness/adapters/_hostport.py` | 14 | 3 | 17 |
| `packages/eng-harness/src/eng_harness/adapters/csi/_session_ops.py` | 5 | 4 | 9 |
| `packages/eng-harness/src/eng_harness/adapters/csi/_tools.py` | 36 | 14 | 50 |
| `packages/eng-harness/tests/workflow/adapters/test_csi_open_original.py` | 197 | 0 | excluded |
| `packages/eng-harness/tests/workflow/adapters/test_csi_revisions.py` | 5 | 5 | excluded |

All six files are in amended T23 scope. Full touched files read. No new source/config/dependency, no suppressed or weakened checks, no test deleted/skipped or changed engineering expected value.

## Review, remaining work and risks

The lead's independent full-diff review found no author medium/high findings. Lead consistency note for later spec cleanup: the spec §4.5.9 table says open_original returns HostInstance while the published implementation and its typed opener seam return Path; detailed Opening original behavior and T23 prose are met. The lead directed no code expansion here.

No live CSI host was driven; owner-machine acceptance remains. B-138 will wire the production binder/opener and visible option in build_ports, as planned; it was not started. The lead explicitly lifted the push hold after review and checks. The remote task head was confirmed at e65e6080, then the task branch was fast-forward pushed to 79302d00 with no published-history rewrite. This resumed session did not attempt a PR; the lead still must list open PRs after API access is available, then decide whether to create a PR and run local CI on its current head before merging. No local CI or merge is claimed by this report.
