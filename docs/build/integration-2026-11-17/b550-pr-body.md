## Summary
Work-Item: B-550
Plan-Task: packages/eng-harness/docs/plans/0002-servers-and-adapters.md#T23
Risk: r1, r2, r3

The CSI host port opens the original from its model-key file mapping, binds it and records its units, so the following working copy uses the same owned instance. `CsiToolPort` accepts a key with no path through its opener and returns a `harness.run_output/1` success envelope; a path, missing key or missing opener returns the specified failure envelope. The host port's `visible` option controls and records every launch (spec 0002 §4.5.9, AC51).

## Acceptance criteria covered

| Criterion | Tests |
|---|---|
| AC51 | `tests/workflow/adapters/test_csi_open_original.py::test_open_original_then_working_copy`, `::test_open_refusals_are_envelopes`, `::test_visible_launch` |
| Revision compatibility | `tests/workflow/adapters/test_csi_revisions.py`, `test_csi_session_ops.py`, `test_csi_reopened.py` |

## Verification

All commands run with the lead's configured UV cache and Python install directories.

- Focused four-file adapter suite: PASS (25 tests; log `<lead>/logs/b550-focused-tests.log`).
- `uv run eng-gate check --package eng-harness --skip mutation`: PASS on `d032e673`, whose tree is identical to final HEAD `79302d00` (attribution-only correction); log `<lead>/logs/b550-gate.log`. All 13 requested steps passed; the existing RT001 notice reports a lowered noqa count in eng-dev-gate, with no task edit there.
- `uv run -q eng-gate test-first --base 2a2171ead9a727686afe671e7aec2209c61bd713 --head HEAD --title "feat(eng-harness): the CSI host port opens the original for the step 2 open and launches visible on request (B-550)"`: PASS on the same tested tree; log `<lead>/logs/b550-test-first.log`.
- `git diff --check`: PASS.

`uv run eng-gate check --package eng-harness --only mutation`: PASS on final HEAD under the shared gate lock, after test-first. None of the changed files matches the configured R1/R2 module globs; no mutants or numeric score, and no MU003 notice (logs `<lead>/logs/b550-mutation.log`, `b550-mutation-scope.log`). Independent lead review found no medium or high author findings. Local CI remains for the lead before merge. Live CSI host acceptance remains an owner-machine check; these tests use the synthetic CSI server.

## Engineering impact (R1)

No engineering output or numerical rule changes; no golden or verification-record change.

## Version impact

No version change; changelog entry added.

## Self-review checklist

- [x] Only plan 0002 T23: six changed files, all in its amended file list.
- [x] 77 counted lines of the frozen 80-line limit (CHANGELOG 1, `_hostport.py` 17, `_session_ops.py` 9, `_tools.py` 50; tests excluded).
- [x] First task commit remains `260e1d0e` (`test:`); published history preserved.
- [x] No dependencies, suppression, threshold or engineering constant added.
- [x] Contract error codes and neutral envelope kinds follow AC51.
- [x] The in-scope collateral revision test now asserts `INVALID_ARGUMENT`, `field=path`, a failure envelope and no host send, per the approved B-554 amendment.
- [x] No secrets, vendor binaries, client data or personal paths committed.
- [x] Continuation commits use the agent author and committer and carry only `Assisted-by: anthropic/claude`.

Written by a subagent of the lead. Reviewed task branch fast-forward pushed at `79302d00953686dea66e21d671cc17a0fc242553` after the lead lifted the push hold. No PR, local CI or merge yet.

## Review

- Written by a subagent of the lead.

Round 1 (d032e673; original implementation e65e608)

Independent lead review of every changed file against plan 0002 T23, spec 0002 AC51 and section 4.5.9, and the B-554 scope amendment. The continuation preserves the published test-first history, merges build/v1 and applies the saved collateral test patch. The 77 counted lines remain below the old gate's estimate of 80. The host port opens the mapped original, reuses only a live owned instance through CsiSession, records binding and expected units, and propagates visible to every launch and its recorded state. The tool port's pathless open calls the opener then binder and emits the specified stored success envelope. Explicit paths, absent file keys and absent opener wiring follow the failure-envelope route; no write-ledger entry is produced. Existing revision opens keep the direct superclass route. The three workflow tests exercise actual synthetic server processes, success state, reuse, refusals and visibility. The collateral test retains the refusal assertion while adopting the explicitly amended envelope contract. No engineering constants or oracle changes.

Author findings: none. Lead consistency note: the spec's host-port mapping table says open_original returns HostInstance, while the implementation and typed opener return the source Path to obtain the envelope's base filename. AC51 and the detailed opening paragraph work with this implementation; queue a narrow spec clarification rather than expand this code task. Live Windows behavior remains owner acceptance, not established by the synthetic tests. Gate, test-first and per-change mutation results are recorded by the writer separately; local CI on a real PR remains required.

Verdict: APPROVE for d032e673; any source repair needs another review.

Final attribution-only continuation head: 79302d00953686dea66e21d671cc17a0fc242553. Its tree is identical to d032e673 (fa00da11223194644f8bc52b76cb01f6d4847c18), so the review also approves this head. The original published commits remain ancestors and were not rewritten. The focused 25 tests, package gate without mutation and test-first passed; the mutation command passed with zero eligible changed R1/R2 modules, no generated mutants and no numeric score. The task branch was pushed fast-forward. No real PR local CI or merge has occurred.

## Local CI

Local CI in the build container (lead decision D-23): **PASS** on head 6eda5f5 against base f538973, pull_request mode, finished 2026-11-17T10:53:39Z.

| Job | Result | Seconds |
|---|---|---|
| setup | pass | 3 |
| gate-check | pass | 1 |
| risk-floor | pass | 1 |
| test-first | pass | 14 |
| agents-drift | pass | 0 |
| ci-review | pass | 0 |
| security | pass | 0 |
| build | pass | 1 |
| gate | pass | 645 |

Mutation step: not run in this pull request run (owner decision of 2026-11-15); it runs on build/v1 after every ten merges

Not run in the container: the dependency audit (`uv audit --locked`; api.osv.dev is outside AGENTS.md section 9 and denied by the network policy) and the windows job (no Windows here). Both are owner local-test items (LOCAL-TESTING.md).

Clarification: the dependency audit remains unrun because AGENTS.md section 9 does not authorize api.osv.dev; the generated network-policy wording above is historical. The Windows job remains unrun on this Linux machine. Both remain owner local-test items.
