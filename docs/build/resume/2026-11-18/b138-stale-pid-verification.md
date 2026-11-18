# B-138 persisted CSI process identity regression

Both runs selected `packages/eng-harness/tests/workflow/test_build_ports.py::test_preflight_attaches_only_to_live_cached_identity` through `uv run pytest`. The three variants simulate a dead process, a reused PID and a still-live identity.

## Test commit `6f609b0a`

The dead and reused cases attempted to attach to PID 4242 and failed the empty-list assertion. The still-live control passed.

```text
FAILED packages/eng-harness/tests/workflow/test_build_ports.py::test_preflight_attaches_only_to_live_cached_identity[dead]
FAILED packages/eng-harness/tests/workflow/test_build_ports.py::test_preflight_attaches_only_to_live_cached_identity[reused]
2 failed, 1 passed in 13.83s
```

## Fix commit `0a407606`

```text
...                                                                      [100%]
3 passed in 18.02s
```

This run verifies preflight attachment selection for these three cases. The complete committed matrix and final package verification remain open.
