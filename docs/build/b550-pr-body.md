Work-Item: B-550
Plan-Task: packages/eng-harness/docs/plans/0002-servers-and-adapters.md#T23
Risk: r1, r2, r3

## Summary
The CSI host port opens the original for the step 2 open (`open_original`), `csi_open_model` with a key and no path is answered by the tool port through its `opener` as a success envelope, and `visible` makes every `csi_launch` visible (spec 0002 4.5.9, AC51).

## Acceptance criteria
| AC | Test |
|---|---|
| AC51 | tests/workflow/adapters/test_csi_open_original.py (3 tests) |

## Verification
`uv run eng-gate check --package eng-harness --skip mutation`: see handoff note (pending plan amendment: budget 80, test_csi_revisions.py collateral).

## Engineering impact
None (no engineering content).

## Version impact
CHANGELOG line, no version change.

## Self-review
- Counted lines: 77 of 60 (amendment proposed)
- test: commit 260e1d0
