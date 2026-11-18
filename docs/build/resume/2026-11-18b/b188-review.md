# B-188 review (plan 0006 T14, branch feat/b188-harness-it14-commands-run-and-resume)

## Round 1 (097f0ce)

Reviewer: an independent subagent of the lead (did not write the change, edited nothing). Diff reviewed:
`git diff 66fe2c2 097f0ce` (merge base with origin/build/v1 = 66fe2c2), against plan 0006 T14 with every amendment
(B-342, B-412 reviews 1 to 9, B-510, B-541; B-536 and B-543 checked as belonging to T14c) and spec 0006 sections
4.1, 4.2.1 to 4.2.3, 4.4.8 and AC6, AC7, AC8, AC9, AC14, AC71.

What was checked:
- Scope: all 13 changed files are in T14's `files`; `pyproject.toml` unchanged (the `eng_harness.cli` public module
  already exists). No collateral edits.
- Counted lines (information only, owner decision 2026-11-17): 678 (672 additions, 6 deletions) against the plan
  estimate 380. The change stays reviewable: `_run.py` 305, `_wiring.py` 221, `__init__.py` 82, `_options.py` 68.
- Test-first: the first commit `3d1b123` (`test:`) holds only the eight `tests_first` tests and the helper
  `tests/helpers/cli_deps.py`; they fail at the base because `eng_harness.cli._wiring` does not exist and `HOST_LOCKED`
  maps to 70. `uv run eng-gate test-first --base 66fe2c2 --head HEAD --title "<prTitle>"`: `test-first: pass`.
- Tests rerun by the reviewer: `pytest tests/unit/cli tests/workflow/test_cli_run.py tests/replay/test_cli_resume.py
  tests/rules/test_cli_cannot_answer.py`: all pass; `ruff check` and `mypy --strict` on `cli/`: clean. Writer gate log
  `<lead>/logs/b188-gate3.log` at 097f0ce: `check: pass` (all steps). Pushed head on origin = 097f0ce.
- Acceptance criteria:
  - AC6: unknown workflow exits 3; unreadable, non-object and model-failing input exits 2; nothing created
    (`test_refusals_create_no_run`). The calc case is wired (preflight of a production run, refusal lists calc,
    status and code, exit 3) but see lead finding 1; the basis case is held as "not available in this build" (exit 2)
    until step 3 exists, see lead finding 2.
  - AC7: `run --json` with a page approval through a real page server exits 0, the journal ends `run_completed`, the
    report exists and stdout holds exactly the seven keys; the launch address never reaches a stream.
  - AC8: `--no-wait` exits 10 with the request title and the resume command, no address, no page served; `resume`
    answered on the page completes (fake engine, re-checked with the real engine by T17c as the plan says).
  - AC9 (T14 part): stop file removed when `Engine.start`/`Engine.resume` returns; a stale file removed at the start of
    `resume`, before the port builder; a file written after that removal is still seen by the engine.
  - AC14: `str`, `int`, `bool`, enum, `Literal` (and their optional forms) offered; float, nested model and list not
    offered; bad values and unknown options are usage errors.
  - AC71 (run and resume): ports entered before and left after the engine call, also when it raises; `ConfigError`
    from the port builder exits 2 printed as `main` prints it; `HOST_LOCKED` exits 4 (`_exit.py` entry beside
    `RUN_LOCKED`, so the B-138 `NOT_IMPLEMENTED` line merges cleanly); `LocalWorkspaceError` exits 2 with message and
    remedy, nothing created; `--input` read as `utf-8-sig`.
- Plan prose: engine factory default bound to the merged `Engine` (maps only the fields `EnginePorts` holds);
  `workflow_registry`, `port_builder`, `calc_port_factory` default `None` and the commands are then "not available in
  this build" (no stub); `calc_port_factory(config, workspace, store, run_class, clock, ids)` and
  `port_builder(config, workspace, store, run_folder, clock, ids)` as specified, `run_folder` = the run-id cell's
  `folder` that raises while empty; run-id cell filled from the first `ApprovalRequest.run_id` for `run` and at once
  for `resume`, `stop_requested` false and report "not available" while empty; `ReleaseMarks` from
  `[project_lane.*]`; `ExpectedTimes` built once; `basis_ref` `res_` + 26 zeros (Q23 interim); `--answers` refused
  until T14c; `resume` reads `run_class` from the run header before `Engine.resume`.
- Error codes and exit codes follow spec 4.2.3; input validation is identical to the engine's (`canonical_json` then
  strict `model_validate_json`). No engineering number, unit or tolerance is introduced; no check weakened; no
  suppression added. Commits carry only `Assisted-by: anthropic/claude`.

Author findings: none of severity high or medium.

Lead findings (non-blocking; a spec or plan must change, or a later task must know):
1. AC6 calc case is inert in production: `_run.py` calls `calc.preflight(())` because `WorkflowDef` declares no calcs
   and spec 4.2.2 step 4 does not say which calc ids are preflighted; `HarnessCalcPort.preflight(())` always returns
   no refusal. The test's `FakeCalc` ignores `calc_ids`, so it shows the plumbing, not the rule. Spec 0006 4.2.2 step 4
   (or engine `WorkflowDef`) needs a sentence naming the calc list; until then an unapproved calc is refused only at
   its step (spec 0003 AC11). The pull request's acceptance table should state this.
2. AC6 basis case has no owner: T14 covers AC6 but refuses a workflow with required basis fields as "not available in
   this build" (exit 2); T15 covers only AC47. T15's `covers` should add AC6 (missing required fields exit 3 with the
   paths) with a test.
3. Spec 4.1 says `cli` may import from `eng_harness.pages` only `PageServer`, the ports and `accept_answers_file`.
   `cli/_wiring.py` imports `_NO_REPORT` (pages/_ports), `PageSettings` (pages/_server), `approval_screens`,
   `sign_off_screens` (pages/_screens_approval) and `choice_screens` (pages/_screens_choice) from private modules,
   which the AC2 rules test does not see. No answer type is named, and without the builders the page shows only
   refusal pages, so the code is right; spec 4.1 (or a pages task exporting default screen builders and settings)
   should make this legitimate. `cli/__init__.py` also imports `CalcRefusal` from the private `eng_harness._calc._port`.
4. `eng_harness.cli.__all__` gains `CalcPortFactory`, `HostedPorts`, `PortBuilder`, `RunCalcPort`, `RunPorts`,
   beyond the public names of spec 4.1; add them to the table or keep them out of `__all__` in a later task.
5. Until T14b (AC70) `--workspace` reaches only the configuration lookup; the run's `Workspace` comes from
   `ENG_WORKSPACE` or the default probe. No production effect while the registry default is `None`.
6. Generated options: values go into the run input (replacing the file's field), so an options-model field absent
   from the input model is refused as "does not fit"; spec 4.2.1 does not say where option values go. They are not
   listed by `run --help` (`parse_known_args`), and a field named like a shared option (`mode`, `input`, `json`)
   would be taken by the shared parser silently. A spec sentence (refuse such names at option generation, as `task`
   already is) would close it.
7. The page's `report` callable raises `REF_NOT_FOUND` for a run with the Q23 placeholder; the page answers its
   generic failure. A fallback to the "not available" document on `ReportError`/`ContractError` would read better.

Verdict: APPROVE.
