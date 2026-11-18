# B-556 per-change mutation gate

The gate returned `check: pass` and `mutation: pass` (exit 0) with notice `MU003`. Mutmut produced no mutants for the selected module. The notice means the gate result includes no mutation coverage for the decorated rule predicates and no mutation score. The focused rule tests separately exercise those predicates, including the drift boundary and failed-check reason.

| Item | Evidence |
|---|---|
| Worktree | `<worktrees>/b556` |
| Verified head | `9ff084d5217d52a34645c1a101356fbe9aad259b` |
| Integration ref at start | `origin/build/v1` at `cf56035beba8bf1cb0447a22dd4846fc1b7e9011` |
| Effective comparison base | `1ec7566c016aacf75c15aacb260435df44f23c67`, the merge base of the integration ref and the task head. The check's default resolver was used without a GitHub event override. |
| Selected changed module | `src/eng_harness/rules/edit_cycle.py` (R1), confirmed in the gate-generated `only_mutate` list. The changed workflow `_points.py` falls outside the configured R1/R2 module globs. |
| Completion | 2026-11-17 19:37:26 UTC |

The command ran once under `.lead/locks/gate.lock` from the task worktree.

```sh
UV_CACHE_DIR=<lead>/uv-cache \
UV_PYTHON_INSTALL_DIR=<lead>/python \
uv run eng-gate check --package eng-harness --only mutation
```

The gate log is `.lead/logs/b556-mutation.log`. The exit record is `.lead/logs/b556-mutation.exit`.

```text
mode: bootstrap
check: pass
  mutation: pass
    [notice] packages/eng-harness: MU003 mutation not run: nothing to mutate: mutmut produced no mutant
```
