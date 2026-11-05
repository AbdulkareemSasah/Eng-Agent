---
id: plan-b061-servers-and-adapters
issue: "B-061"
spec: packages/eng-harness/docs/specs/0002-servers-and-adapters.md
status: draft            # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1, r3]           # binding for every pull request of this plan; r3 because T1 touches pyproject.toml and uv.lock
tasks:
  - id: T1
    title: MCP SDK dependency ADR, harness.toml server and tool sections
    files:
      - "pyproject.toml"
      - "uv.lock"
      - "packages/eng-harness/pyproject.toml"
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/adr/0001-mcp-python-sdk.md"
      - "packages/eng-harness/docs/local-testing.md"
      - "packages/eng-harness/src/eng_harness/servers/__init__.py"
      - "packages/eng-harness/src/eng_harness/servers/_config.py"
      - "packages/eng-harness/tests/unit/servers/__init__.py"
      - "packages/eng-harness/tests/unit/servers/test_config.py"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/servers/test_config.py::test_load_full"
      - "packages/eng-harness/tests/unit/servers/test_config.py::test_timeouts_required"
      - "packages/eng-harness/tests/unit/servers/test_config.py::test_forbidden_options"
    covers: [AC1, AC2, AC3]
    depends_on: []
  - id: T2
    title: Process launcher and inspector ports, POSIX implementation
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.servers (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/servers/_launcher.py"
      - "packages/eng-harness/src/eng_harness/servers/_procinfo.py"
      - "packages/eng-harness/tests/unit/servers/test_launcher_posix.py"
      - "packages/eng-harness/tests/unit/servers/test_procinfo.py"
      - "packages/eng-harness/tests/fakes/proc/**"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/servers/test_launcher_posix.py::test_group_terminated"
      - "packages/eng-harness/tests/unit/servers/test_launcher_posix.py::test_server_exits_when_engine_killed"
      - "packages/eng-harness/tests/unit/servers/test_launcher_posix.py::test_tool_timeout_kills_group"
      - "packages/eng-harness/tests/unit/servers/test_procinfo.py::test_identity_stable"
      - "packages/eng-harness/tests/unit/servers/test_procinfo.py::test_terminate_checks_start_time"
    covers: [AC4, AC6, AC7]
    depends_on: [T1]
  - id: T3
    title: Windows launcher, per-server Job Objects with breakaway, Windows process inspector
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.servers (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/servers/_launcher_windows.py"
      - "packages/eng-harness/src/eng_harness/servers/_procinfo.py"
      - "packages/eng-harness/tests/windows/test_jobs.py"
      - "packages/eng-harness/tests/windows/test_procinfo.py"
      - "packages/eng-harness/tests/fakes/proc/**"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/windows/test_jobs.py::test_suspended_assign_resume"
      - "packages/eng-harness/tests/windows/test_jobs.py::test_kill_on_close"
      - "packages/eng-harness/tests/windows/test_jobs.py::test_breakaway_survives"
      - "packages/eng-harness/tests/windows/test_jobs.py::test_tool_job_no_breakaway"
      - "packages/eng-harness/tests/windows/test_procinfo.py::test_identity_windows"
    covers: [AC5, AC6, AC7]
    depends_on: [T2]
  - id: T3b
    title: Process listings leave out processes the engine may not open; close() documented as ending a Windows job
    # Amendment (B-388, documents only): the B-122 reviews found that one process OpenProcess refuses (another user's
    # host program) made snapshot() and children() fail, and that the port docstring of close() disagreed with the
    # Windows kill-on-close behaviour.
    files:
      - "packages/eng-harness/src/eng_harness/servers/_procinfo.py"
      - "packages/eng-harness/src/eng_harness/servers/_launcher.py"
      - "packages/eng-harness/tests/windows/test_procinfo.py"
    max_changed_lines: 40
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/windows/test_procinfo.py::test_listing_skips_inaccessible"
    covers: [AC7a]
    depends_on: [T3]
  - id: T4
    title: Synthetic Sasaah CSI fake server (test-only) and its schema check
    files:
      - "packages/eng-harness/tests/fakes/__init__.py"
      - "packages/eng-harness/tests/fakes/sasaah_csi/**"
      - "packages/eng-harness/tests/contract/test_csi_allowlist.py"
      - "packages/eng-harness/tests/unit/test_package_contents.py"
    max_changed_lines: 50
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/contract/test_csi_allowlist.py::test_fake_schemas_match_inventory"
      - "packages/eng-harness/tests/unit/test_package_contents.py::test_fakes_not_shipped"
    covers: [AC35]
    depends_on: [T1]
  - id: T5
    # Amendment (B-373, documents only): the process transport builds the anyio memory-object streams the SDK's client
    # session reads, so anyio becomes a direct dependency (already locked through mcp); tests/workflow/servers/__init__.py
    # leaves the files (mypy reports a duplicate module "servers" next to tests/unit/servers/__init__.py).
    title: Process transport, MCP client session, crash detection, restart and shutdown
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry (B-356); the anyio dependency (B-373)
      - "uv.lock"  # the anyio dependency, already locked through mcp (B-373)
      - "packages/eng-harness/docs/adr/0001-mcp-python-sdk.md"  # records anyio as a direct dependency (B-373)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/servers/__init__.py"
      - "packages/eng-harness/src/eng_harness/servers/_transport.py"
      - "packages/eng-harness/src/eng_harness/servers/_session.py"
      - "packages/eng-harness/tests/workflow/servers/test_session.py"
      - "packages/eng-harness/tests/workflow/conftest.py"
      - "packages/eng-harness/tests/workflow/__init__.py"  # empty package marker: without it mypy names this folder's conftest.py "conftest", as it does every bare conftest module (engine T3b's tests/conftest.py, tools/eng-dev-gate/tests/conftest.py) (B-377, B-378)
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/servers/test_session.py::test_start_list_call"
      - "packages/eng-harness/tests/workflow/servers/test_session.py::test_crash_restart"
      - "packages/eng-harness/tests/workflow/servers/test_session.py::test_shutdown_leaves_hosts"
    covers: [AC8, AC11, AC12]
    depends_on: [T2, T4]
  - id: T6
    title: Tool descriptors, allowlist data with escape-hatch refusal and release marks
    # Amendment (B-342, documents only): the original T6 (430 lines) exceeded limits.max_task_lines (400, gate GC005);
    # lead decision D-12: split. T6 keeps the descriptors, the allowlist data and its load-time refusals (AC16) and the
    # release marks (AC38 load side, B-068); T6b keeps the build check, the fingerprint and `ServerCheck` (AC9, AC10).
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/pyproject.toml"
      - "packages/eng-harness/src/eng_harness/servers/_config.py"
      - "packages/eng-harness/src/eng_harness/adapters/__init__.py"
      - "packages/eng-harness/src/eng_harness/adapters/_descriptors.py"
      - "packages/eng-harness/src/eng_harness/adapters/_allowlist.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/__init__.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_allowlist.toml"
      - "packages/eng-harness/tests/unit/servers/test_config.py"
      - "packages/eng-harness/tests/unit/adapters/__init__.py"
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py"
      - "packages/eng-harness/tests/contract/test_csi_allowlist.py"
    max_changed_lines: 250
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py::test_entries_complete"
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py::test_escape_hatches_refused"
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py::test_release_marks"
      - "packages/eng-harness/tests/unit/servers/test_config.py::test_cli_tools_release_marks"
      - "packages/eng-harness/tests/contract/test_csi_allowlist.py::test_against_inventory"
    covers: [AC16, AC38]
    depends_on: [T5]
  - id: T6b
    title: Build check, tool-list fingerprint pinned from the inventory, and ServerCheck
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.csi, eng_harness.servers (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/servers/_buildcheck.py"
      - "packages/eng-harness/src/eng_harness/servers/_session.py"
      - "packages/eng-harness/src/eng_harness/adapters/_allowlist.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_allowlist.toml"
      - "packages/eng-harness/tests/unit/servers/test_buildcheck.py"
      - "packages/eng-harness/tests/contract/test_csi_allowlist.py"
      - "packages/eng-harness/tests/workflow/servers/test_session.py"
    max_changed_lines: 180
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/servers/test_buildcheck.py::test_fingerprint_definition"
      - "packages/eng-harness/tests/unit/servers/test_buildcheck.py::test_each_mismatch"
      - "packages/eng-harness/tests/contract/test_csi_allowlist.py::test_pinned_fingerprint_from_inventory"
      - "packages/eng-harness/tests/workflow/servers/test_session.py::test_build_mismatch_stops_run"
    covers: [AC9, AC10]
    depends_on: [T6]
  - id: T7
    title: Machine-level host-instance lock and process guard
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.servers (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/servers/_hostlock.py"
      - "packages/eng-harness/src/eng_harness/servers/_guard.py"
      - "packages/eng-harness/src/eng_harness/servers/_session.py"
      - "packages/eng-harness/tests/unit/servers/test_hostlock.py"
      - "packages/eng-harness/tests/workflow/servers/test_guard.py"
    max_changed_lines: 350
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/servers/test_hostlock.py::test_second_driver_refused"
      - "packages/eng-harness/tests/unit/servers/test_hostlock.py::test_stale_and_pid_reuse"
      - "packages/eng-harness/tests/workflow/servers/test_guard.py::test_close_only_started"
      - "packages/eng-harness/tests/workflow/servers/test_guard.py::test_close_after_timeout_falls_back"
    covers: [AC13, AC14, AC15]
    depends_on: [T6b]
  - id: T8
    title: Adapter framework - arguments and references, envelopes with limits and provenance
    # Amendment (B-342, documents only): the original T8 (430 lines) exceeded limits.max_task_lines (400, gate GC005);
    # lead decision D-12: split. T8 keeps the argument and envelope layers (AC18, AC19); T8b keeps the write ledger and
    # the ToolPort over them (AC17, AC38 port side, B-068). T8 waits for T6b because provenance records the build.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/__init__.py"
      - "packages/eng-harness/src/eng_harness/adapters/_args.py"
      - "packages/eng-harness/src/eng_harness/adapters/_envelope.py"
      - "packages/eng-harness/src/eng_harness/_kinds.py"
      - "packages/eng-harness/tests/unit/adapters/test_args.py"
      - "packages/eng-harness/tests/unit/adapters/test_envelope.py"
    max_changed_lines: 180
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/adapters/test_args.py::test_refs_resolved_converted_recorded"
      - "packages/eng-harness/tests/unit/adapters/test_envelope.py::test_limits_and_provenance"
    covers: [AC18, AC19]
    depends_on: [T6b]
  - id: T8b
    title: Write ledger and ToolPort describe, call and unreleased_tools
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/__init__.py"
      - "packages/eng-harness/src/eng_harness/adapters/_ledger.py"
      - "packages/eng-harness/src/eng_harness/adapters/_toolport.py"
      - "packages/eng-harness/src/eng_harness/_kinds.py"
      - "packages/eng-harness/tests/unit/adapters/test_toolport.py"
    max_changed_lines: 250
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/adapters/test_toolport.py::test_not_allowlisted"
      - "packages/eng-harness/tests/unit/adapters/test_toolport.py::test_unreleased_tools"
    covers: [AC17, AC38]
    depends_on: [T8]
  - id: T9
    title: Error and timeout mapping, the CSI error table (interim model_locked)
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.csi (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/_errors.py"
      - "packages/eng-harness/src/eng_harness/adapters/_toolport.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_errors.py"
      - "packages/eng-harness/tests/unit/adapters/test_csi_errors.py"
      - "packages/eng-harness/tests/unit/adapters/test_timeouts.py"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/adapters/test_csi_errors.py::test_mapping_table"
      - "packages/eng-harness/tests/unit/adapters/test_csi_errors.py::test_model_locked_interim"
      - "packages/eng-harness/tests/unit/adapters/test_timeouts.py::test_timeout_mapping"
    covers: [AC20, AC21]
    depends_on: [T8b]
  - id: T10
    title: Harness-side model identity (ADR-0032), CSI session operations, HostPort file and instance methods
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.csi (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/_identity.py"
      - "packages/eng-harness/src/eng_harness/adapters/_hostport.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_session_ops.py"
      - "packages/eng-harness/tests/unit/adapters/test_identity.py"
      - "packages/eng-harness/tests/workflow/adapters/__init__.py"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_session_ops.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/adapters/test_identity.py::test_resolution_rules"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_session_ops.py::test_working_copy_restore_save"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_session_ops.py::test_restore_after_timeout"
    covers: [AC15, AC30]
    depends_on: [T7, T9]
  - id: T11
    title: CSI model-state reader, model kinds, fingerprint and units read
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.csi, eng_harness.adapters.csi.products (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_state.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_replies.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/__init__.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/_etabs.py"
      - "packages/eng-harness/src/eng_harness/adapters/_hostport.py"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_state.py"
      - "packages/eng-harness/tests/workflow/adapters/test_units_after_timeout.py"
      - "packages/eng-harness/tests/property/test_fingerprint.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/adapters/test_csi_state.py::test_kinds_and_fingerprint"
      - "packages/eng-harness/tests/property/test_fingerprint.py::test_order_independent_and_edit_sensitive"
      - "packages/eng-harness/tests/workflow/adapters/test_units_after_timeout.py::test_units_trap"
    covers: [AC22, AC27]
    depends_on: [T10]
  - id: T12
    title: CSI edit kinds, read-back helpers and check_model
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.csi (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_tools.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_edits.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_checks.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_allowlist.toml"
      - "packages/eng-harness/src/eng_harness/adapters/_hostport.py"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_steps.py"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_edits.py"
      - "packages/eng-harness/tests/workflow/adapters/test_readback.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/adapters/test_csi_steps.py::test_step_mapping"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_edits.py::test_edit_kinds"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_edits.py::test_gaps_not_implemented"
      - "packages/eng-harness/tests/workflow/adapters/test_readback.py::test_mismatch_detected"
    covers: [AC24, AC25, AC26]
    depends_on: [T11]
  - id: T13
    title: CSI analysis, design and results through the long role
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.csi, eng_harness.adapters.csi.products (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_tools.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_replies.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/_etabs.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_allowlist.toml"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_analysis.py"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/workflow/adapters/test_csi_analysis.py::test_long_role_and_save_first"
    covers: [AC28]
    depends_on: [T12]
  - id: T14
    title: Reconciliation by reading model state, preview and read_back
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.csi (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_reconcile.py"
      - "packages/eng-harness/src/eng_harness/adapters/_toolport.py"
      - "packages/eng-harness/src/eng_harness/adapters/_ledger.py"
      - "packages/eng-harness/tests/workflow/adapters/test_reconcile.py"
    max_changed_lines: 350
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/adapters/test_reconcile.py::test_outcomes_per_tool"
      - "packages/eng-harness/tests/workflow/adapters/test_reconcile.py::test_long_tools_unknown_without_proof_of_end"
    covers: [AC23]
    depends_on: [T13]
  - id: T15
    title: ADR-0031 switch - model_locked as model_unlocked precondition and the approved unlock step (blocked until accepted)
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.csi (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_errors.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_tools.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_allowlist.toml"
      - "packages/eng-harness/tests/unit/adapters/test_csi_errors.py"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_unlock.py"
    max_changed_lines: 150
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/workflow/adapters/test_csi_unlock.py::test_unlock_under_approval"
    covers: [AC29]
    depends_on: [T14]
  - id: T16
    title: Command-line tool adapter (dxf-prep, etabs-model build)
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.cli (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/cli/__init__.py"
      - "packages/eng-harness/src/eng_harness/adapters/cli/_adapter.py"
      - "packages/eng-harness/src/eng_harness/adapters/_toolport.py"
      - "packages/eng-harness/tests/fakes/sasaah_cli/**"
      - "packages/eng-harness/tests/workflow/adapters/test_cli.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/adapters/test_cli.py::test_prepare_outputs_hashed"
      - "packages/eng-harness/tests/workflow/adapters/test_cli.py::test_build_config_and_pins"
      - "packages/eng-harness/tests/workflow/adapters/test_cli.py::test_timeout_no_effect"
    covers: [AC6, AC31, AC32]  # AC6: a timed-out tool step fails TIMEOUT_NO_EFFECT (B-378)
    depends_on: [T14]
  - id: T17
    title: Record mode, sanitizer and manifest, recorded-reply fake, contract tests on recordings
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.servers (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/servers/_record.py"
      - "packages/eng-harness/src/eng_harness/servers/__init__.py"
      - "packages/eng-harness/acceptance/recordings/README.md"
      - "packages/eng-harness/acceptance/scripts/record_csi.py"
      - "packages/eng-harness/tests/fakes/recorded/**"
      - "packages/eng-harness/tests/unit/servers/test_record.py"
      - "packages/eng-harness/tests/contract/test_csi_recordings.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/servers/test_record.py::test_sanitized_and_manifest"
      - "packages/eng-harness/tests/contract/test_csi_recordings.py::test_adapter_on_recordings"
      - "packages/eng-harness/tests/contract/test_csi_recordings.py::test_synthetic_matches_recordings"
    covers: [AC33, AC34]
    depends_on: [T16]
  - id: T18
    title: eng-harness doctor
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/pyproject.toml"
      - "packages/eng-harness/src/eng_harness/doctor.py"
      - "packages/eng-harness/tests/unit/test_doctor.py"
      - "packages/eng-harness/tests/windows/test_doctor.py"
    max_changed_lines: 350
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/test_doctor.py::test_checks_and_output"
      - "packages/eng-harness/tests/windows/test_doctor.py::test_integrity_level"
      - "packages/eng-harness/tests/unit/test_doctor.py::test_extra_checks_and_unreleased_tools"
    covers: [AC37, AC39]
    depends_on: [T7]
  - id: T19
    title: Port wiring, edit-cycle step sequence and crash matrix against real fake-server processes
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/__init__.py"
      - "packages/eng-harness/docs/local-testing.md"
      - "packages/eng-harness/tests/workflow/test_csi_cycle.py"
      - "packages/eng-harness/tests/replay/test_csi_resume.py"
      - "packages/eng-harness/tests/workflow/test_build_ports.py"
    max_changed_lines: 200
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/test_csi_cycle.py::test_cycle_steps"
      - "packages/eng-harness/tests/replay/test_csi_resume.py::test_crash_matrix"
      - "packages/eng-harness/tests/workflow/test_build_ports.py::test_allowlist_loaded_for_route"
    covers: [AC36, AC41]
    depends_on: [T17, T18, T20]
  - id: T20
    title: Framework additions for the IDEA adapter (routes, route key, audit_log flag, unit header) (B-085)
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.servers (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/servers/_config.py"
      - "packages/eng-harness/src/eng_harness/servers/_launch_args.py"
      - "packages/eng-harness/src/eng_harness/servers/_session.py"
      - "packages/eng-harness/src/eng_harness/adapters/_descriptors.py"
      - "packages/eng-harness/src/eng_harness/adapters/_allowlist.py"
      - "packages/eng-harness/tests/unit/servers/test_config.py"
      - "packages/eng-harness/tests/unit/servers/test_launch_args.py"
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py"
    max_changed_lines: 200
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/servers/test_config.py::test_audit_log_flag"
      - "packages/eng-harness/tests/unit/servers/test_config.py::test_route_key"
      - "packages/eng-harness/tests/unit/servers/test_launch_args.py::test_audit_log_default_and_off"
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py::test_routes_declared"
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py::test_route_filter"
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py::test_unit_header_entries"
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py::test_unit_header_missing_on_unserved_tool"
    covers: [AC40, AC41, AC42]
    depends_on: [T7]
---

# Implementation plan: eng-harness servers and adapters

## 1. Approach

Bottom-up, in the order the code imports itself, with the risky parts early: configuration (T1); processes and Job
Objects (T2, T3), because a wrong breakaway choice either kills an engineer's ETABS or orphans instances; the
synthetic fake (T4), which every later workflow test runs as a real process; the MCP session (T5); the build check
and allowlist (T6, T6b), the first safety gate of a run; the host-instance lock and guard (T7); the adapter framework (T8,
T8b, T9); then the CSI adapter in the order of the cycle: identity and session operations (T10), model state (T11), edits
and read-back (T12), analysis and design (T13), reconciliation (T14); the blocked ADR-0031 switch (T15); the
command-line tools (T16); record mode (T17); the doctor (T18); and an end-to-end task (T19) that wires the ports into
the engine and runs the crash matrix. T20 (B-085) adds the framework items that the IDEA adapter (spec 0014, item A1)
needs and that no CSI task uses.

Every task is test-first: its first commit is `test:` with the tests in `tests_first`, failing on `build/v1`
([process/05](../../../../design/process/05-testing-and-verification.md) §9). Each task adds a `CHANGELOG.md` line and
any public module to `[tool.eng-gate] public_modules`. Workflow tests start the synthetic fakes through the harness's
own launcher (POSIX in Linux CI); `tests/windows/` runs in the Windows CI job. Tasks that share a source file are
serialized by `depends_on`: `_session.py` (T5, T6b, T7, T20), `_toolport.py` (T8b, T9, T14, T16), `_hostport.py` (T10, T11,
T12), `csi/_tools.py` and `_allowlist.toml` (T12, T13, T15), `servers/__init__.py` (T1, T5, T17), `servers/_config.py` and `test_config.py` (T1, T6, T20),
`_allowlist.py` (T6, T6b, T20) and `test_allowlist.py` (T6, T20). Parallel tasks
(T3 beside T4; T18 beside T8 to T17) share only `CHANGELOG.md` and `pyproject.toml`, merged in pull-request order.

Reuse (spec §2): the MCP SDK's `Client` and message types (not its `stdio_client`), the S-10 job design, the S-02 and
S-04 call sequences, `eng-contract` for validation, units, envelopes, the store and identity revisions.

## 2. Tasks

**T1 Dependency and configuration** (spec §4.2). Package ADR `docs/adr/0001-mcp-python-sdk.md` (Proposed, owner
queue) for the runtime dependency `mcp>=2.3,<3` (MIT; its transitive licenses checked by the gate's license check);
`uv add` in the package; `ServersConfig` models loaded with `tomllib`; required timeouts; the forbidden options list;
`docs/local-testing.md` gains the spec's §12 list. Touches the root `pyproject.toml` only if the engine plan's T1 has
not yet added the package as a workspace member.

**T2 POSIX launcher and inspector** (§4.3.1). The ports, the process-group launcher, `/proc`-based identity with the
boot id, terminate through one handle (`pidfd` where available, else a start-time check immediately before the
signal). Test helpers under `tests/fakes/proc/` start children and grandchildren.

**T3 Windows launcher** (§4.3.1). `ctypes` declarations, `CreateProcessW` suspended with a handle list, the job with
kill-on-close and silent breakaway (server) or no breakaway (tool), `AssignProcessToJobObject`, `ResumeThread`, member
listing, the Windows inspector (`GetProcessTimes`, `OpenProcess` plus `TerminateProcess` on the same handle). Every
constant cites its header and Win32 page. The breakaway test is the case ADR-0030 asks `windows_check.py` to gain.

**T4 Synthetic CSI fake** (§4.8.3). Test code only (counts as tests for the budget): the server built with the SDK's
server API, `schemas.json` copied from the S-12 inventory for the allowlisted tools and the session tools, the
in-memory model, Sasaah reply shapes, faults from a control file, and the session behaviors of §4.8.3 (a
`timeout` invalidates the session and the next call re-attaches with `launched: false`; `csi_exit` acts on the
current target). Its contract test keeps the schemas equal to the
inventory; a packaging test proves `tests/` is not in the wheel.

**T5 Session** (§4.3.2, §4.3.3, §4.3.5). `ProcessTransport`, roles, `Client(mode, cache=None)`, per-call backstop
timeouts, crash detection, restart with re-attach, shutdown. Uses the synthetic fake.

**T6 Allowlist** (§4.3.4). Descriptors, the TOML allowlist with the deny list and pattern refusal, and the CSI
allowlist data, whose header names the S-12 commit; `test_against_inventory` checks the entries against the inventory.
AC38's load side (B-068): the `release` and `release_record` keys on allowlist entries (in `_allowlist.py`) and on
`[cli_tools.*]` entries (in T1's `servers/_config.py`, so T6 also owns that file and `test_config.py`), the
`{name: release_record}` mapping each exposes, and the load-time refusals. Budget 250 lines. T8b adds the
`ToolPort.unreleased_tools()` side. The original T6 (build check included, 400 lines, 430 with AC38) was split by B-342
(D-12).

**T6b Build check** (§4.5.1). The fingerprint of the tool list computed from the inventory and pinned in the allowlist
header (`fingerprint_source = "s12-inventory"`, `_allowlist.py` and `_allowlist.toml`), the build check and
`ServerCheck`; the workflow test stops a run through the engine's preflight. Budget 180 lines. T6b edits `_session.py`,
so T7 follows it.

**T7 Lock and guard** (§4.4). OS locks in the machine-level lock folder, holder records, stale handling; launched
instance identification by snapshot diff; launch ownership per role session counter; `close_started` rules with
the `csi_status` current-target check and the fallback; helper tracking.

**T8 Framework** (§4.5.2, §4.5.3). `validate_input` with `require_refs`, conversion by token, explicit target,
envelopes within the limits and provenance (the build comes from T6b's `ServerCheck`); harness kinds registered in
`_kinds.py`. Budget 180 lines. The original T8 (400 lines, 430 with AC38's port side) was split by B-342 (D-12).

**T8b ToolPort** (§4.5.3, §4.5.7 ledger). The write ledger with `fsync`, `ToolPort.describe` and `call` over T8's layers,
and `ToolPort.unreleased_tools()` over T6's two mappings (AC38's port side, `test_toolport.py::test_unreleased_tools`;
B-068). Budget 250 lines. T9 and later tasks that edit `_toolport.py` follow T8b.

**T9 Errors and timeouts** (§4.5.5, §4.5.6). The mapping table as data with Sasaah source lines, the timeout and
backstop rules, wedged state and epochs; `model_locked` interim mapping (`HOST_LOCKED`) per ADR-0031 decision 5.

**T10 Identity and session operations** (§4.5.9, ADR-0032). The identity store, launch and open of a working copy,
save with hash and identity update, restore (a new hidden instance when launch ownership is lost), `locate`,
`model_files`.

**T11 Model state** (§4.6.4). The read set, the six model kinds and the status, the fingerprint, `LIMIT_EXCEEDED` on
truncation, outside-edit detection, `read_units`; the units-trap workflow test with the synthetic fault.

**T12 Edits and read-back** (§4.6.1, §4.6.2, §4.5.8). Argument models and builders per edit kind, the
`NotImplementedGap` entries H-G1 to H-G3 and the seismic exclusion, read-back helpers, `check_model` with the basis
tolerance.

**T13 Analysis and design** (§4.6.1 steps 11 to 13). Long-role routing, analysis status, design run and results, the
three force kinds, analysis messages.

**T14 Reconciliation** (§4.5.7). The per-tool rules with pre-images and evidence, `read_back`, `preview`;
analysis and design reconcile `unknown` while no proof of end exists (gap H-G7).

**T15 ADR-0031 switch.** Blocked until the owner accepts ADR-0031 and `eng-contract` releases `model_unlocked` and
`server_owned_instance`. Then: the new mappings, `csi_unlock_model` on the allowlist with action `unlock`, and the
interim test replaced, because the accepted ADR changes the specified behavior (a spec change, not a test changed to
pass). The engine's action-based always-ask list (engine spec 0001 §4.7: action `delete`, saves over an original)
gains the action `unlock` in the engine plan, not here; the edit-cycle workflow's existing tool-name entry
`always_ask=("csi_unlock_model",)` matches it and stays.

**T16 Command-line tools** (§4.7). Tool jobs, attempt folders, hashed inputs and outputs, the configuration rewrite,
build-artifact pins, exit-code mapping, reconciliation by completion record; a Python stand-in for the scripts.

**T17 Record mode** (§4.8.1, §4.8.2). The recording transport wrapper, the sanitizer, the manifest, the recorded-reply
fake, the contract and fidelity tests (skipped with a reason until the owner commits recordings), the owner's record
script and its README.

**T18 Doctor** (§4.9). The checks behind interfaces (installed programs, integrity level, location probe), table and
JSON output, exit codes; the unreleased-tools check and the `extra_checks` extension point for spec 0006 (AC39, B-068).

**T19 End to end.** `build_ports` wiring; a test block that runs the cycle's steps through the real engine and real
fake-server processes; the crash matrix that kills the engine at each write step and resumes. Completes
`docs/local-testing.md`. `build_ports` loads each allowlist for its server section's `route` (T20); the route-bearing
case is tested in `test_build_ports.py` with a synthetic routed allowlist (test data, product-neutral), since the CSI
cycle has no route (AC41).

**T20 Framework additions for the IDEA adapter** (AC40 to AC42, spec §11 A3, B-085). `audit_log` on the server
section (default true) and the argv builder `servers/_launch_args.py`, wired into `_session.py`, so the CSI argv stays
as it is and a section with `audit_log = false` gets no `--audit-log`; the `route` key and the allowlist header
`routes` with the entries' `routes` and loading for one route; the header `[[unit]]` entries with `unit_status` on the
descriptors and `Allowlist.units`, where a `missing` entry may name an unserved tool. Product-neutral: no module names IDEA. The IDEA server section, its options and its allowlist are plan
0014 T1 and T3, which start after this task; the issue codes, host codes and harness kinds of A3 are implemented where
they are used (plan 0014 T5, T7, T8).

## 3. Dependencies

- Runtime: `mcp` 2.x (package ADR in T1, owner queue); `eng-contract`, `pydantic` as in the engine plan. No other.
- Development: the root workspace group; no new development dependency.
- Work items: the engine plan's ([0001-engine](0001-engine.md)) T1 (package skeleton) before this plan's T1; its T6
  (ports, port data types and fakes) before T8; its run loop, invariants and replay tasks before the workflow and
  replay tests that run the real engine (T6b's `test_build_mismatch_stops_run`, T11's units trap, T19). `eng-contract`
  0.1.0 merged. T15 waits for ADR-0031 and an `eng-contract` minor release.

## 4. Verification

- Local gate per task (`uv run eng-gate check` once available; until then ruff, mypy strict and pytest with coverage
  from `packages/eng-harness/`); the pull request links its CI run.
- Windows CI job: `tests/windows/` (jobs, breakaway, inspector, doctor integrity level).
- Needs local test (spec §12, listed in `docs/local-testing.md`): everything that drives `sasaah-csi-mcp`, ETABS or
  the PowerShell tools, including the breakaway of a server-launched ETABS, the long-role attach, the live
  fingerprint, the table keys, timeouts and reconciliation with S-02, fingerprint stability with S-04, the doctor and
  record mode on the owner's machine.
- Review: correctness, Python, type-design, silent-failure and test lenses on every task; the security lens on T1
  (configuration), T3 (process creation, handle inheritance), T7 (locks, terminating processes), T16 (running scripts
  with arguments) and T17 (sanitizing recordings); R1 review against the spec's reconciliation and units rules on T9,
  T11, T12, T14. Second-family review and owner approvals are `awaiting owner` (ADR-0028 §4).

## 5. Rollback

Each task is one squash-merged pull request into `build/v1`; reverting it removes it and its dependants. Nothing here
writes to a host program in CI. The allowlist and its fingerprint are data: a wrong pin is fixed forward by a new
header, and a run against an untested build is refused by the build check rather than run.
