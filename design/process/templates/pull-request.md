## Summary
Closes #{{issue}}
Plan-Task: docs/plans/{{plan file}}#T{{n}}
Risk: {{r0 | r1 | r2 | r3}} (from the plan)

{{What changed and why, in two to four sentences.}}

## Acceptance criteria covered
| Criterion | Test(s) |
|---|---|

## Verification
CI run: {{link}} (the gate, `gate-check`, `risk-floor`, `test-first`, CI reviewers)
Live acceptance needed before the next release: {{yes, which scripts and host versions / no}}
Changed lines: {{counted}} (plan estimate `max_changed_lines`: {{n}}; informational)

## Engineering impact (R1)
Golden diff report: {{link or "no output change"}} · Verification record: {{link}}

## Version impact
{{patch / minor / major}} · Changelog entry: {{added / not needed}}

## Self-review checklist
- [ ] Only this plan task's change; files within the task's list
- [ ] First commit is `test:` with tests that fail without the change
- [ ] Principles P1 to P12 respected; no escape hatches; nothing from the forbidden list
- [ ] Units, suffixes, bounds and error codes per the contract; neutral kinds for anything crossing packages
- [ ] Every engineering constant cited; no literal thresholds in blocks or rules
- [ ] Generated documents regenerated; human documents updated
- [ ] No secrets, vendor binaries, client data or personal paths
- [ ] No task-log content and no `tasklog/` path (A24, GC017)
- [ ] `Assisted-by:` trailer on agent-written commits

## Progress and handoff
{{Done so far, what is left, risks, sessions used of max_sessions. Updated at the end of every session.}}
