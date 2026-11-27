Work-Item: B-551
Plan-Task: packages/eng-harness/docs/plans/0001-engine.md#T23
Risk: r1, r2, r3

## Summary
`Preview.models` takes `ModelHandle | str` and `ctx.promote` takes `ModelHandle | str` (a str is a model key); `_approvals.model_key` answers the key of either for the approval binding, the models of an inserted preview and the promotion (spec 0001 4.3.2, 4.9, AC72).

## Acceptance criteria
| AC | Test |
|---|---|
| AC72 | `tests/workflow/test_model_keys.py::test_preview_and_promote_take_a_key` |

## Verification
`uv run eng-gate check --package eng-harness --skip mutation`: see handoff (pending the collateral edit). Test-first check: pass.

## Engineering impact
None; no engineering value.

## Version impact
CHANGELOG line under Unreleased.

## Collateral test edits
`packages/eng-harness/tests/unit/test_ctx_basis.py`, 1 line: the type of `Preview.models` is now a union, so the assertion compares the handle instead of reading `.revision`.

## Self-review
Counted lines 23 of 30; test commit bfafa63.
