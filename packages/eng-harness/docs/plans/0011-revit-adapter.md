---
id: plan-b080-revit-adapter
issue: "B-080"
spec: packages/eng-harness/docs/specs/0011-revit-adapter.md
status: draft            # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1, r2, r3]  # r3 from the public_modules entries in pyproject.toml (amendment B-356); r2 from the kinds (amendment B-453)
tasks:
  - id: T1
    title: Framework extensions (attended class, host_dialog confirm, optional pid, deny-list names) and the Revit server section
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.ports, eng_harness.servers (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/ports.py"
      - "packages/eng-harness/src/eng_harness/servers/_config.py"
      - "packages/eng-harness/src/eng_harness/servers/_buildcheck.py"
      - "packages/eng-harness/src/eng_harness/adapters/_descriptors.py"
      - "packages/eng-harness/src/eng_harness/adapters/_allowlist.py"
      - "packages/eng-harness/tests/unit/servers/test_config.py"
      - "packages/eng-harness/tests/unit/servers/test_buildcheck.py"
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py"
    max_changed_lines: 350
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/servers/test_config.py::test_revit_server_section"
      - "packages/eng-harness/tests/unit/servers/test_config.py::test_revit_forbidden_options"
      - "packages/eng-harness/tests/unit/servers/test_buildcheck.py::test_addin_hashes"
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py::test_attended_class_and_deny_names"
    covers: [AC1, AC2, AC3]   # AC2 and AC3 in part: T1 holds the framework tests (deny-list names and class, add-in hashes); T3 and T4 complete them
    depends_on: []
  - id: T2
    title: Synthetic Revit fake server (test-only), its faults and its schema check
    files:
      - "packages/eng-harness/tests/fakes/sasaah_revit/**"
      - "packages/eng-harness/tests/contract/test_revit_allowlist.py"
      - "packages/eng-harness/tests/unit/test_package_contents.py"
    max_changed_lines: 60
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/contract/test_revit_allowlist.py::test_fake_schemas_match_inventory"
      - "packages/eng-harness/tests/unit/test_package_contents.py::test_revit_fake_not_shipped"
    covers: [AC30]
    depends_on: [T1]
  - id: T3
    title: Revit allowlist data, argument models and pinned role fingerprints
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.revit (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/revit/__init__.py"
      - "packages/eng-harness/src/eng_harness/adapters/revit/_allowlist.toml"
      - "packages/eng-harness/src/eng_harness/adapters/revit/_tools.py"
      - "packages/eng-harness/tests/unit/adapters/test_revit_allowlist.py"
      - "packages/eng-harness/tests/contract/test_revit_allowlist.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/adapters/test_revit_allowlist.py::test_entries_complete"
      - "packages/eng-harness/tests/unit/adapters/test_revit_allowlist.py::test_escape_hatches_refused"
      - "packages/eng-harness/tests/contract/test_revit_allowlist.py::test_against_inventory"
      - "packages/eng-harness/tests/contract/test_revit_allowlist.py::test_fingerprints_from_inventory"
    covers: [AC2]
    depends_on: [T1, T2]
  - id: T4
    title: Revit build check (excluded tools, toolset reason, catalog version), role start options and the pinned pipe
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.servers (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/servers/_buildcheck.py"
      - "packages/eng-harness/src/eng_harness/servers/_session.py"
      - "packages/eng-harness/tests/workflow/servers/test_revit_session.py"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_target.py"
    max_changed_lines: 300
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/servers/test_revit_session.py::test_build_check_reasons"
      - "packages/eng-harness/tests/workflow/servers/test_revit_session.py::test_read_role_has_no_write_tool"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_target.py::test_pipe_pinned"
    covers: [AC3, AC4]
    depends_on: [T3]
  - id: T5
    title: Reply parsing, error and timeout mapping, units from specification identifiers
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.revit (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/revit/_replies.py"
      - "packages/eng-harness/src/eng_harness/adapters/revit/_errors.py"
      - "packages/eng-harness/src/eng_harness/adapters/revit/_units.py"
      - "packages/eng-harness/src/eng_harness/adapters/revit/_specs.toml"
      - "packages/eng-harness/tests/unit/adapters/test_revit_replies.py"
      - "packages/eng-harness/tests/unit/adapters/test_revit_errors.py"
      - "packages/eng-harness/tests/unit/adapters/test_revit_units.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/adapters/test_revit_replies.py::test_parse_warning_truncated"
      - "packages/eng-harness/tests/unit/adapters/test_revit_errors.py::test_mapping_table"
      - "packages/eng-harness/tests/unit/adapters/test_revit_errors.py::test_timeout_text_rule"
      - "packages/eng-harness/tests/unit/adapters/test_revit_errors.py::test_unexpected_text_on_write"
      - "packages/eng-harness/tests/unit/adapters/test_revit_errors.py::test_consumed_token_and_not_executed_on_write_unknown"
      - "packages/eng-harness/tests/unit/adapters/test_revit_units.py::test_length_feet_to_mm"
      - "packages/eng-harness/tests/unit/adapters/test_revit_units.py::test_unmapped_spec_listed"
      - "packages/eng-harness/tests/unit/adapters/test_revit_units.py::test_display_value_never_used"
    covers: [AC5, AC6, AC7]
    depends_on: [T3]
  - id: T6
    title: Revit kinds and the parameter role map
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.revit, eng_harness.kinds and more (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/kinds/revit.py"
      - "packages/eng-harness/src/eng_harness/kinds/__init__.py"
      - "packages/eng-harness/src/eng_harness/adapters/revit/_parameters.py"
      - "packages/eng-harness/src/eng_harness/servers/_config.py"
      - "packages/eng-harness/tests/contract/test_revit_kinds.py"
      - "packages/eng-harness/tests/unit/adapters/test_revit_parameters.py"
    max_changed_lines: 330
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/contract/test_revit_kinds.py::test_fixtures"
      - "packages/eng-harness/tests/unit/adapters/test_revit_parameters.py::test_role_map_rules"
    covers: [AC33]
    depends_on: [T5]
  - id: T7
    title: Revit state reader, chunked reads, fingerprint and the neutral kinds
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.revit (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/revit/_state.py"
      - "packages/eng-harness/src/eng_harness/adapters/_hostport.py"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_state.py"
      - "packages/eng-harness/tests/property/test_revit_fingerprint.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/adapters/test_revit_state.py::test_kinds_and_ids"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_state.py::test_truncation_by_level"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_state.py::test_response_too_large_halves"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_state.py::test_neutral_kinds_complete_rows_only"
      - "packages/eng-harness/tests/property/test_revit_fingerprint.py::test_order_independent_and_edit_sensitive"
    covers: [AC9, AC10, AC11]
    depends_on: [T6]
  - id: T8
    title: Revit edit kinds, value encoding, call preconditions (identity, active document, shared type, parameter resolution)
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.revit (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/revit/_edits.py"
      - "packages/eng-harness/src/eng_harness/adapters/revit/_tools.py"
      - "packages/eng-harness/tests/unit/adapters/test_revit_values.py"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_edits.py"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_identity_check.py"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_active_document.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/adapters/test_revit_values.py::test_value_encoding"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_edits.py::test_edit_mapping"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_edits.py::test_batch_fits_dialog_summary"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_edits.py::test_shared_type_refused"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_edits.py::test_duplicate_no_overrides"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_edits.py::test_parameter_resolution"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_identity_check.py::test_unique_id_verified_before_write"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_active_document.py::test_active_document_checked"
    covers: [AC8, AC12, AC13, AC14, AC15, AC16, AC17]
    depends_on: [T7]
  - id: T9
    title: Attended writes (dialog outcomes), read-back and check_model for Revit
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.revit (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/revit/_checks.py"
      - "packages/eng-harness/src/eng_harness/adapters/revit/_edits.py"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_dialog.py"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_readback.py"
    max_changed_lines: 350
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/adapters/test_revit_dialog.py::test_declined_not_applied"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_dialog.py::test_unanswered_is_busy"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_dialog.py::test_short_timeout_is_unknown"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_readback.py::test_commit_unchecked_detected"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_readback.py::test_mismatch"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_readback.py::test_check_model_issues"
    covers: [AC18, AC19]
    depends_on: [T8]
  - id: T10
    title: Reconciliation by reading for the Revit write tools
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.revit (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/revit/_reconcile.py"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_reconcile.py"
    max_changed_lines: 350
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/adapters/test_revit_reconcile.py::test_outcomes_per_tool"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_reconcile.py::test_retry_duplicate_setter_applied"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_reconcile.py::test_duplicate_type_after_retry"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_reconcile.py::test_retry_token_consumed_applied"
    covers: [AC20, AC21]
    depends_on: [T9]
  - id: T11
    title: Revit session operations (working copy, gaps), Revit identity rules and the pipe-keyed host lock
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.revit, eng_harness.servers (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/revit/_session_ops.py"
      - "packages/eng-harness/src/eng_harness/adapters/_identity.py"
      - "packages/eng-harness/src/eng_harness/servers/_hostlock.py"
      - "packages/eng-harness/tests/unit/adapters/test_identity.py"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_session_ops.py"
      - "packages/eng-harness/tests/workflow/servers/test_revit_hostlock.py"
    max_changed_lines: 350
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/adapters/test_revit_session_ops.py::test_working_copy"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_session_ops.py::test_workshared_refused"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_session_ops.py::test_gaps_not_implemented"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_session_ops.py::test_engineer_save_registered"
      - "packages/eng-harness/tests/unit/adapters/test_identity.py::test_revit_resolution"
      - "packages/eng-harness/tests/workflow/servers/test_revit_hostlock.py::test_pipe_key"
    covers: [AC23, AC24, AC25, AC26]
    depends_on: [T7]
  - id: T12
    title: Calc harness.frame_element_map and its kind, with golden cases
    # Amendment (B-467, documents only): the calc reads the basis field compare.length_mm (spec 0007 4.8 name).
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.calcs, eng_harness.calcs.frame_element_map, eng_harness.kinds and more (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/verification/calcs/harness.frame_element_map.md"
      - "packages/eng-harness/src/eng_harness/calcs/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/frame_element_map.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/src/eng_harness/kinds/calcs.py"
      - "packages/eng-harness/tests/unit/calcs/test_frame_element_map.py"
      - "packages/eng-harness/tests/property/test_frame_element_map.py"
      - "packages/eng-harness/tests/data/golden/calcs/frame-element-map-*.json"
    max_changed_lines: 380
    max_sessions: 3
    tests_first:
      # Amendment (B-452): the golden cases of the shared loader tests/golden/test_calcs_golden.py are data, not test
      # functions, and this task does not change that file, so they cannot be test-first evidence (gate TF008, TF010);
      # the task's golden files stay in its first commit and run in the tests step.
      - "packages/eng-harness/tests/property/test_frame_element_map.py::test_permutation_invariant"
      - "packages/eng-harness/tests/unit/calcs/test_frame_element_map.py::test_basis_fields_required"
    covers: [AC27, AC28, AC29]
    depends_on: [T6]
  - id: T13
    title: Record mode scenario for Revit, sanitizer rules, recordings contract tests and the record script
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.servers (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/servers/_record.py"
      - "packages/eng-harness/acceptance/recordings/README.md"
      - "packages/eng-harness/acceptance/scripts/record_revit.py"
      - "packages/eng-harness/tests/fakes/recorded/**"
      - "packages/eng-harness/tests/unit/servers/test_record.py"
      - "packages/eng-harness/tests/contract/test_revit_recordings.py"
    max_changed_lines: 330
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/servers/test_record.py::test_revit_sanitized"
      - "packages/eng-harness/tests/contract/test_revit_recordings.py::test_adapter_on_recordings"
    covers: [AC31]
    depends_on: [T11]
  - id: T14
    title: Doctor checks for the Revit server
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.doctor (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/doctor.py"
      - "packages/eng-harness/tests/unit/test_doctor.py"
    max_changed_lines: 220
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/test_doctor.py::test_revit_checks"
    covers: [AC32]
    depends_on: [T4]
  - id: T15
    title: Port wiring, crash matrix, stale-map test and the Revit local-testing document
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/__init__.py"
      - "packages/eng-harness/docs/local-testing.md"
      - "packages/eng-harness/tests/replay/test_revit_resume.py"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_map_stale.py"
    max_changed_lines: 200
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/replay/test_revit_resume.py::test_crash_matrix"
      - "packages/eng-harness/tests/workflow/adapters/test_revit_map_stale.py::test_map_stale_after_edit"
    covers: [AC22, AC29]
    depends_on: [T10, T11, T12, T13, T14]
---

# Implementation plan: the `sasaah-revit-mcp` adapter

## 1. Approach

The adapter is a Revit module beside the CSI module of [plan 0002](0002-servers-and-adapters.md): the framework (server
manager, allowlist loader, build check, envelopes, ledger, `HostPort` and `ToolPort` shells, identity, record mode,
doctor) is reused, and this plan adds only what Revit needs. Risky and shared parts come first. T1 changes shared code
(the `attended` class, `host_dialog`, optional `HostInstance.pid`, the deny-list names), so it lands before anything
else and carries the regression proof that the CSI suite of plan 0002 still passes unchanged. The fake (T2) comes next
so every later task runs against a real server process with the faults of spec §4.13. Then the data and parsing that
everything depends on: allowlist and pinned fingerprints (T3), the build check and the pinned pipe (T4), replies,
errors and units (T5), kinds and the role map (T6). The state reader (T7) precedes the writes because every write
verifies identity and the active document against a read. The edit kinds with their preconditions (T8) are followed by
attended outcomes and read-back (T9) and by reconciliation (T10), in the order the engine needs them (write, check,
reconcile). Session operations and the pipe-keyed lock (T11) are independent of T9 and T10 and need only the state
reader. The mapping calc (T12) needs only the kinds, so it may run beside T9 to T11, but all tasks edit
`CHANGELOG.md` and several edit `_edits.py`, `_buildcheck.py` or `_config.py`, so they run one after another by
pull-request order (`depends_on` shows the needed order, not a parallel plan). T13 and T14 are the record script and
the doctor; T15 wires the ports and adds the crash matrix and the stale-map test.

Every task is test-first ([process/05](../../../../design/process/05-testing-and-verification.md) §9): its first
commit holds the tests of `tests_first` (and, for T12, the golden files with hand-derived expected values), and they fail
on `build/v1`. `max_changed_lines` counts non-test code, as in plan 0002 (T3 and T5 are near the cap because the
allowlist data and the error table are data-heavy; if a task measures over, it is split by a plan amendment in its own
reviewed pull request, decision D-12, and not given a bigger budget). Nothing in this plan needs a host program in CI.

R1 content in bootstrap mode ([ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §4): the calc is
registered with `verification="draft"` and no approval is added; `src/eng_harness/calcs/` and `tests/data/golden/` are
protected paths, so T12's pull request is R1 and lists the calc id and content hash for the owner queue. The parameter
role map and the specification-identifier table ship as data with the status `candidate`; no task marks a value
`reference` before the owner's local record exists.

## 2. Tasks

**T1 Framework and config** (spec §4.2, §4.4, §11 A1). `attended` as a timeout class and `confirm = "host_dialog"` in
the descriptor model, `ToolInfo.attended`, `HostInstance.pid` optional in `ports.py`, the deny-list names
(`revit_shutdown_bridge`, `revit_authenticate`, `revit_prepare_destructive`, `revit_switch_target`, and the
code-toolset names `revit_compile_and_run`, `revit_batch_execute` and the others of spec §4.4, all as exact MCP names), `[servers.revit]` with `pipe_name`,
`build.addin_sha256` and `addin_paths`, the role-to-class table, required and forbidden options, and the add-in hash
check in the build check. The tests of plan 0002 that read these structures change only in how they construct them,
never in what they expect.

**T2 Fake** (spec §4.13). Test code only. A stdio MCP server built from the inventory schemas of a fixed list of the 21
allowlisted tool names (the allowlist itself arrives in T3, whose contract test checks that list against it), with levels, grids, columns, framing, types and parameters (raw feet values, `specId`, `builtInParameter`), one
document with a path, `open_model`, transactions that validate then apply, and the faults `dialog_declined`,
`dialog_unanswered`, `commit_unchecked`, `retry_duplicate`, `retry_token_consumed`, `timeout_not_started`, `timeout_executing`,
`response_too_large`, `element_replaced`, `other_document_active`, `workshared_open`, `lost_pipe`,
`destructive_toolset_off`, `code_toolset_on`. The contract test checks that its tool list equals the inventory for the
allowlisted tools.

**T3 Allowlist** (spec §4.4). The 21 entries with kind, class, effect, action, `confirm`, result kind, read-back and
argument model, the deny list applied on load, the header with `sasaah_commit`, `also_tested_commits` and the two
role fingerprints computed from the inventory (`fingerprint_source = "s12-inventory"`). Argument models for all tools
are here (small `ParamModel`s) so the entries are complete; `expected_instances`, lengths and `valueType` are declared.

**T4 Build check and pipe** (spec §4.3). The excluded-tool rule, the destructive-toolset reason, `catalog_version`
recorded, server start options per role (`--read-only` on `read` only, the explicit negative options), and the
`revit_get_current_target` equality check; the read role lists no bridge write tool.

**T5 Replies, errors, units** (spec §4.5 to §4.7). The reply parser with the `_warning` rule, the error table with the
text rules ("NOT executed", "already executing", the code-less texts) and the write-certainty rule (only a text that a
resend cannot produce is certain: the declined dialog; a consumed-token or "NOT executed" text on a write is unknown), and the
specification table `_specs.toml` (length and angle only) with the conversions through `eng_contract.units`.

**T6 Kinds and role map** (spec §4.5, §4.8). The `harness.revit_*` kinds with strict models and the `frame_element_map`
kind registration point, and the role map loader with statuses and the load-time rules.

**T7 State** (spec §4.5, §4.9). The reader (metadata, levels, grids, the two category lists, details, parameters of the
mapped roles, types), chunking by halving, the per-level re-read, the fingerprint over raw replies, the neutral kinds
for complete rows, the `loaded` and `locate` hooks.

**T8 Edits** (spec §4.8). Value encoding (length only, explicit `valueType` and `unit`), batch sizing from the 500
characters of the dialog summary, the `unique_id` check and the active-document check before every write, the
shared-type rule, `duplicate_family_type` without overrides, parameter resolution from the prior read.

**T9 Attended writes and checks** (spec §4.7, §4.8). Dialog outcomes at the tool layer (declined, unanswered), the
read-back helpers per tool, and `check_model` with the Revit issue codes. The unanswered dialog is tested twice: with a
`write` timeout above the add-in deadline (`HOST_BUSY`) and below it (`TIMEOUT_UNKNOWN_OUTCOME`).

**T10 Reconciliation** (spec §4.10). The per-tool rules, including the retried `duplicate_family_type` and the
element-not-found case of `change_element_type`, with the evidence stored.

**T11 Session** (spec §4.9, §4.12). `working_copy` with its reply checks, the gaps (`save`, `restore`) as
`NotImplementedGap`, empty `started_instances`, the identity rule for an engineer save, and the host lock keyed by the
pipe name.

**T12 Mapping calc** (spec §4.11). Pure function over `model.frame_placements/1` inputs, the optional link map and the
basis fields (`compare.length_mm`, `mapping.offset_*`), exact arithmetic, the output kind, the verification record
(draft), and golden cases derived by hand and written in each file's `derivation` field.

**T13 Recordings** (spec §4.13, AC31). The Revit scenario of record mode (titles, paths and user names replaced), the
sanitizer test, the recorded-reply contract tests (skipped with a reason until the owner commits recordings), and the
record script for the owner's local run.

**T14 Doctor** (AC32). The Revit checks as a `CheckProvider`: pipe and bridge, hashes, destructive toolset, Revit
version, open document base name, and the warning when the `write` role's `call_timeout_s` is not above the add-in
queue deadline (spec §4.2 rule 1).

**T15 Wiring and documents** (AC22, AC29). Port wiring for the Revit adapter, the crash matrix against real fake
processes, the stale-map test, and the Revit section of `docs/local-testing.md` (spec §12, L1 to L15).

## 3. Dependencies

- Runtime: none new (`mcp`, `eng-contract`, `pydantic` as in plan 0002). Development: none new.
- Work items before T1: plan 0002 T6 and T6b (allowlist, build check), T7 to T10 (lock, guard, framework, errors, identity,
  session operations) as the tasks named below need them: T3 needs plan 0002 T8b, T5 needs T9, T7 needs T11, T8 needs
  T12, T10 needs T14, T11 needs T10, T13 needs T17, T14 needs T18, T15 needs T19a (amendment B-475). Engine plan 0001 as for plan 0002 (T1
  edits `ports.py` of engine T6).
- T12 needs the calc framework of plan 0003 (T1 to T6) and the helper style of its T12 (`placement_compare`).
- Plan 0008 (SAFE) also edits `servers/_buildcheck.py` and the allowlist header shape: whichever lands second adapts to
  the other in its own task; this plan keeps its fingerprints in its own `adapters/revit/_allowlist.toml`, keyed by role,
  so the CSI header does not change.
- Spec 0004 (design basis template) needs `mapping.offset_x`, `_y`, `_z` with a source each; until the owner accepts them
  (spec Q6) the calc refuses a basis without them, and T12 does not depend on the template.
- Owner decisions that do not block T1 to T15: Q1 to Q9 of the spec (the recommendations are implemented). The Sasaah
  tools of Q2 (save and close) would unblock `work_on_copy` on Revit; they are a project-lane request, not part of this plan.

## 4. Verification

- Local gate per task (`uv run eng-gate check` once available; until then ruff, mypy strict and pytest with coverage from
  `packages/eng-harness/`); the pull request links its CI run.
- Fake-host workflow tests run the Revit fake as a real process through the harness launcher (POSIX in Linux CI).
- Review: correctness, Python, type-design, silent-failure and test lenses on every task; the security lens on T1, T3
  and T4 (the deny list and the build check are the barrier against `revit_compile_and_run`, `revit_shutdown_bridge`, `revit_batch_execute`
  and the other forwarders); R1 review of T8 to T11 against the spec's unit, read-back, reconciliation and active-document
  rules. Second-family review and owner approvals are `awaiting owner` (ADR-0028 §4).
- Needs local test (spec §12, listed in `docs/local-testing.md` by T15): everything that drives `sasaah-revit-mcp` and
  Revit, which is all of spike S-05 (L1 to L15). No task claims a live result.
- Owner queue after the plan: the spec's Q1 to Q9 and R-G1 to R-G15, the correction C1 to S-12 §10, the calc id and
  content hash of T12, and the `candidate` entries of the role map and the specification table.

## 5. Rollback

Each task is one squash-merged pull request into `build/v1`; reverting it removes it and its dependants. T1 changes shared
structures: its revert restores the CSI-only shapes, and the plan 0002 suite is its regression test. The Revit allowlist
is data: a wrong entry is fixed forward, and a Sasaah build the allowlist was not tested with is refused by the build
check rather than run. The calc is registered with `verification="draft"`; a defective calc is withdrawn through
`approvals.yaml` in a later change, never edited under its id. Nothing here writes to Revit in CI.
