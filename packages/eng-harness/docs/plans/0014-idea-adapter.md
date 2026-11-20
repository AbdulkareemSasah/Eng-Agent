---
id: plan-b090-idea-adapter
issue: "B-090"
spec: packages/eng-harness/docs/specs/0014-idea-adapter.md
status: draft            # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1, r2, r3]  # r3 from the public_modules entries in pyproject.toml (amendment B-356); r2 from the kinds (amendment B-453)
tasks:
  - id: T1
    title: The IDEA server section on the framework additions of plan 0002 T20 (routes, audit_log flag)
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.servers (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/servers/_config.py"
      - "packages/eng-harness/src/eng_harness/servers/_launch_args.py"
      - "packages/eng-harness/src/eng_harness/servers/_session.py"
      - "packages/eng-harness/tests/unit/servers/test_config.py"
      - "packages/eng-harness/tests/unit/servers/test_launch_args.py"
      - "packages/eng-harness/tests/workflow/servers/test_session.py"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/servers/test_config.py::test_idea_server_section"
      - "packages/eng-harness/tests/unit/servers/test_config.py::test_idea_forbidden_options"
      - "packages/eng-harness/tests/unit/servers/test_config.py::test_idea_service_url_loopback_only"
      - "packages/eng-harness/tests/unit/servers/test_config.py::test_idea_env_keys_refused"
      - "packages/eng-harness/tests/unit/servers/test_launch_args.py::test_idea_argv_has_no_audit_log"
      - "packages/eng-harness/tests/workflow/servers/test_session.py::test_idea_launcher_receives_no_audit_log"
    covers: [AC1]
    depends_on: []   # after plan 0002 T20 (framework additions, which follows its `_session.py` tasks T5 to T7), see section 3
  - id: T2
    title: Synthetic IDEA fake server (test-only), its faults and its schema check
    files:
      - "packages/eng-harness/tests/fakes/sasaah_idea/**"
      - "packages/eng-harness/tests/contract/test_idea_allowlist.py"
      - "packages/eng-harness/tests/unit/test_package_contents.py"
    max_changed_lines: 60
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/contract/test_idea_allowlist.py::test_fake_schemas_match_inventory"
      - "packages/eng-harness/tests/unit/test_package_contents.py::test_idea_fake_not_shipped"
    covers: [AC21]   # in part: the schema check; recordings come in T9
    depends_on: [T1]
  - id: T3
    # Amendment (B-584, documents only): AC3 workflow tests need ServerManager._verify to call expected.status_tool
    # (BuildExpectation.status_tool, default csi_status; IDEA idea_status) instead of the hardcoded csi_status, and to
    # name that tool in the error message; measured by the B-302 writer on
    # packages/eng-harness/src/eng_harness/servers/_session.py (not previously in T3's files).
    title: IDEA allowlist data (58 tools classified), argument models, pinned fingerprint, build-check items and unit header
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.idea, eng_harness.servers (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/idea/__init__.py"
      - "packages/eng-harness/src/eng_harness/adapters/idea/_allowlist.toml"
      - "packages/eng-harness/src/eng_harness/adapters/idea/_tools.py"
      - "packages/eng-harness/src/eng_harness/adapters/_allowlist.py"
      - "packages/eng-harness/src/eng_harness/servers/_buildcheck.py"
      - "packages/eng-harness/src/eng_harness/servers/_session.py"  # _verify calls expected.status_tool (BuildExpectation.status_tool) instead of hardcoded csi_status and names it in the error; AC3 (amendment B-584)
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py"
      - "packages/eng-harness/tests/unit/adapters/test_idea_args.py"
      - "packages/eng-harness/tests/unit/adapters/test_idea_units.py"
      - "packages/eng-harness/tests/unit/servers/test_buildcheck.py"
      - "packages/eng-harness/tests/contract/test_idea_allowlist.py"
      - "packages/eng-harness/tests/workflow/servers/test_session.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py::test_idea_entries_match_classification"
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py::test_idea_gap_and_not_served_refused"
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py::test_idea_run_script_refused"
      - "packages/eng-harness/tests/contract/test_idea_allowlist.py::test_against_inventory"
      - "packages/eng-harness/tests/contract/test_idea_allowlist.py::test_fingerprint_from_inventory"
      - "packages/eng-harness/tests/contract/test_idea_allowlist.py::test_unit_header"
      - "packages/eng-harness/tests/unit/servers/test_buildcheck.py::test_idea_status_flags"
      - "packages/eng-harness/tests/workflow/servers/test_session.py::test_idea_script_enabled_stops_run"
      - "packages/eng-harness/tests/workflow/servers/test_session.py::test_idea_listed_run_script_stops_run"
      - "packages/eng-harness/tests/unit/adapters/test_idea_args.py::test_confirm_only_under_approval"
      - "packages/eng-harness/tests/unit/adapters/test_idea_args.py::test_design_code_from_basis_only"
      - "packages/eng-harness/tests/unit/adapters/test_idea_units.py::test_declared_units_and_status"
    covers: [AC2, AC3, AC15, AC16]   # AC4, AC15 and AC16 in part: argument rules and the header; session ops, verdict labels and read-back follow in T5 to T7
    depends_on: [T1, T2]
  - id: T4
    title: Error mapping, timeouts and licensing outcomes
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.idea (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/idea/_errors.py"
      - "packages/eng-harness/tests/unit/adapters/test_idea_errors.py"
      - "packages/eng-harness/tests/unit/adapters/test_idea_timeouts.py"
      - "packages/eng-harness/tests/workflow/adapters/test_idea_license.py"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/adapters/test_idea_errors.py::test_mapping_table"
      - "packages/eng-harness/tests/unit/adapters/test_idea_timeouts.py::test_timeout_mapping"
      - "packages/eng-harness/tests/workflow/adapters/test_idea_license.py::test_refusal_maps"
      - "packages/eng-harness/tests/workflow/adapters/test_idea_license.py::test_hang_bounded"
    covers: [AC17, AC18, AC19]   # AC18 in part: the mapping; reconciliation is T8
    depends_on: [T3]
  - id: T5
    title: Replies, stub guard, harness kinds and the host-verdict mapping
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.idea, eng_harness.kinds and more (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/idea/_replies.py"
      - "packages/eng-harness/src/eng_harness/adapters/idea/_stub.py"
      - "packages/eng-harness/src/eng_harness/adapters/idea/_verdicts.py"
      - "packages/eng-harness/src/eng_harness/kinds/idea.py"
      - "packages/eng-harness/src/eng_harness/kinds/__init__.py"
      - "packages/eng-harness/tests/unit/adapters/test_idea_stub.py"
      - "packages/eng-harness/tests/unit/adapters/test_idea_verdicts.py"
      - "packages/eng-harness/tests/golden/test_idea_verdicts.py"
      - "packages/eng-harness/tests/property/test_idea_verdicts_props.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/adapters/test_idea_stub.py::test_stub_markers"
      - "packages/eng-harness/tests/golden/test_idea_verdicts.py::test_mapping_cases"
      - "packages/eng-harness/tests/property/test_idea_verdicts_props.py::test_no_status_upgrade"
      - "packages/eng-harness/tests/unit/adapters/test_idea_verdicts.py::test_set_properties"
      - "packages/eng-harness/tests/unit/adapters/test_idea_verdicts.py::test_host_only"
      - "packages/eng-harness/tests/unit/adapters/test_idea_verdicts.py::test_empty_is_precondition"
      - "packages/eng-harness/tests/unit/adapters/test_idea_verdicts.py::test_passed_disagreement"
      - "packages/eng-harness/tests/unit/adapters/test_idea_verdicts.py::test_code_label_and_assumptions"
    covers: [AC11, AC13, AC14, AC15]   # AC11 in part: the markers; the calls are T8
    depends_on: [T3]
  - id: T6
    title: Working copy, route preconditions, HostPort methods and gap entries
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.idea (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/idea/_session_ops.py"
      - "packages/eng-harness/src/eng_harness/adapters/idea/_gaps.py"
      - "packages/eng-harness/tests/workflow/adapters/test_idea_session_ops.py"
      - "packages/eng-harness/tests/workflow/adapters/test_idea_gaps.py"
    max_changed_lines: 350
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/adapters/test_idea_session_ops.py::test_working_copy_hash"
      - "packages/eng-harness/tests/workflow/adapters/test_idea_session_ops.py::test_out_path_new_and_distinct"
      - "packages/eng-harness/tests/workflow/adapters/test_idea_session_ops.py::test_no_path_outside_run_folder"
      - "packages/eng-harness/tests/workflow/adapters/test_idea_session_ops.py::test_rest_route_requires_live_project"
      - "packages/eng-harness/tests/workflow/adapters/test_idea_session_ops.py::test_service_unreachable_host_not_connected"
      - "packages/eng-harness/tests/workflow/adapters/test_idea_session_ops.py::test_native_route_requires_hidden_calculator"
      - "packages/eng-harness/tests/workflow/adapters/test_idea_gaps.py::test_create_project_gap"
      - "packages/eng-harness/tests/workflow/adapters/test_idea_gaps.py::test_set_loads_gap"
      - "packages/eng-harness/tests/workflow/adapters/test_idea_gaps.py::test_project_model_edits_gap"
    covers: [AC4, AC5, AC6]
    depends_on: [T4, T5]
  - id: T7
    # Amendment (B-593, documents only): AC10 rebind and the §4.10 check_model integrity set need IdeaHostPort.check_model
    # and the model-key rebind after a successful write in
    # packages/eng-harness/src/eng_harness/adapters/idea/_session_ops.py (not previously in T7's files; T6 left an INTERNAL
    # stub and a handoff). Measured by the B-306 writer and confirmed by its review (b306-review.md).
    title: Load map (unset), load plan, structure-preserving loading builder, set_loads, read-back and check_model
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.idea, eng_harness.kinds and more (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/idea/_load_map.toml"
      - "packages/eng-harness/src/eng_harness/adapters/idea/_loads.py"
      - "packages/eng-harness/src/eng_harness/adapters/idea/_checks.py"
      - "packages/eng-harness/src/eng_harness/adapters/idea/_session_ops.py"  # replace check_model stub with §4.10 integrity set from last set_loads (load-map status, zero-dropped, read-back mismatch or unavailable); rebind model key to out_path after successful write (AC10); amendment B-593
      - "packages/eng-harness/src/eng_harness/kinds/idea.py"
      - "packages/eng-harness/tests/fixtures/idea/load_map_synthetic.toml"
      - "packages/eng-harness/tests/unit/adapters/test_idea_loads.py"
      - "packages/eng-harness/tests/unit/adapters/test_idea_units.py"
      - "packages/eng-harness/tests/property/test_idea_loads_props.py"
      - "packages/eng-harness/tests/workflow/adapters/test_idea_loads.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/adapters/test_idea_loads.py::test_unconfirmed_map_gap"
      - "packages/eng-harness/tests/unit/adapters/test_idea_loads.py::test_synthetic_map_proceeds"
      - "packages/eng-harness/tests/unit/adapters/test_idea_loads.py::test_refs_resolved_converted"
      - "packages/eng-harness/tests/unit/adapters/test_idea_loads.py::test_literal_force_refused"
      - "packages/eng-harness/tests/unit/adapters/test_idea_loads.py::test_stale_ref_refused"
      - "packages/eng-harness/tests/unit/adapters/test_idea_loads.py::test_wrong_kind_refused"
      - "packages/eng-harness/tests/unit/adapters/test_idea_loads.py::test_only_force_fields_change"
      - "packages/eng-harness/tests/unit/adapters/test_idea_loads.py::test_unmapped_segment_refused"
      - "packages/eng-harness/tests/unit/adapters/test_idea_loads.py::test_percentage_forces_gap"
      - "packages/eng-harness/tests/unit/adapters/test_idea_loads.py::test_unknown_segment_refused"
      - "packages/eng-harness/tests/property/test_idea_loads_props.py::test_structure_preserved"
      - "packages/eng-harness/tests/unit/adapters/test_idea_units.py::test_read_back_loads_canonical"
      - "packages/eng-harness/tests/workflow/adapters/test_idea_loads.py::test_set_loads_writes_new_file"
      - "packages/eng-harness/tests/workflow/adapters/test_idea_loads.py::test_readback_mismatch_detected"
      - "packages/eng-harness/tests/workflow/adapters/test_idea_loads.py::test_zero_effect_dropped_warning"
      - "packages/eng-harness/tests/workflow/adapters/test_idea_loads.py::test_all_zero_loads_host_error"
    covers: [AC7, AC8, AC9, AC10, AC16]   # AC16 in part: the canonical read-back
    depends_on: [T6]
  - id: T8
    title: Calculation on both routes, host-verdict reads, reconciliation and the stub-refusal workflows
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.idea (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/idea/_calculate.py"
      - "packages/eng-harness/src/eng_harness/adapters/idea/_reconcile.py"
      - "packages/eng-harness/tests/workflow/adapters/test_idea_calculate.py"
      - "packages/eng-harness/tests/workflow/adapters/test_idea_reconcile.py"
    max_changed_lines: 350
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/adapters/test_idea_calculate.py::test_stub_refused_rest"
      - "packages/eng-harness/tests/workflow/adapters/test_idea_calculate.py::test_service_stopped_preflight"
      - "packages/eng-harness/tests/workflow/adapters/test_idea_calculate.py::test_live_create_fallback_offline_refused"
      - "packages/eng-harness/tests/workflow/adapters/test_idea_calculate.py::test_native_checks_to_verdicts"
      - "packages/eng-harness/tests/workflow/adapters/test_idea_calculate.py::test_native_errors_are_error_verdicts"
      - "packages/eng-harness/tests/workflow/adapters/test_idea_calculate.py::test_unexpected_shape_host_error"
      - "packages/eng-harness/tests/workflow/adapters/test_idea_calculate.py::test_zero_utilization_true_needs_engineer"
      - "packages/eng-harness/tests/workflow/adapters/test_idea_reconcile.py::test_set_loads_outcomes"
      - "packages/eng-harness/tests/workflow/adapters/test_idea_reconcile.py::test_calculate_unknown_no_rerun"
    covers: [AC11, AC12, AC13, AC18]   # AC13 in part: the fake-fault workflow; the mapping is T5
    depends_on: [T5, T7]
  - id: T9
    title: End-to-end cycles, crash matrix, recorded-reply contract tests, doctor section and the IDEA local-testing steps
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.doctor (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/doctor/_idea.py"
      - "packages/eng-harness/docs/local-testing.md"
      - "packages/eng-harness/acceptance/scripts/record_idea.py"
      - "packages/eng-harness/tests/unit/test_doctor.py"
      - "packages/eng-harness/tests/workflow/test_idea_cycle.py"
      - "packages/eng-harness/tests/replay/test_idea_resume.py"
      - "packages/eng-harness/tests/contract/test_idea_recordings.py"
    max_changed_lines: 300
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/test_idea_cycle.py::test_native_cycle_steps"
      - "packages/eng-harness/tests/workflow/test_idea_cycle.py::test_rest_cycle_steps"
      - "packages/eng-harness/tests/replay/test_idea_resume.py::test_crash_matrix"
      - "packages/eng-harness/tests/contract/test_idea_recordings.py::test_adapter_on_recordings"
      - "packages/eng-harness/tests/contract/test_idea_recordings.py::test_synthetic_matches_recordings"
      - "packages/eng-harness/tests/unit/test_doctor.py::test_idea_section"
    covers: [AC20, AC21, AC22]
    depends_on: [T8]
---

# Implementation plan: the `sasaah-idea-mcp` adapter

## 1. Approach

The adapter is data and mapping on the framework of [plan 0002](0002-servers-and-adapters.md), in the structure of
[plan 0011](0011-revit-adapter.md) (non-CSI server section, allowlist data pinned to the inventory, a synthetic fake with
faults) and [plan 0012](0012-sap2000-adapter.md) (gap entries that raise `NotImplementedGap`, each with a test that expects
it). Nothing is reused by copying. The spec's reading of the Sasaah sources is the reason for the order: the barriers come
first (server options and the allowlist with the 58-tool partition, T1 to T3), then the errors and the stub and verdict
rules that decide what the harness believes from IDEA (T4, T5), then the session and the gaps (T6), and only then the one
write the adapter has, the loads (T7), because it depends on the confirmed load map that the owner has not yet committed:
the map ships unset and T7's tests use a synthetic map, so the step raises `NotImplementedGap` (IG-2) on real use. The
calculation glue (T8) joins the pieces; T9 runs the whole cycle, the crash matrix and the recorded-reply tests, and writes
the local-test steps of spike S-08.

## 2. Tasks

**T1 Server section** (AC1). The `[servers.idea]` rules of spec §4.2 on the framework of plan 0002 T20, which adds
`routes`, the `route` key, `audit_log` and `servers/_launch_args.py` (spec 0002 AC40 to AC42, §11 A3, amended by B-085):
`audit_log = false` for IDEA (no `--audit-log` argument; a workflow test checks the argv the launcher actually receives,
because Sasaah ignores unknown arguments with only a warning), the `single` topology required (a second role is refused),
`route` required (`native` or `rest`), required `--disable-script`, forbidden `--read-only`, `--default-project`, other
arguments and `SASAAH_IDEA_*`, `SASAH_IDEA_*`, `IDEA_*` variables, loopback-only `service_url`. T3's allowlist declares
`routes = ["native", "rest"]` in its header and its `[[unit]]` entries in the framework's format.

**T2 Fake** (AC21 in part). The test-only fake of spec §4.12 with all faults, schemas from the inventory, and the
check that it is not packaged.

**T3 Allowlist, argument models, build check** (AC2, AC3, AC15, AC16 in part). The `_allowlist.toml` exactly as the
spec §4.4 lists the four classes (a test partitions the inventory), the pinned fingerprint over the 9 served tools,
`idea_status` flags in the build check, the argument models (explicit `connection_ids`, `save` fixed false, `confirm`
only under approval, design code from the basis only) and the unit header with its statuses. Session `_verify` may call
`BuildExpectation.status_tool` (default `csi_status`; IDEA `idea_status`) and name that tool in the build-check error
(amendment B-584). This is the barrier against
escape hatches, so the security lens reviews it.

**T4 Errors, timeouts, licensing** (AC17 to AC19). The code table of §4.8, the read or write timeout rule, and the
licensing outcomes of §4.9 bounded by the backstop. Reconciliation of the two write-like tools is T8.

**T5 Replies, stub guard, kinds, verdicts** (AC11 in part, AC13 to AC15). The reply parser with path reduction, the stub
markers, the harness kinds, and the pure verdict mapping with its golden and property tests (no upgrade of a host status; zero utilization with a true status goes to the engineer because Sasaah fills missing values with 0).
`_verdicts.py` is engineering content: it stays draft and the owner reviews it.

**T6 Session, ports, gaps** (AC4 to AC6). Working copy and hashes, the route preconditions, `acquire`, `locate`,
`save`, `restore`, `read_units` and the others of §4.10, and the `NotImplementedGap` entries IG-1, IG-3 and IG-4.

**T7 Loads** (AC7 to AC10, AC16 in part). `_load_map.toml` with every sign unset and status `unconfirmed`, the load
plan and builder (exact segment match, structure preserved, `forcesPercentageOnSegments` refused), the write to a new
file, the read-back, the `harness.idea_loads/1` kind and `check_model` for the adapter. T7 may only replace the
`check_model` stub in `_session_ops.py` with the section 4.10 integrity set built from the last `set_loads` (load-map
status, zero-dropped, read-back mismatch or unavailable) and rebind the model key to `out_path` after a successful write
(AC10; amendment B-593). The synthetic map lives in `tests/fixtures/idea/` and says so in its header.

**T8 Calculation** (AC11, AC12, AC13 in part, AC18). `idea_native_calculate` and `idea_calculate` / `idea_get_check_results` with the
pre-flight and the stub refusal, host verdicts out, reconciliation of `idea_native_set_loads` by file and read-back, and
`unknown` without re-run for `idea_calculate`.

**T9 End to end** (AC20 to AC22). Both cycles, the crash matrix at every write step, recorded-reply contract tests
(skipped with a reason until the owner commits IDEA recordings), the doctor section, the S-08 steps (spec §12 L1 to L11)
in `docs/local-testing.md` and a record script under `acceptance/scripts/`. If another plan's task has not created
`docs/local-testing.md`, T9 creates it with the IDEA part only.

**T10 Typed loads on the REST route (blocked, not in the front matter).** Starts only after the owner has run L4 and
decided Q1 and, in the Sasaah repository, a typed tool that sends loads to the REST service exists (project lane,
ADR-0026). Then: the tool's allowlist entry, its unit header, its read-back, and the replacement of the IG-1 and IG-3
gap tests for that tool (a spec change, not a test changed to pass). Its own plan amendment lists files and budget.

## 3. Dependencies

- Runtime: none new. Development: none new.
- Plans: plan 0002 T1, T5 to T10, T14 and T20 (config, transport, allowlist and build check, lock and guard, adapter
  framework, error mapping, model identity, reconciliation, and the framework additions of spec 0002 §11 A3: routes,
  `audit_log`, the unit header) before T1 and T3 of this plan; plan 0001 (engine ports,
  `NotImplementedGap`) and plan 0004 (design-basis fields `connection.design_code` and `checks.readback_relative_tolerance_ratio`
  must exist in the workflow's template, which the workflow spec adds) before T7 runs a workflow. Specs: `eng-contract`
  0.1.0 merged and its `verdicts.set/1`, `forces.member_end/1` and `issues.model_check/1` kinds built (contract tasks
  T10 to T12). The column workflow spec (B-083) is the first consumer of the load plan and the verdict set.
- Owner decisions that do not block T1 to T9: Q1 to Q11 of the spec (the recommendations are implemented); the confirmed
  load map (Q11) is a data commit after L9, not a code task.
- Shared file (amendment B-593): `packages/eng-harness/src/eng_harness/adapters/idea/_session_ops.py` belongs to T6; T7
  extends it (serialization T6 then T7) so T7 may only replace the `check_model` INTERNAL stub with the section 4.10
  integrity set built from the last `set_loads` (load-map status, zero-dropped, read-back mismatch or unavailable) and
  rebind the model key to `out_path` after a successful write (AC10). T7 already depends on T6.

## 4. Verification

- Local gate per task (`uv run eng-gate check` once available; until then ruff, mypy strict and pytest with coverage from
  `packages/eng-harness/`); the pull request links its CI run.
- Fake-host workflow tests run the synthetic fake as a real process through the harness launcher.
- Needs local test (spec §12, listed in `docs/local-testing.md`): everything that drives `sasaah-idea-mcp`, the REST
  service or the hidden calculator. No task claims a live result.
- Review: correctness, type-design, silent-failure and test lenses on every task; the security lens on T1 and T3
  (options, allowlist); R1 review against the spec's evidence rules on T5 (verdict mapping) and T7 (loads). Second-family
  review and owner approvals are `awaiting owner` (ADR-0028 §4).

## 5. Rollback

Each task is one squash-merged pull request into `build/v1`; reverting it removes it and its dependants. T1 and T3 only add
a server section and an allowlist, so their revert leaves the CSI and Revit adapters (and their pinned fingerprints)
untouched. A wrong verdict rule or load map is fixed forward in the data file or mapping; a Sasaah build the allowlist was
not tested with is refused by the build check rather than run.
