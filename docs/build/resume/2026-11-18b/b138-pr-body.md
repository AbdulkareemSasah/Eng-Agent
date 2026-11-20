## Summary
Work-Item: B-138
Plan-Task: packages/eng-harness/docs/plans/0002-servers-and-adapters.md#T19a
Risk: r1, r2, r3

`build_ports` wires the CSI adapter (ETABS) into the engine ports inside the async `AdapterPorts` lifetime: the production binder, one written-items book shared by both ports, the pre-image on a reconciled write (opt-in `record_pre_image`), `ToolPort.preview` (no binding read for an unbound open), the CSI reconciler and host read-back with the frozen run-basis tolerance `checks.readback_relative_tolerance_ratio` (no fallback), the run's `Revisions` and `reopened`, the host's `open_original` as opener, `visible`, the route-aware allowlist loader, and a guarded reload that attaches the server only to a cached process whose identity is still live. `[cli_tools.*]` entries are refused with `NOT_IMPLEMENTED` (gap H-G8), which the command line maps to exit 2. Under amendment B-562 (AC52) the engine records the CSI original-open guarantee (`ToolInfo.opens_model_without_writing`, true only for a pathless `csi_open_model`) as the strict optional `step_started` field `opens_model_without_writing`: that open keeps its write effect but leaves the dirty flag as it was; an open confirmed `applied` during its call, or replayed without its binding, binds the model, reads its units and takes the EC1 copy; and the resume host-state check compares actual writes only, skipping the unloaded original only on the journaled EC1 handoff. The edit-cycle step sequence and the six-write AC36 crash matrix (SIGKILL of the real engine, resume with new ports) run against real synthetic-server processes; no host program is driven.

## Acceptance criteria covered
| Criterion | Test(s) |
|---|---|
| AC9 (engine clause) | `tests/workflow/servers/test_session.py::test_build_mismatch_stops_run` |
| AC22 | `tests/workflow/adapters/test_units_after_timeout.py::test_units_trap` |
| AC36 | `tests/workflow/test_csi_cycle.py::test_cycle_steps`; `tests/replay/test_csi_resume.py::test_crash_matrix` (cuts after `csi_open_model`, both section setters, `csi_save_model`, `csi_run_analysis`, `csi_design_run`: adapter `applied` with evidence for the setters, the engineer's `engine.in_flight` decision for the open, the save and the two long tools, the AC34 `accept` baseline for the save without read-back evidence; one logical call per cut, one attempt, only `m@copy` checked) |
| AC41 | `tests/workflow/test_build_ports.py::test_allowlist_loaded_for_route` |
| AC43 (interim refusal, H-G8) | `test_build_ports.py::test_cli_tools_not_wired_gap`; `tests/unit/cli/test_exit_codes.py::test_error_codes` (`NOT_IMPLEMENTED` -> 2) |
| AC44 | `test_build_ports.py::test_readback_tolerance_from_run_basis` |
| AC45 | `test_build_ports.py::test_csi_wiring_shares_book_and_pre_image`, `::test_csi_preview_sends_no_write`, `::test_binder_from_host_port`, `::test_open_preview_without_binding` |
| AC47 (reload, stale PID) | `test_build_ports.py::test_preflight_attaches_only_to_live_cached_identity` (dead, reused, live) |
| AC52 | `tests/workflow/adapters/test_csi_revisions.py::test_only_the_pathless_original_open_changes_no_model_content`; `tests/unit/test_journal_events.py::test_open_capability_is_a_strict_optional_marker`, `::test_open_capability_only_on_a_tool_write_open`, `::test_a_legacy_step_started_payload_is_unchanged`; `tests/unit/test_engine_edit_cycle_amendments.py::test_content_free_open_skips_only_its_own_dirty_mark`, `::test_immediately_applied_open_binds_and_copies`, `::test_replayed_open_binds_before_the_live_copy`; `tests/replay/test_host_state.py::test_the_ec1_handoff_needs_its_whole_journal_proof` (16 cases), `::test_content_writes_leave_out_only_resolved_content_free_opens`, `::test_a_later_content_free_open_keeps_the_earlier_write_as_the_comparison`, `::test_a_pending_content_free_open_on_a_lost_model_still_needs_recovery`, `::test_after_the_handoff_the_copy_is_still_checked`; the cycle and crash matrix above |

## Verification
CI run: local CI by the integrator.
- `uv run eng-gate check --package eng-harness --skip mutation`: `check: pass` (head 5991420, after merging `origin/build/v1` at 51d9573 with B-555, B-164 and B-564; earlier run at da18e9f: 2055 tests passed)
- `uv run -q eng-gate test-first --base 51d9573 --head HEAD --title "<title>"`: `test-first: pass` (head 5991420; first `test:` commit eeae76f)
- Mutation step: not run for this change. The run started at da18e9f was lost in the machine restart of 2026-11-18 before it produced a result, and plan T19a does not set `mutation: true` (playbook section 9 item 5: no per-task mutation run; the periodic mutation run every ten merges covers the changed modules).
Live acceptance needed before the next release: yes, `docs/local-testing.md` item 26 (owner's Windows host with real ETABS: the cycle, the build and units stops, the frozen tolerance after resume, the pre-image, a snapshot restore, the original-open handoff and the kill/resume cuts).
Changed lines: 478 counted (plan estimate `max_changed_lines`: 380; informational, owner decision of 2026-11-17)

## Engineering impact (R1)
Golden diff report: no output change; no calc, golden case or engineering constant changes. The read-back tolerance is read from the run's frozen design basis (`checks.readback_relative_tolerance_ratio`) and is never defaulted; the 0.25 used by the tests is a synthetic engineer input of the fixture · Verification record: none (no calc changed)

## Version impact
minor · Changelog entry: added (two lines: the CSI wiring, the original-open capability)

## Self-review checklist
- [x] Only this plan task's change; files within the task's list (16 source and document files and 12 test files, all in the T19a list after B-562)
- [x] First commit is `test:` (eeae76f) with tests that fail without the change (the test-first check passed)
- [x] Principles P1 to P12 respected; no escape hatches; nothing from the forbidden list
- [x] Units, suffixes, bounds and error codes per the contract; neutral kinds for anything crossing packages
- [x] Every engineering constant cited; no literal thresholds in blocks or rules
- [x] Generated documents regenerated; human documents updated (CHANGELOG, `docs/local-testing.md` item 26)
- [x] No secrets, vendor binaries, client data or personal paths
- [x] `Assisted-by:` trailer on agent-written commits (the merge commit and every commit of sessions 1 to 4)
