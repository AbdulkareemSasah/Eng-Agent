# B-552 writer handoff (documents amendment, gate spec and plan T40)

Head: 48420c1 (pushed to origin/docs/b552-gate-line-count-estimate, fast-forward, new branch).
Gate: `uv run eng-gate check --package eng-dev-gate --skip mutation` -> `check: pass` at 48420c1 (log <lead>/logs/b552-check.log).
test-first: `skipped (exempt: type docs)`.
gate-check (base gate root at the merge base, event `Plan-Task: none (spec and plan)`, `Risk: r3`): no error; AW02, AW03, AW08 only.
Counted lines: 80 (spec 19+/16-, plan 44+/1-).

## Done
- Spec 0001: AC11 and §4.5 step 7: GC009 is a notice (counted lines, estimate, largest files), never a failure. AC13 and step 8: no size cap. §5: no `limits.max_task_lines`. §6: GC009 "notice: counted lines". AC12c: wording. Cites ADR-0035.
- Plan 0001: T40 (B-553) after T39, estimate 260, tests_first two tests, covers AC11 and AC13, depends_on [T4, T13, T14, T15, T16, T38]. Amendment paragraph. §2 opening sentence no longer states a 400-line limit.

## Not done here, and why (status NEEDS_PLAN_AMENDMENT)
Items (3) and (4) of the lead notes cannot be in this pull request:
- gate-check GC010 (AC12): a pull request that changes a spec or a plan may change nothing else. Trial: the combined change gave 25 GC010 findings.
- The `none (hub documents)` reason accepts only `design/**`, but the AGENTS template change needs its renders (`AGENTS.md` x5) and the new `template-version` in five `.gate/agents.yml` files. Without them, agents drift reports AG003.
- `.github/pull_request_template.md` fits no `none` reason (trivial excludes `.github/`).
So T40's `files` already list them: design/00-OVERVIEW-AR.md, design/docs/adr/{README.md, 0021-..., 0035-no-changed-line-limit.md}, design/process/**, .gate/agents.yml, */*/.gate/agents.yml, AGENTS.md, */*/AGENTS.md, .github/pull_request_template.md.
Trial of those files: <lead>/reports/b552-t40-documents-trial.patch (apply with `git apply` on 48420c1). It gave 117 counted lines and `agents drift: pass`. New template-version: sha256:7a1a12af2a76. The gate's purpose line in tools/eng-dev-gate/.gate/agents.yml drops "diff budget". Conflicts with build-only text were resolved by keeping A23 to A25, keeping the task-log wording of process README item 4, and amending the ADR README 0021 row to "ADR-0026, ADR-0028 and ADR-0035".
Alternative if the lead prefers: send design/** without the template as its own `none (hub documents)` pull request, and keep only the template, renders, agents.yml and PR template in T40.

## Risks and notes for B-553
- T40 is judged by the gate of its base, where GC009 still fails above max_changed_lines (260) and the cap is 400. Expected: about 117 documents lines plus about 60 to 90 code lines.
- Removing `max_task_lines` from `Limits` (extra=forbid) breaks every test fixture whose gate.yml string still carries it: support/pullrequest.py, support/toy.py, test_agents_drift.py, test_gate_root.py (integration and unit), test_modes.py, test_review.py, test_workspace.py, test_config.py:138. All are under tests/**.
- test_budget_counting (GC009 error) and the "400" case of test_plan_front_matter_rules change with AC11 and AC13 as amended. This is not a weakened test.
- ADR number: the hub numbers the decision 0028, but build/v1 already has ADR-0028 (build v1 here). The spec and plan cite design/docs/adr/0035-no-changed-line-limit.md, which does not exist until T40 (or a hub-documents pull request) adds it.
