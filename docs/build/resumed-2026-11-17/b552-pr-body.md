## Summary
Work-Item: B-552
Plan-Task: none (spec and plan)
Risk: r3

Documents amendment for the owner's decision of 2026-11-17 ("I want to get it done; remove the line-count limit"), recorded in the hub as ADR-0035 (hub branch `claude/pensive-volta-gcx0y9` at 49f43e0). The build copy is also cited as ADR-0035 (`design/docs/adr/0035-no-changed-line-limit.md`). `max_changed_lines` stays in plan front matter as an estimate only: going over it is never a failure, never a reason to stop and never needs a plan amendment. Unchanged: file scope (GC008), `max_sessions` (A22, left to review), test-first, the risk floor and every other check.

- Gate spec 0001: AC11 and §4.5 step 7 make GC009 a notice that gives the counted lines, the task's `max_changed_lines` (an estimate) and the largest files, and never a failure. AC13 and §4.5 step 8 drop the size cap. §5 drops `limits.max_task_lines`. In the §6 code table, GC009 now reads "notice: counted lines". AC12c says "counted lines" instead of "diff budget". The governing documents cite ADR-0035.
- Gate plan 0001: new task T40 (work item B-553) implements this: GC009 becomes a notice in `gate_check.py`; `parse_plan` loses its cap; `Limits` and the root `.gate/gate.yml` drop `max_task_lines`; the call sites in `gate_check.py`, `gate_check_docs.py`, `risk_floor.py` and `test_first.py` follow, along with the test fixtures and CHANGELOG. `tests_first`: `test_gate_check.py::test_counted_lines_above_estimate_is_a_notice` and `test_frontmatter.py::test_task_estimate_above_400_parses`. Estimate 260, `depends_on` [T4, T13, T14, T15, T16, T38]. In §2, the line "at most about 400 changed lines" becomes "an estimate, never a limit".
- Not in this pull request, by the gate's own rule: the `design/` copies of the hub text, the AGENTS template, the rendered `AGENTS.md` files with their `.gate/agents.yml` `template-version`, and the `max_changed_lines` box of `.github/pull_request_template.md`. Next to a spec or a plan, gate-check refuses every other file (GC010, AC12). A template change without its renders fails `agents drift` (AG003). The `none (hub documents)` reason accepts only `design/**`. These files are therefore in T40's file list. A trial of them (patch kept by the lead) gave 117 counted lines and `agents drift: pass`. Gate-check from the base gate root gave 25 GC010 findings when the trial and the spec and plan were combined. For this spec and plan alone it gave only `awaiting owner` notices.

## Acceptance criteria covered
| Criterion | Test(s) |
|---|---|
| none: documents only. Amended: AC11 (GC009 notice), AC12c (wording), AC13 (no size cap). New task T40 covers AC11 and AC13. Every criterion of spec 0001 stays covered by some task. | not applicable |

## Verification
Local gate: `uv run eng-gate check --package eng-dev-gate --skip mutation` gave `check: pass` at 48420c1 (lock, config, format, lint, types, forbidden, imports, ratchet, secrets, tests, docs-fresh, licenses, workflows all pass).
`uv run eng-gate test-first` gave `skipped (exempt: type docs)`.
`eng-gate gate-check` with `--gate-root` at the merge base and an event `Plan-Task: none (spec and plan)`, `Risk: r3` gave no error, only AW02, AW03 and AW08 (`awaiting owner`).
Checked by hand: the plan front matter parses as YAML (42 tasks; ids unique), T40's `max_changed_lines` (260) is within the cap of the base gate (400), and every trial file matches T40's globs (`PurePosixPath.full_match`).
Changed lines: 80 (plan estimate: none, documents amendment; informational).
Live acceptance needed before the next release: no.

## Engineering impact (R1)
None. No engineering content changes.

## Version impact
patch (documents only) · Changelog entry: not needed (the T40 implementation adds one)

## Self-review checklist
- [x] Only this change: gate spec 0001 and gate plan 0001. 80 counted lines (63 added, 17 deleted). No code.
- [x] No `test:` commit: this is a documents-only amendment.
- [x] Only the edits the owner's decision needs (D-28). Historical amendment notes in plans (for example B-020, B-056, B-089) record past measurements and stay as they are.
- [x] Plan front matter parses as YAML. Every acceptance criterion is covered. T40 is within the base gate's cap.
- [x] T40 carries an amendment comment naming B-552.
- [x] No secrets or personal paths.
- [x] `Assisted-by:` trailer on the commit.


Resumed-machine verification: `uv run eng-gate check --package eng-dev-gate --skip mutation` passed on 0200eebd; the attribution-only correction to 8cb72712 preserves that exact tree. The branch was pushed to origin at 8cb72712. Local CI has not run in this resumed session.

## Review

Round 1 (8cb72712; original writer head 48420c1)

Independent lead review of the full diff against origin/build/v1, the owner's decision of 2026-11-17, the saved writer report and line-limit sweep. Only the gate spec and plan change (80 counted lines). AC11 changes GC009 to an informational notice, AC13 drops the parsing cap, and T40 owns the implementation, all call sites, fixtures, protected gate configuration, process copies and generated agent instructions. File scope, test-first, risk floor and max_sessions remain mandatory. The implementation will still be judged by its base gate until B-553 merges; T40's estimate is 260, within that base's 400 cap. No code is in this documents change. `uv run eng-gate check --package eng-dev-gate --skip mutation` passed on 0200eebd in this machine; log: `.lead/logs/b552-resumed-check.log`.

Author findings: none. Lead notes: the historical hub ADR-0028 wording is stale after its renumbering to 0035; the PR description should use the current hub head 49f43e0. The existing traceability test name can remain if B-553 retains that test and adds the named new regression tests. The linked ADR-0035 arrives with T40, as explicitly planned to avoid GC010. No unrelated enforcement changes are authorized.

Verdict: APPROVE. Local CI on a real pull request's current head remains required before merge; it has not run in this resumed session.

Attribution correction before publication: the local merge commit was recreated as 8cb72712 with the agent identity; its tree equals the tested tree at 0200eebd. Published commits were not rewritten. This metadata-only correction does not change the reviewed diff.
