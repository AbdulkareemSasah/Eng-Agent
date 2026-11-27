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

- Focused four-file adapter suite: PASS (25 tests; log `.lead/logs/b550-focused-tests.log`).
- `uv run eng-gate check --package eng-harness --skip mutation`: PASS on `d032e673`, whose tree is identical to final HEAD `79302d00` (attribution-only correction); log `.lead/logs/b550-gate.log`. All 13 requested steps passed; the existing RT001 notice reports a lowered noqa count in eng-dev-gate, with no task edit there.
- `uv run -q eng-gate test-first --base 2a2171ead9a727686afe671e7aec2209c61bd713 --head HEAD --title "feat(eng-harness): the CSI host port opens the original for the step 2 open and launches visible on request (B-550)"`: PASS on the same tested tree; log `.lead/logs/b550-test-first.log`.
- `git diff --check`: PASS.

`uv run eng-gate check --package eng-harness --only mutation`: PASS on final HEAD under the shared gate lock, after test-first. None of the changed files matches the configured R1/R2 module globs; no mutants or numeric score, and no MU003 notice (logs `.lead/logs/b550-mutation.log`, `b550-mutation-scope.log`). Independent lead review found no medium or high author findings. Local CI remains for the lead before merge. Live CSI host acceptance remains an owner-machine check; these tests use the synthetic CSI server.

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

Written by a subagent of the lead. Reviewed task branch fast-forward pushed at `79302d00953686dea66e21d671cc17a0fc242553` after the lead lifted the push hold. This resumed session did not create a PR or run local CI; the current PR list could not be refreshed.
