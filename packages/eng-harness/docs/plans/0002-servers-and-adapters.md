---
id: plan-b061-servers-and-adapters
issue: "B-061"
spec: packages/eng-harness/docs/specs/0002-servers-and-adapters.md
status: draft            # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1, r2, r3]       # binding for every pull request of this plan; r3 because T1 touches pyproject.toml and uv.lock; r2 because T21 adds eng_harness/kinds/csi.py (amendment B-537)
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
    # Amendment (B-413, documents only): test_build_mismatch_stops_run (the engine stop of AC9, engine AC44) moves to
    # T19a (B-475), so T6b does not wait for engine T13; the workflow fixture's build pins and the fake's script_enabled join the files.
    # Amendment (B-413, documents only): the check is a ServerManager constructor argument, run by _session.py only on a
    # restart (engine calls preflight at start and resume); the fixture uses sasaah-csi-mcp only for the CSI fake, the PAGED double keeps its adapter.
    # Amendment (B-413, documents only): test_restart_repeats_build_check covers AC11's build-check clause on a restart.
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
      - "packages/eng-harness/tests/workflow/conftest.py"  # build pins from the SHA-256 of sys.executable and the allowlist's sasaah_commit (B-413)
      - "packages/eng-harness/tests/fakes/sasaah_csi/server.py"  # csi_status reports script_enabled false, spec §4.3.4 item 5 (B-413)
    max_changed_lines: 180
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/servers/test_buildcheck.py::test_fingerprint_definition"
      - "packages/eng-harness/tests/unit/servers/test_buildcheck.py::test_each_mismatch"
      - "packages/eng-harness/tests/contract/test_csi_allowlist.py::test_pinned_fingerprint_from_inventory"
      - "packages/eng-harness/tests/workflow/servers/test_session.py::test_restart_repeats_build_check"
    covers: [AC9, AC10, AC11]
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
    # Amendment (B-413, documents only): the synthetic CSI fake joins the files (a restore needs a distinct launched instance).
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.csi (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/_identity.py"
      - "packages/eng-harness/src/eng_harness/adapters/_hostport.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_session_ops.py"
      - "packages/eng-harness/tests/unit/adapters/test_identity.py"
      - "packages/eng-harness/tests/workflow/adapters/__init__.py"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_session_ops.py"
      - "packages/eng-harness/tests/fakes/sasaah_csi/**"  # the fake's behaviour for the session operations, test code (B-413)
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/adapters/test_identity.py::test_resolution_rules"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_session_ops.py::test_working_copy_restore_save"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_session_ops.py::test_restore_after_timeout"
    covers: [AC15, AC30]
    depends_on: [T7, T9]
  - id: T11
    title: CSI reply mapping to the six model kinds and the model status
    # Amendment (B-450, D-12): split from the reader (now T11b); the B-130 writer measured 581 counted lines for the
    # whole task (the reply mapping alone about 385).
    files:
      - "packages/eng-harness/pyproject.toml"
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_replies.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/__init__.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/_etabs.py"
      - "packages/eng-harness/tests/unit/adapters/test_csi_replies.py"
      - "packages/eng-harness/tests/fakes/sasaah_csi/**"
    max_changed_lines: 390
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/adapters/test_csi_replies.py::test_six_kinds_and_status_validate"
    covers: [AC27]
    depends_on: [T10]
  - id: T11b
    title: CSI model-state reader, fingerprint and units read
    # Amendment (B-450, D-12): the reader half of the former T11. tests/property/test_fingerprint.py is shared with
    # calcs plan 0003 T7 (and later the SAFE and SAP2000 plans), so T11b merges after calcs T7.
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_state.py"
      - "packages/eng-harness/src/eng_harness/adapters/_hostport.py"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_state.py"
      - "packages/eng-harness/tests/property/test_fingerprint.py"
      - "packages/eng-harness/tests/fakes/sasaah_csi/**"
    max_changed_lines: 250
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/workflow/adapters/test_csi_state.py::test_kinds_and_fingerprint"
      - "packages/eng-harness/tests/property/test_fingerprint.py::test_order_independent_and_edit_sensitive"
    covers: [AC27]
    depends_on: [T11]
  - id: T12
    title: CSI edit kinds and the tool port over them
    # Amendment (B-413, documents only): the synthetic CSI fake joins the files (its edit tools must apply the writes they report).
    # Amendment (B-465, D-12): split from the read-back and check_model (now T12b); the B-131 writer measured about 621
    # counted lines for the whole task, 301 for this half. The binder is given the tool's descriptor (_toolport.py), and
    # the reader's fingerprint gains the wall-section table (_state.py, products/_etabs.py; spec 4.6.4). Estimate: 301,
    # _toolport.py about +6, _tools.py about -12 (the context variable goes), _state.py and _etabs.py about +5: about
    # 300; budget 340.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.csi (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_tools.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_edits.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_allowlist.toml"
      - "packages/eng-harness/src/eng_harness/adapters/_toolport.py"  # ModelBinder.binding is given the descriptor (B-465)
      - "packages/eng-harness/src/eng_harness/adapters/csi/_state.py"  # the wall-section table in the fingerprint (B-465)
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/_etabs.py"  # that table's key, OQ-G10 (B-465)
      - "packages/eng-harness/tests/unit/adapters/test_toolport.py"  # the binder's new argument (B-465)
      - "packages/eng-harness/tests/workflow/adapters/test_csi_steps.py"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_edits.py"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_state.py"  # a wall-thickness edit moves the fingerprint (B-465)
      - "packages/eng-harness/tests/fakes/sasaah_csi/**"  # applies the §4.6.2 edit tools, loads and restraints, test code (B-413)
    max_changed_lines: 340
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/adapters/test_csi_steps.py::test_step_mapping"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_edits.py::test_edit_kinds"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_edits.py::test_gaps_not_implemented"
    covers: [AC25, AC26, AC27]  # AC27: the wall-section table in the fingerprint (B-465 fix round)
    depends_on: [T11b]
  - id: T12b
    title: CSI read-back helpers and check_model
    # Amendment (B-465, D-12): the read-back half of the former T12 (work item B-466); the B-131 draft measured about 322
    # counted lines (_checks.py 282, _hostport.py about 40). It also takes the read-back table keys and columns into the
    # product module (OQ-G10), the write hook in csi/_tools.py with the wrote() calls, and the take_warnings() drain
    # (B-451 L4). Estimate: _checks.py 282, _hostport.py about 40 plus about 4 (wrote, the drain), the _tools.py hook
    # about 10, the columns in the product profile about 6 (the constants leave _checks.py), CHANGELOG and ratchet 3:
    # about 345; plus 10 percent, 380 (the cap). The saved fingerprint (B-451 L3, about 13) is T19a's (B-475), so it fits.
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_checks.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_tools.py"  # CsiToolPort records each write (B-465)
      - "packages/eng-harness/src/eng_harness/adapters/_hostport.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/__init__.py"  # the profile carries the read-back columns (B-465)
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/_etabs.py"  # read-back table keys and columns, OQ-G10 (B-465)
      - "packages/eng-harness/tests/workflow/adapters/test_readback.py"
      - "packages/eng-harness/tests/fakes/sasaah_csi/**"  # read-back tables, test code (B-413)
    max_changed_lines: 380
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/adapters/test_readback.py::test_mismatch_detected"
    covers: [AC24]
    depends_on: [T12]
  - id: T13
    title: CSI analysis, design and results through the long role
    # Amendment (B-413, documents only): the synthetic CSI fake joins the files (analysis status, design results, forces).
    # Amendment (B-465, documents only): waits for T12b (the T12 split); the T11 mappers' bare errors (B-451 L1) are T13's.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.csi, eng_harness.adapters.csi.products (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_tools.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_replies.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/_etabs.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_allowlist.toml"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_analysis.py"
      - "packages/eng-harness/tests/unit/adapters/test_csi_replies.py"  # the mappers raise UNEXPECTED_REPLY (B-451 L1, B-465)
      - "packages/eng-harness/tests/fakes/sasaah_csi/**"  # analysis, design and result replies, test code (B-413)
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/workflow/adapters/test_csi_analysis.py::test_long_role_and_save_first"
    covers: [AC28]
    depends_on: [T12b]
  - id: T14
    title: Reconciliation by reading model state, preview and read_back
    # Amendment (B-413, documents only): the synthetic CSI fake joins the files (timeout_after_apply leaves each write applied).
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.csi (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_reconcile.py"
      - "packages/eng-harness/src/eng_harness/adapters/_toolport.py"
      - "packages/eng-harness/src/eng_harness/adapters/_ledger.py"
      - "packages/eng-harness/tests/workflow/adapters/test_reconcile.py"
      - "packages/eng-harness/tests/fakes/sasaah_csi/**"  # fault behaviour per write tool, test code (B-413)
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
    # Amendment (B-504, documents only): tests/unit/test_runner.py joins the files for one test-helper fix: _meta_run_id
    # closes its journal connection (the `with` form only commits), found by T16's local CI run (B-135); test code, not counted.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.cli (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/cli/__init__.py"
      - "packages/eng-harness/src/eng_harness/adapters/cli/_adapter.py"
      - "packages/eng-harness/src/eng_harness/adapters/_toolport.py"
      - "packages/eng-harness/tests/fakes/sasaah_cli/**"
      - "packages/eng-harness/tests/workflow/adapters/test_cli.py"
      - "packages/eng-harness/tests/unit/test_runner.py"  # _meta_run_id closes its connection (B-504)
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
    # Amendment (B-413, documents only): the Windows test is test_doctor_windows.py, since without __init__.py files mypy
    # would name both tests/unit/test_doctor.py and tests/windows/test_doctor.py "test_doctor" (duplicate module).
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/pyproject.toml"
      - "packages/eng-harness/src/eng_harness/doctor.py"
      - "packages/eng-harness/tests/unit/test_doctor.py"
      - "packages/eng-harness/tests/windows/test_doctor_windows.py"
    max_changed_lines: 350
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/test_doctor.py::test_checks_and_output"
      - "packages/eng-harness/tests/windows/test_doctor_windows.py::test_integrity_level"
      - "packages/eng-harness/tests/unit/test_doctor.py::test_extra_checks_and_unreleased_tools"
    covers: [AC37, AC39]
    depends_on: [T7]
  - id: T19c
    title: HostPort lease, preflight and epoch, run-state reload and the saved fingerprint on the CSI host port
    # Amendment (B-530, documents only): new, split from T19a after the pre-flight audit. AdapterHostPort lacks the
    # HostPort methods preflight, session_epoch, acquire and release, never reads run_dir/adapter/state.json back, and
    # its persisted instance rows lack the start time, observation time and exe name that HostLocks and OpenedInstance
    # need (spec 4.4.1, 4.5.9; reloaded instances take session -1, bindings reload too). The saved fingerprint
    # (B-451 L3) moves here from T19a. Estimate: host methods and reload about 55, the saved fingerprint about 13, the
    # persisted rows about 12: about 80; budget 90 (merged analogs T10 400, T12b 380 bound it from above).
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/_hostport.py"
      - "packages/eng-harness/src/eng_harness/adapters/_identity.py"  # record_save keeps the saved state's fingerprint (B-465)
      - "packages/eng-harness/tests/workflow/adapters/test_csi_session_ops.py"  # T10's test: the saved fingerprint (B-465)
      - "packages/eng-harness/tests/workflow/adapters/test_csi_host_resume.py"
    max_changed_lines: 90
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/workflow/adapters/test_csi_session_ops.py::test_save_records_the_state_fingerprint"  # B-451 L3
      - "packages/eng-harness/tests/workflow/adapters/test_csi_host_resume.py::test_lease_preflight_and_epoch"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_host_resume.py::test_new_port_restores_from_run_state"
    covers: [AC47]
    depends_on: [T12b]  # external: plan 0007 T13 (B-522, merged; also edits _hostport.py)
  - id: T19a
    title: Port wiring for the CSI adapter (ETABS), edit-cycle step sequence and crash matrix against real fake-server processes
    # Amendment (B-413, documents only): runs the real engine, so it waits for engine plan 0001 T13, T15, T16, T16b (B-499) and T19;
    # it also takes the two engine stops left out of T6b and T11 (AC9's engine clause, AC22), which fail at its base
    # because build_ports does not exist there yet.
    # Amendment (B-465, documents only): takes the saved fingerprint (B-451 L3) from the T12 split, about 13 counted
    # lines (record_save in _identity.py, the save line in _hostport.py); budget 200 + 15.
    # Amendment (B-475, documents only): T19 split into T19a and T19b (shorter first-live-run path, lead decision D-32).
    # The SAFE engine stop test_safe_build_mismatch_stops_run moves to plan 0008 T3, so T19a no longer waits for plan
    # 0008 T3; the command-line adapter wiring moves to T19b, and build_ports refuses [cli_tools.*] entries with
    # NOT_IMPLEMENTED (gap H-G8, spec AC43) until T19b. T17 leaves depends_on (no shared file; the CSI fake chain ends at
    # T14). Budget 215 + 15 for the refusal (about 10 lines in adapters/__init__.py, 3 of CHANGELOG.md; an estimate).
    # Amendment (B-495, documents only): owner answer of 2026-11-14 (spec section 11 Q9): the refusal exits 2 (USAGE),
    # not 70; cli/_exit.py maps its code NOT_IMPLEMENTED to 2 (spec 0006 section 6), about 1 line; budget 230 + 5.
    # The case ("NOT_IMPLEMENTED", 2) joins the error-code table test tests/unit/cli/test_exit_codes.py (test code).
    # Amendment (B-503, documents only): the first-live-run wiring gaps (spec AC44, AC45; closes H-G9): the read-back
    # tolerance provider (about 20 lines in adapters/__init__.py, 8 in _hostport.py), the shared written-items book,
    # host.wrote, the CSI reconciler, the run's Revisions and host.reopened passed to CsiToolPort (about 10), the
    # pre-image on a write's binding and ToolPort.preview in _toolport.py (about 8 and 28, its refusal of a binding without host included), 2 of
    # CHANGELOG.md: budget 235 + 78 = 313 (an estimate). CSI_KINDS reach the run's registry through T21; Revisions comes from plan 0007 T5
    # and reopened from plan 0007 T13, so T19a waits for both (section 3).
    # Amendment (B-530, documents only): pre-flight audit. The HostPort methods, the run-state reload and the saved
    # fingerprint move to the new T19c, which T19a waits for (the crash matrix needs them); _identity.py and
    # test_csi_session_ops.py leave the files. Added: the production binder (AdapterHostPort.binding and revision,
    # about 35), the reconciler's tolerance provider (csi/_reconcile.py, about 6), the keyword seams of build_ports
    # (spec 4.1, about 25), the route argument of csi_allowlist (csi/__init__.py, about 2) and record_pre_image in
    # _toolport.py (about 3). Estimate 313 - 13 + 35 + 6 + 25 + 2 + 3 = about 371, rounded to 380.
    # Amendment (B-543, documents only): build_ports takes the keyword visible and gives it to AdapterHostPort, and
    # passes host.open_original to CsiToolPort as opener (spec 4.1 item 6, 4.5.9; built by T23, which T19a now waits
    # for); about 4 lines in adapters/__init__.py; and preview answers a tool with action open on a key with no bound
    # model with models empty instead of the model_open refusal (spec 4.5.9, AC45), about 4 lines in _toolport.py:
    # estimate 371 to 379, budget 380 unchanged. test_cycle_steps opens the original through the step 2 tool step
    # (spec 0007 4.5).
    # Amendment (B-541, documents only): first-live-run gaps, third set. T19a waits for the new T22, which defines
    # AdapterPorts (with its servers field and async context), the platform launcher and inspector, servers_config and
    # ServersConfig.host_program (spec 4.1, AC48 to AC50). build_ports types config as ServersConfig, returns
    # AdapterPorts(tool_port, host_port, servers), names the host port's program product.lower() and takes exe_name
    # and host_exes from host_program(product) (spec 4.1); its workflow tests enter the ports around Engine.start and Engine.resume (test
    # code). Estimate unchanged at about 371: the AdapterPorts class and the platform default it no longer writes offset
    # the servers field and the host_program call; files and budget unchanged.
    # Amendment (B-562, documents only): record the CSI original-open content guarantee in the journal (AC52).
    # Keep write recovery and complete the post-open lifecycle. The regressions below accompany the implementation.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/__init__.py"
      - "packages/eng-harness/src/eng_harness/adapters/_hostport.py"  # the tolerance provider (B-503); binding and revision (B-530)
      - "packages/eng-harness/src/eng_harness/adapters/_toolport.py"  # pre-image on a write's binding, preview (B-503); record_pre_image (B-530)
      - "packages/eng-harness/src/eng_harness/adapters/csi/_reconcile.py"  # the tolerance provider of CsiReconciler (B-530)
      - "packages/eng-harness/src/eng_harness/adapters/csi/_revisions.py"  # CSI descriptor capability (B-562)
      - "packages/eng-harness/src/eng_harness/adapters/csi/__init__.py"  # csi_allowlist takes a route (B-530)
      - "packages/eng-harness/src/eng_harness/cli/_exit.py"  # NOT_IMPLEMENTED to exit 2, spec 0006 section 6 (B-495)
      - "packages/eng-harness/src/eng_harness/ports.py"
      - "packages/eng-harness/src/eng_harness/journal/_events.py"
      - "packages/eng-harness/src/eng_harness/engine/_ctx_impl.py"
      - "packages/eng-harness/src/eng_harness/engine/_inflight.py"
      - "packages/eng-harness/src/eng_harness/engine/_hoststate.py"
      - "packages/eng-harness/src/eng_harness/engine/_hostsafety.py"
      - "packages/eng-harness/src/eng_harness/engine/_modes.py"  # distinguish a replayed copy from a still-live one
      - "packages/eng-harness/docs/local-testing.md"
      - "packages/eng-harness/tests/workflow/test_csi_cycle.py"
      - "packages/eng-harness/tests/replay/test_csi_resume.py"
      - "packages/eng-harness/tests/replay/test_host_state.py"
      - "packages/eng-harness/tests/workflow/test_build_ports.py"
      - "packages/eng-harness/tests/workflow/servers/test_session.py"  # the ETABS stop (from T6b), B-413; the SAFE stop is plan 0008 T3's (B-475)
      - "packages/eng-harness/tests/workflow/adapters/test_csi_revisions.py"
      - "packages/eng-harness/tests/workflow/adapters/test_units_after_timeout.py"  # test_units_trap (from T11, B-413)
      - "packages/eng-harness/tests/fakes/sasaah_csi/**"  # test code (B-413)
      - "packages/eng-harness/tests/unit/cli/test_exit_codes.py"  # the NOT_IMPLEMENTED case (B-495)
      - "packages/eng-harness/tests/unit/test_engine_edit_cycle_amendments.py"
      - "packages/eng-harness/tests/unit/test_journal_events.py"
    max_changed_lines: 380
    max_sessions: 4  # amendment B-563: one additional writer session (was 3)
    tests_first:
      - "packages/eng-harness/tests/workflow/test_csi_cycle.py::test_cycle_steps"
      - "packages/eng-harness/tests/replay/test_csi_resume.py::test_crash_matrix"
      - "packages/eng-harness/tests/workflow/test_build_ports.py::test_allowlist_loaded_for_route"
      - "packages/eng-harness/tests/workflow/test_build_ports.py::test_cli_tools_not_wired_gap"
      - "packages/eng-harness/tests/unit/cli/test_exit_codes.py::test_error_codes"  # case NOT_IMPLEMENTED -> 2 (B-495)
      - "packages/eng-harness/tests/workflow/servers/test_session.py::test_build_mismatch_stops_run"
      - "packages/eng-harness/tests/workflow/adapters/test_units_after_timeout.py::test_units_trap"
      - "packages/eng-harness/tests/workflow/test_build_ports.py::test_readback_tolerance_from_run_basis"  # AC44 (B-503)
      - "packages/eng-harness/tests/workflow/test_build_ports.py::test_csi_wiring_shares_book_and_pre_image"  # AC45 (B-503)
      - "packages/eng-harness/tests/workflow/test_build_ports.py::test_csi_preview_sends_no_write"  # AC45 (B-503)
      - "packages/eng-harness/tests/workflow/test_build_ports.py::test_binder_from_host_port"  # the production binder (B-530)
      - "packages/eng-harness/tests/workflow/test_build_ports.py::test_open_preview_without_binding"  # AC45 (B-543)
    covers: [AC9, AC22, AC36, AC41, AC43, AC44, AC45, AC52]  # AC43: only its interim refusal (gap H-G8); T19b covers the rest
    depends_on: [T14, T18, T19c, T20, T21, T22, T23]  # external: engine plan 0001 T13, T15, T16, T16b and T19; plan 0007 T5 and T13 (section 3); T22 by B-541, T23 by amendment B-543
  - id: T19b
    title: Command-line tool adapter in build_ports (closes gap H-G8)
    # Amendment (B-475, documents only): new, split from T19. Off the first-live-run path: it returns with the DXF start,
    # the first workflow that names a command-line tool (section 3). Replaces T19a's H-G8 gap test, because the specified
    # behavior changes (spec AC43; a spec change, not a test changed to pass). Budget an estimate.
    files:
      - "packages/eng-harness/pyproject.toml"
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/__init__.py"
      - "packages/eng-harness/docs/local-testing.md"
      - "packages/eng-harness/tests/workflow/test_build_ports.py"
    max_changed_lines: 120
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/workflow/test_build_ports.py::test_cli_tool_routed_through_build_ports"
    covers: [AC43]
    depends_on: [T16, T19a]
  - id: T20
    title: Framework additions for the IDEA adapter (routes, route key, audit_log flag, unit header) (B-085)
    # Amendment (B-413, documents only): test_route_key leaves tests_first (no config-level route rule fails at the base;
    # AC41 makes every route rule of the framework an allowlist load error; the IDEA section's configuration check for a
    # missing route is plan 0014 T1's, spec 0014 AC1); a route on a CSI section is covered in test_route_filter.
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
      - "packages/eng-harness/tests/unit/servers/test_launch_args.py::test_audit_log_default_and_off"
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py::test_routes_declared"
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py::test_route_filter"
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py::test_unit_header_entries"
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py::test_unit_header_missing_on_unserved_tool"
    covers: [AC40, AC41, AC42]
    depends_on: [T7]
  - id: T21
    title: CSI harness kinds in a kinds module, registered in HARNESS_KINDS
    # Amendment (B-503, documents only): new. A store over HARNESS_KINDS refuses an analysis or design result today, and
    # the edit-cycle calcs of plan 0007 T4 cannot import CsiRows from adapters/csi/_replies.py (spec 0003 4.3). Moves the
    # six payload models and CSI_KINDS (about 60 lines of _replies.py) to kinds/csi.py; _replies.py re-exports them;
    # _kinds.py extends HARNESS_KINDS with CSI_KINDS. Three tests that extend HARNESS_KINDS with CSI_KINDS (two merged,
    # one added by plan 0007 T5, which T21 follows) take HARNESS_KINDS as it is (one line each, test code). Budget: about
    # 65 added and 60 removed lines, 2 in _kinds.py, 2 in pyproject.toml, 2 of CHANGELOG.md: 131; 150 (an estimate).
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.kinds.csi
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/kinds/csi.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_replies.py"
      - "packages/eng-harness/src/eng_harness/_kinds.py"
      - "packages/eng-harness/tests/contract/test_csi_kinds.py"
      - "packages/eng-harness/tests/rules/test_calc_modules.py"  # the admitted module eng_harness.kinds.csi (spec 0003 4.3)
      - "packages/eng-harness/tests/workflow/adapters/test_reconcile.py"  # HARNESS_KINDS already holds CSI_KINDS
      - "packages/eng-harness/tests/workflow/adapters/test_csi_analysis.py"  # HARNESS_KINDS already holds CSI_KINDS
      - "packages/eng-harness/tests/workflow/adapters/test_csi_read_state_tool.py"  # added by plan 0007 T5; HARNESS_KINDS already holds CSI_KINDS
    max_changed_lines: 150
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/contract/test_csi_kinds.py::test_csi_kinds_registered"
    covers: [AC46]
    depends_on: [T13]  # external: plan 0007 T5 (section 3)
  - id: T22
    title: Platform launcher for doctor and build_ports, AdapterPorts lifetime, server sections from parsed tables, host program of a product
    # Amendment (B-541, documents only): new, first-live-run gaps, third set (launch). Doctor started its roles through
    # the POSIX launcher (fails on Windows at construction) and windows_launcher() had no caller; nothing entered or left
    # the ServerManager context; build_ports' config was untyped; no rule named a server's host program (spec 4.1,
    # 4.2 rule 6, 4.9; AC48 to AC50). Before T19a, which builds AdapterPorts with these pieces, and before plan 0006
    # T16, which calls doctor.run with the new arguments. Estimate (fix round 1 of B-541, docstrings counted): the
    # factory with its importlib branches and the POSIX narrowing about 30, doctor's private _inspector removed about 8,
    # doctor (LiveRoles.__init__, the _gather parameter, run's config_path=None and env) about 15, servers_config split
    # out of load_servers_config with the byte-order mark about 15, host_program about 10, AdapterPorts about 22,
    # exports about 5, local-testing.md 3, CHANGELOG.md 3: about 111; budget 115.
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/local-testing.md"
      - "packages/eng-harness/src/eng_harness/servers/__init__.py"
      - "packages/eng-harness/src/eng_harness/servers/_platform.py"
      - "packages/eng-harness/src/eng_harness/servers/_config.py"
      - "packages/eng-harness/src/eng_harness/doctor.py"
      - "packages/eng-harness/src/eng_harness/adapters/__init__.py"
      - "packages/eng-harness/tests/unit/servers/test_platform.py"
      - "packages/eng-harness/tests/unit/servers/test_config.py"
      - "packages/eng-harness/tests/unit/test_doctor.py"
      - "packages/eng-harness/tests/unit/adapters/test_ports.py"
      - "packages/eng-harness/tests/windows/test_platform_windows.py"
    max_changed_lines: 115
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/unit/adapters/test_ports.py::test_ports_enter_and_leave_server_manager"
      - "packages/eng-harness/tests/unit/servers/test_platform.py::test_platform_pair"
      - "packages/eng-harness/tests/unit/test_doctor.py::test_live_roles_use_platform_launcher"
      - "packages/eng-harness/tests/unit/test_doctor.py::test_no_config_file_and_environment"
      - "packages/eng-harness/tests/unit/servers/test_config.py::test_servers_config_from_tables"
      - "packages/eng-harness/tests/unit/servers/test_config.py::test_byte_order_mark_accepted"
      - "packages/eng-harness/tests/unit/servers/test_config.py::test_host_program_of_product"
    covers: [AC48, AC49, AC50]
    depends_on: [T18, T20]  # both merged (doctor.py, servers/_config.py); T19a and plan 0006 T16 wait for T22 (section 3)
  - id: T23
    title: The CSI host port opens the original for the step 2 open and launches visible on request
    # Amendment (B-543, documents only): new (spec 4.5.9 "Opening the original", AC51; spec 0007 4.5 step 2). The merged
    # CsiToolPort refuses csi_open_model by name, outside its try (an unknown-outcome write for the engine), and nothing
    # opens and binds the original, so copy_on_open takes no working copy; every launch is hidden. Estimate:
    # AdapterHostPort.open_original and the visible keyword about 16 (_hostport.py), the visible launch about 5
    # (csi/_session_ops.py), the opener keyword, the routing of csi_open_model inside the try and the optional path of
    # OpenModelArgs about 22 (csi/_tools.py), 1 of CHANGELOG.md: about 44 (measured 77 by the B-550 writer, an estimate only: CHANGELOG.md 1, _hostport.py 17, _session_ops.py 9,
    # _tools.py 50); budget 80. Before T19a, whose cycle test
    # opens the original through it and which wires opener and visible in build_ports; after T19c (merged), the last
    # task that edited _hostport.py; plan 0002 T15 also edits csi/_tools.py, without an order (whichever lands second adapts).
    # Amendment (B-554, documents only, 2026-11-17): test_csi_revisions.py joins files, because spec 4.5.9 and AC51 turn the
    # csi_open_model refusal into a failure envelope and its test test_open_model_is_not_a_tool_of_the_workflow asserted the
    # old raised ContractError; max_changed_lines 60 to 80 from the measured 77 (an estimate only, owner decision of 2026-11-17).
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/_hostport.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_session_ops.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_tools.py"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_open_original.py"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_revisions.py"  # test_open_model_is_not_a_tool_of_the_workflow now expects the INVALID_ARGUMENT failure envelope, test code (B-554)
    max_changed_lines: 80
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/workflow/adapters/test_csi_open_original.py::test_open_original_then_working_copy"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_open_original.py::test_open_refusals_are_envelopes"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_open_original.py::test_visible_launch"
    covers: [AC51]
    depends_on: [T19c]  # external: plan 0007 T5 and T13 (merged; csi/_tools.py and _hostport.py)
  - id: T24
    title: "Mutation scope: the section 9 modules in r1_modules"
    # Amendment (B-601, owner decision D-46, 2026-11-20): CI mutates only modules listed in
    # [tool.eng-gate] r1_modules; spec 0002 section 9 names seven R1 modules that are merged but
    # absent from that list, so they have never been mutated. This task adds those paths to
    # r1_modules, adds a contract guard that the section 9 list is covered by a glob, and
    # strengthens the existing unit and workflow tests until each module reaches mutation_min
    # (80 %) with real tests. No exclusions, pragmas or lowered thresholds; no module may be
    # removed from r1_modules to pass MU001. No source module is listed: the work strengthens
    # tests only. If a module cannot reach 80 % without a source change, the implementing
    # writer reports NEEDS_PLAN_AMENDMENT.
    files:
      - "packages/eng-harness/pyproject.toml"  # r1_modules entries for the listed modules only, amendment B-601
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/tests/contract/test_mutation_scope.py"  # shared by the five B-601 tasks; this task adds test_spec_0002_section_9_modules_in_r1
      - "packages/eng-harness/tests/unit/adapters/test_csi_errors.py"  # adapters/_errors.py and adapters/csi/_errors.py
      - "packages/eng-harness/tests/unit/adapters/test_timeouts.py"  # adapters/_errors.py timeout paths
      - "packages/eng-harness/tests/workflow/adapters/test_reconcile.py"  # adapters/csi/_reconcile.py
      - "packages/eng-harness/tests/unit/adapters/test_args.py"  # adapters/_args.py
      - "packages/eng-harness/tests/unit/servers/test_buildcheck.py"  # servers/_buildcheck.py
      - "packages/eng-harness/tests/unit/servers/test_hostlock.py"  # servers/_hostlock.py
      - "packages/eng-harness/tests/workflow/servers/test_guard.py"  # servers/_guard.py
    max_changed_lines: 80
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/contract/test_mutation_scope.py::test_spec_0002_section_9_modules_in_r1"
    covers: []  # section 9 mutation scope is not an AC; this plan's covers style lists ACs only
    depends_on: [T6b, T7, T8, T9, T14]  # T6b _buildcheck; T7 _hostlock and _guard; T8 _args; T9 _errors and csi/_errors; T14 _reconcile
---

# Implementation plan: eng-harness servers and adapters

## 1. Approach

Bottom-up, in the order the code imports itself, with the risky parts early: configuration (T1); processes and Job
Objects (T2, T3), because a wrong breakaway choice either kills an engineer's ETABS or orphans instances; the
synthetic fake (T4), which every later workflow test runs as a real process; the MCP session (T5); the build check
and allowlist (T6, T6b), the first safety gate of a run; the host-instance lock and guard (T7); the adapter framework (T8,
T8b, T9); then the CSI adapter in the order of the cycle: identity and session operations (T10), reply mapping and model state (T11, T11b), edits
(T12) and read-back (T12b), analysis and design (T13), reconciliation (T14); the blocked ADR-0031 switch (T15); the
command-line tools (T16); record mode (T17); the doctor (T18); the remaining `HostPort` methods of the CSI host port
(T19c, amendment B-530); the step 2 open of the original and the visible launch (T23, amendment B-543); and an
end-to-end task (T19a) that wires the CSI ports
into the engine and runs the crash matrix, together with the two engine stops that the early tasks leave out (a failed
build check, the units trap; B-413), and T19b, which adds the command-line tools to that wiring (amendment B-475: T19
split so that the first live run, the edit cycle on ETABS, waits for neither the command-line adapter nor record mode).
T20 (B-085) adds the framework items that the IDEA adapter (spec 0014, item A1) needs and that no CSI task uses.
T21 (B-503) moves the CSI kind models to a kinds module and registers them, before T19a and edit-cycle plan 0007 T4.
T22 (B-541) gives the doctor and `build_ports` one platform launcher and inspector, defines `AdapterPorts` with the
`ServerManager`'s lifetime, converts parsed server sections and names a server's host program, before T19a and plan
0006 T16. T23 (B-543) is the step 2 open of the original and the visible launch (the entry above).

Every task is test-first: its first commit is `test:` with the tests in `tests_first`, failing on `build/v1`
([process/05](../../../../design/process/05-testing-and-verification.md) §9). Each task adds a `CHANGELOG.md` line and
any public module to `[tool.eng-gate] public_modules`. Workflow tests start the synthetic fakes through the harness's
own launcher (POSIX in Linux CI); `tests/windows/` runs in the Windows CI job. Each adapter task extends the synthetic
CSI fake (`tests/fakes/sasaah_csi/`, test code) with the behaviour of the tools it adds (spec §4.8.3); the tasks that
share it (T6b, T10, T11, T11b, T12, T12b, T13, T14, T19a; plan 0012 T3 may only record product on csi_launch and confirm on csi_open_model, B-586) are serialized by `depends_on` (B-413). Tasks that share a source file are
serialized by `depends_on`: `_session.py` (T5, T6b, T7, T20; plan 0014 T3 after them, B-584), `doctor.py` and `test_doctor.py` (T18, T22; B-541), `_toolport.py` (T8b, T9, T12, T14, T16, T19a; T16 and
T19a are not ordered, so whichever lands second adapts to the other in its own task, B-503; plan 0007 T13b adds a
no-op hook and is not ordered with T16 either, B-569), `_hostport.py` (T10, T11b,
T12b, plan 0007 T13, T19c, T23, T19a, then plan 0007 T13b; plan 0008 T3 and T5 after them, B-581; plan 0012 T4 after them for absences-aware state-reader selection and fingerprint on save only, B-590; B-503, B-530, B-543, B-569), `_identity.py` and `test_csi_session_ops.py` (T10, T19c;
B-530), `csi/_session_ops.py` (T10, T23; B-543),
`csi/_reconcile.py` (T14, T19a; plan 0008 T6 after them; plan 0012 T4 for absences-aware state-reader selection from the profile only, B-590), `adapters/__init__.py` (T22, T19a, T19b; B-541; plan 0007 T13b wires one callback and is not ordered with T19b, so
whichever lands second adapts, B-569) and
`test_build_ports.py` (T19a, T19b; B-475; plan 0008 T1 also edits `build_ports` after T19a: whichever of T19b and 0008 T1 lands second
adapts to the other in its own task), `csi/_tools.py` (T12, T12b, T13, T15, T23; plan 0007 T5 and T13, B-503: T15 and
those two are not ordered, and T15 and T23 are not ordered, B-543, so whichever lands second adapts; plan 0007 T13b
after T13 and T23, not ordered with T15, B-569; plan 0008 T6 and T7 after them, B-588: T7 may only merge the SAFE
result-reader tokens, argument models and readers; plan 0012 T5 and T6 after them, B-594: T5 may only merge the
SAP2000 add-frame builders and tokens, the section check and the reply-name retarget, T6 may only merge the SAP2000
analysis, result-reader and design BUILDERS, TOKENS and READERS, serialize T5 then T6 or either order with the
integrator merging),
`_allowlist.toml` (T12, T13, T15), `_state.py` and `test_csi_state.py` (T11b, T12), `products/_etabs.py` (T11, T12,
T12b, T13), `products/__init__.py` (T11, T12b; plan 0012 T3 for the gap and step-gap registry fields only, B-586; plan 0012 T4 for ProductProfile.declared_absences only, B-590; plan 0012 T5 for ProductProfile.add_frame_naming only, B-594), `_replies.py` (T11, T13, T21) and
`test_csi_replies.py` (T11, T13), `test_toolport.py` (T8b, T12), `servers/__init__.py` (T1, T5, T22; T17 is not ordered with T22, so whichever lands second adapts, B-541), `servers/_config.py` and `test_config.py` (T1, T6, T20, T22; B-541),
`_allowlist.py` (T6, T6b, T20) and `test_allowlist.py` (T6, T20) (B-465). `_kinds.py` is shared by T21 and every
later task of another plan that adds kinds to `HARNESS_KINDS` (plan 0008 T4, T5, T7 and T9, plan 0011 T6, plan 0013 T2; B-503, B-589): none
waits for T21 or T21 for it, and whichever lands second adds its registry to the line the other wrote. Plan 0011 T6 may only
register `REVIT_KINDS` there (amendment B-589; the same `_kinds.py` listing as plan 0008 T4 for SAFE). Parallel tasks
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
`ServerCheck`; the workflow fixture's build pins become the real ones (the SHA-256 of `sys.executable` and the
allowlist's `sasaah_commit`) and the fake's `csi_status` reports `script_enabled: false`, so the build check passes when
`preflight` runs over the CSI fake and when a role of it restarts. Where the check runs (spec §4.3.4, B-413): the engine
calls `ServerManager.preflight` at run start and resume; `_session.py` runs the check itself only on a restart
(§4.3.5), never on a role's first start. The check reaches the `ServerManager` as a constructor argument beside the
launcher (`build_ports`, wired in T19a, builds it from the adapter allowlist, so `servers` needs no import of
`adapters`); a `ServerManager`
built without one answers `preflight` with `ok` false and runs no check on a restart. The fixture `make_config` names
the CSI allowlist's adapter `sasaah-csi-mcp`, with `--disable-script` in its args (spec §4.2 rule 3; the fake reads no
command-line options), only when its script is the CSI fake, through a fixture parameter that follows the script; the
configs of the PAGED transport double in `test_session.py` keep the adapter `synthetic-csi` and no `--disable-script`,
so the argv assertions of `test_launch_arguments` and `test_launch_arguments_without_audit_log` stay as they are. The
existing T5 tests build `ServerManager` without a check, so the restart in
`test_server_exiting_before_handshake_is_not_connected` runs none and no T5 expectation changes (A4); not through a
mapping of `synthetic-csi` in `_session.py` (B-413). `test_session.py::test_restart_repeats_build_check` (AC11's
build-check clause, B-413) builds a `ServerManager` with a check over the CSI fake, kills the server during a call and
shows that the restart runs the check again before the re-attach (§4.3.5); it fails
at T6b's base because `servers/_buildcheck.py` and the `ServerManager` check argument do not exist there. The workflow
test that stops a run through the engine's preflight is T19a's (B-413).
Budget 180 lines. T6b edits `_session.py`,
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

**T11 Model kinds** (§4.6.4). The mapping of the CSI replies to the six model kinds and the status, with the product
tables, tested on the fake's replies. **T11b Model state** (§4.6.4). The read set, the fingerprint, `LIMIT_EXCEEDED` on
truncation, outside-edit detection, `read_units`. Amendment B-450 (D-12): T11 split in two (581 counted lines measured);
`tests/property/test_fingerprint.py` is shared with calcs plan 0003 T7, so T11b merges after it. A dependency on
servers T11 named in another plan means T11 and T11b.
The units-trap workflow test, in which the engine stops, is T19a's (B-413).

**T12 Edits** (§4.6.1, §4.6.2, §4.5.4). Argument models and builders per edit kind, the `NotImplementedGap` entries
H-G1 to H-G3 and the seismic exclusion, and the CSI tool port over them. §4.5.4 chooses the units token per call, so
`ModelBinder.binding` (`_toolport.py`) is given the tool's descriptor, and the CSI binder in `_tools.py` (the only
`ModelBinder` in the source) puts that tool's token of §4.6.3 from `TOKENS`, which stays in `_tools.py`, on the
binding (`kN_mm_C` for the wall thickness, `kN_m_C` for the loads). The B-131 context variable set by
`CsiToolPort.call` is removed. The reader's fingerprint gains the table `Wall Property Definitions -
Specified` (§4.6.4, its key in `products/_etabs.py`), so a wall-thickness edit changes it (AC27; B-451 L2). Whether
the combination factors (`scale_ratio`, an engineering quantity in §4.6.2 and §5) may stay literals inside the
contract's `CombinationItem`, as B-131 wrote them, is an owner question (B-465). Amendment
B-465 (D-12): T12 split in two (about 621 counted lines measured); a dependency on servers T12 named in another plan
means T12 and T12b.

**T12b Read-back and check_model** (§4.5.8, the read-back column of §4.6.2; work item B-466). Read-back helpers and
`check_model` with `READBACK_MISMATCH`, `READBACK_UNAVAILABLE` and the tolerance-free codes. The read-back table keys
and columns are product facts in `products/_etabs.py`, flagged OQ-G10, not constants in `_checks.py`. Quantities are
compared "within the design basis field `checks.readback_relative_tolerance_ratio` (required by every workflow that writes
quantities; never a constant here, §11 G-2)" (spec §4.5.8); by the owner answer of 2026-11-14 (amendment B-495,
spec §11 Q8) that value comes from the basis field, passed by the workflow, and arrives as `ReadBack.tolerance_ratio`
(`check_model(model_key)` takes no basis); when none is passed a quantity read back is `READBACK_UNAVAILABLE`, as
merged. T19a delivers the value from the run's frozen basis (spec §4.5.8, AC44; H-G9 closed by amendment B-503). The write hook is in
`CsiToolPort` (`csi/_tools.py`): it wraps its edit
builders (`EDIT_BUILDERS`), whose builder sees the canonical model and the binding before the send, to call the
written-items book's `prepare`; `CsiToolPort.call` runs `commit` after a successful reply and then
`AdapterHostPort.wrote(model_key)`, so the write is not reported as `MODEL_CHANGED_OUTSIDE` (B-451 L4). T12b also drains `take_warnings()` (B-451 L4); which result reports the drained warnings is a lead
question (B-465), since design 04 §3.4 and spec §4.6.4 say only that the read adds `MODEL_CHANGED_OUTSIDE`.

**T13 Analysis and design** (§4.6.1 steps 11 to 13). Long-role routing, analysis status, design run and results, the
three force kinds, analysis messages. The T11 mappers in `_replies.py` raise `HOST_ERROR` (`UNEXPECTED_REPLY`) instead
of a bare `KeyError` or a pydantic `ValidationError` (B-451 L1, tested in `test_csi_replies.py`; amendment B-465).

**T14 Reconciliation** (§4.5.7). The per-tool rules with pre-images and evidence, `read_back`, `preview`;
analysis and design reconcile `unknown` while no proof of end exists (gap H-G7). The merged T14 built no `preview`
(`ToolPort.preview` arrived later, with engine plan T15) and set no pre-image on a write's binding; both are T19a's
(amendment B-503).

**T15 ADR-0031 switch.** Blocked until the owner accepts ADR-0031 and `eng-contract` releases `model_unlocked` and
`server_owned_instance`. Then: the new mappings, `csi_unlock_model` on the allowlist with action `unlock`, and the
interim test replaced, because the accepted ADR changes the specified behavior (a spec change, not a test changed to
pass). The engine's action-based always-ask list (engine spec 0001 §4.7: action `delete`, saves over an original)
gains the action `unlock` in the engine plan, not here; the edit-cycle workflow's existing tool-name entry
`always_ask=("csi_unlock_model",)` matches it and stays.

**T16 Command-line tools** (§4.7). Tool jobs, attempt folders, hashed inputs and outputs, the configuration rewrite,
build-artifact pins, exit-code mapping, reconciliation by completion record; a Python stand-in for the scripts.

**T17 Record mode** (§4.8.1, §4.8.2). The recording transport wrapper, the sanitizer, the manifest, the recorded-reply
fake, the contract and fidelity tests (run on every applicable committed recording under `acceptance/recordings` and
on the synthetic recording produced by record mode for that adapter; verified against the real server only once the
owner commits recordings, spec §12 item 13; amendment B-573), the owner's record script and its README.

**T18 Doctor** (§4.9). The checks behind interfaces (installed programs, integrity level, location probe), table and
JSON output, exit codes; the unreleased-tools check and the `extra_checks` extension point for spec 0006 (AC39, B-068).

**T19c Host port leases, run-state reload and the saved fingerprint** (amendment B-530, split from T19a after the
pre-flight audit; spec §4.4.1, §4.5.9). `AdapterHostPort` (`_hostport.py`) gains the `HostPort` methods it lacks:
`preflight` and `session_epoch` delegate to its `ServerManager`; `acquire(host_key)` answers a `HostLease` and re-locks,
through `HostLocks.acquire`, every instance of the run state that is still alive with the same pid and start time;
`release` calls `HostLocks.release_all`. At construction it loads `run_dir/adapter/state.json` when present, as a cache
(the journal wins, §4.5.9): the bindings (model key to instance id, model id and file; the constructor's `files` win for
a key both name), expected units and instance rows; the persisted rows gain `started_at`, `observed_at` and `exe_name`,
so a resumed port can rebuild each `OpenedInstance` (`_host` reads `observed_at`), re-lock and close them, and a
reloaded instance takes the session value `-1` of the spec §4.5.9 decision, so `_reusable` and `restore` never treat it
as launch-owned and launch anew. `save` returns in `SavedModel.fingerprint` the fingerprint of the saved state instead
of `""` (`_identity.py` `record_save`), so the engine's resume check does not report `model_differs` after a save (B-451
L3; from the T12 split, amendment B-465). Tests: `test_csi_session_ops.py::test_save_records_the_state_fingerprint` (a
new test, because the existing assertion compares `""` with `""` at the base: after `save`, `fingerprint` is not `""`,
equals the `CsiStateReader` fingerprint of the saved model and the state store's),
`test_csi_host_resume.py::test_lease_preflight_and_epoch` and `::test_new_port_restores_from_run_state` (a new
`AdapterHostPort` over the same `run_dir` restores `m@copy`).

**T19a End to end on ETABS** (split from T19 by amendment B-475). `build_ports` wiring for the CSI adapter; a test
block that runs the cycle's steps through the real engine and real
fake-server processes; the crash matrix that kills the engine at each write step and resumes (the host port's lease
and run-state reload are T19c's, amendment B-530). Completes
`docs/local-testing.md`. `build_ports` loads each allowlist for its server section's `route` (T20); the route-bearing
case is tested in `test_build_ports.py` with a synthetic routed allowlist (test data, product-neutral), since the CSI
cycle has no route (AC41). The two engine stops moved out of T6b and T11 (B-413):
`test_session.py::test_build_mismatch_stops_run`, a mismatched build stops the run before any write (AC9's engine
clause, engine AC44); `test_units_after_timeout.py::test_units_trap`, the synthetic fault `units_left_changed` makes the
engine stop with `PRECONDITION_FAILED` (`units_verified`) before reconciliation (AC22, engine AC45). Both need
`build_ports`, which this task adds to `src/eng_harness/adapters/__init__.py`, so they fail at its base. They read the
pinned fingerprint and the units through the allowlist loader and the ports. Until T19b, `build_ports` builds no
command-line tool: given a configuration with any `[cli_tools.*]` entry it raises `NotImplementedGap`
(`NOT_IMPLEMENTED`, gap H-G8) naming the entries, rather than drop them, so `ToolPort.unreleased_tools()` never lists
a tool that no port can reach (AC43; `test_build_ports.py::test_cli_tools_not_wired_gap`). The command line meets the
refusal at step 2 of spec 0006 §4.2.2 (amendment B-536), outside the engine, and ends with exit 2 `USAGE` (spec AC43, §11 Q9; owner
answer of 2026-11-14, amendment B-495), the message naming H-G8 and the entries: `cli/_exit.py` maps the code
`NOT_IMPLEMENTED` to 2 (spec 0006 §6; plan 0006 T14c catches the exception and returns the usage exit itself, spec 0006 AC68, amendment B-536), pinned by the case `("NOT_IMPLEMENTED", 2)` added to the error-code table test
`tests/unit/cli/test_exit_codes.py::test_error_codes` (70 at the base). A `harness.toml` for a run
before T19b therefore holds no `[cli_tools.*]` section. T19a does not wait for plan 0008.

Keyword seams of `build_ports` (amendment B-530; spec §4.1): `inspector`, `launcher`, `lock_dir`, `files`, `checks`,
`allowlists` and `visible` (amendment B-543, given to the host port; `build_ports` also passes `host.open_original` as
the tool port's `opener`, T23), with the defaults and rules of spec §4.1 (in production the command line fills `files`, plan 0006 T14c,
amendment B-536); the workflow and replay tests pass `files`, a test inspector and
launcher over the CSI fake, and `test_allowlist_loaded_for_route` passes, through `allowlists`, a loader of its
synthetic routed allowlist (a `load_allowlist` call with the route it is given). `allowlists` maps an adapter name to a
loader taking the section's `route`, because `load_allowlist` refuses a routed allowlist without a route and
`_for_route` is private; its default is `csi_allowlist`, which gains a `route` argument (`csi/__init__.py`). For CSI the
result only validates the section's route, since `CsiToolPort` builds its own `tool_allowlist()`. Amendment B-541
(spec §4.1): `config` is a `ServersConfig`; the result is T22's `AdapterPorts(tool_port, host_port, servers)`; the
`inspector` and `launcher` defaults are T22's `platform_inspector()` and `platform_launcher(inspector)`; the host
port's `program` (the host-lock key) is the entry name `product.lower()`, and its `exe_name` and the guard's
`host_exes` come from `config.host_program(product)` (T22), whose
`ConfigError` the command line ends with exit 2 (spec 0006 AC71); and every workflow and replay test of T19a that
runs the engine over the built ports enters them around `Engine.start` and `Engine.resume` (test code; spec AC48),
as does every later task whose tests run the real engine over `build_ports` (section 3).
Production binder
(amendment B-530): `AdapterHostPort` gains `binding(host_key, model, descriptor)` and `revision(model_id)`
(`_hostport.py`), and `build_ports` passes the host port as `binder` (`CsiToolPort` wraps it in `_TokenBinder`).
`binding` raises `PRECONDITION_FAILED` (`model_open`) when no instance is bound; target from the bound instance; `owned`
from `CsiSession.owns`; `units_system` from the expected units of the open (the tool's `TOKENS` value overrides it in
`_TokenBinder`); `host` from the identity record (model id, revision) and the program version of the spec §4.5.9
decision. `revision(model_id)` answers the revision in the `states` store, `None` when unknown or when no store is
wired. `test_build_ports.py::test_binder_from_host_port` checks each source and the refusal.

Wiring list of the CSI ports (amendment B-503; spec AC44, AC45). `build_ports` builds one `WrittenItems` book and
hands it to both ports: to `AdapterHostPort` inside its `ReadBack` (with the run's store and the server's
`ServerCheck`) and to `CsiToolPort` as `written`, with `wrote=host.wrote`, the CSI `Reconciler` of
`csi/_reconcile.py`, `revisions=Revisions(run_dir / "copies", run_dir / "adapter" / "revisions.json")` (plan 0007
T5) and `reopened=host.reopened` (plan 0007 T13). The run's `KindRegistry` holds `CSI_KINDS` through
`HARNESS_KINDS` (T21), so an analysis or design result is stored. Read-back tolerance (closes spec H-G9):
`AdapterHostPort` gains a keyword `tolerance`, a callable answering the ratio or `None`; `check_model` calls it until
it answers a value, keeps that value and uses it in place of `ReadBack.tolerance_ratio`. `build_ports` passes a
provider that opens `JournalReader(run_dir)`, takes the `basis_ref` of `run_started`, loads it with
`StoreBasisPort(store)` and answers the number at `checks.readback_relative_tolerance_ratio`; it answers `None` while
the journal or header is missing (`JournalIntegrityError`), the basis does not load (`BasisInvalid`) or the field is
absent or holds no number. `CsiReconciler` takes the same provider as a keyword `tolerance` beside its fixed
`tolerance_ratio` and asks it the same way (`csi/_reconcile.py`, amendment B-530). This changes no engine port and
needs nothing from the command line: `Engine.start` writes
the header before any step, and a resume keeps it (spec §4.5.8, spec 0006 §4.2.2).
`test_build_ports.py::test_readback_tolerance_from_run_basis` writes a quantity through the built ports in a run
whose basis holds the field and checks the comparison within it, then resumes the run in a new engine with new ports
and checks it again, and with a basis without the field checks `READBACK_UNAVAILABLE`. Pre-image (spec §4.5.7): the
`ModelBinder` sees no call arguments, so `AdapterToolPort._call` itself, when its new keyword `record_pre_image`
(default false; `build_ports` passes true, so hand-wired ports such as those of
`tests/workflow/adapters/test_reconcile.py` keep their binder's pre-image) is set, for a write tool for which
`self.supports_reconcile(tool)` holds (so not the saves and opens of `_UNRECONCILED`), takes `read_back(tool, args)`
before the ledger entry and sets the binding's `pre_image_ref` to `<result_id>#/value/observed` of that stored read;
none when the read-back answers `None` (analysis, design) or the tool is not reconciled, so the ledger entry carries it
only then (amendment B-530). `ToolPort.preview` (spec §4.5.9 row) validates the arguments, stores them as
`harness.run_output/1`, takes the pre-image as above when `record_pre_image` is set and otherwise uses the binding's own
`pre_image_ref`, and answers a `Preview` with one item (id the tool name, label the tool and its target, refs the two
stored results), no `diff_ref` and the call's model handle from the binding's `host` (model id and revision); no write
is sent. A binding without `host` carries no model identity, so `preview` raises `PRECONDITION_FAILED` with precondition
`model_open` before it stores anything (as `AdapterHostPort._held` does). `test_csi_wiring_shares_book_and_pre_image`
checks, through the built ports, that a written edit is in the book that `check_model` reads, that the next
`model_state` gives no `MODEL_CHANGED_OUTSIDE`, that the ledger entry's `pre_image_ref` resolves to the value read
before the write, and that `csi_save_model` with `as_new_revision` and `csi_open_revision` work on the run's copies
folder; `test_csi_preview_sends_no_write` checks the preview, that the fake server logged no write, and that a binding
without `host` is refused with nothing stored.

**Original-open capability (B-562, AC52).** Add `ToolInfo.opens_model_without_writing(args)` with a false default
and the CSI override in `CsiToolInfo` (spec §4.5.9). Record an explicit true on the live attempt's `StepStarted`
before sending the open. Use the recorded value in live, immediate `applied`, and replay handling. Skip only
the dirty mark for that step. Keep the write effect for approvals, leases, units, sibling conflicts, unknown
outcomes and retries. Keep journal version 1 and earlier canonical payloads (engine §§4.4.2 and 10).

During resume, compare actual writes and retain the existing recovery for pending, lost or reopened models.
Exclude the unloaded original from the content check only with the completed, journaled EC1 handoff described
in engine §4.5.4. Use the content-writing view for expected provenance and revision-save candidates so a later
content-free open cannot hide evidence of an earlier edit or save. The recorded host and action support any
missing post-open binding and units checks before a still-live EC1 copy, and a recorded copy is replayed without
rebinding the original. Finish the same lifecycle when an open is resolved `applied` during its live call
(engine §4.7).

Add implementation regressions in `test_journal_events.py` (strict optional marker and unchanged legacy payloads),
`test_csi_revisions.py` (CSI descriptor opt-in and exclusions), `test_engine_edit_cycle_amendments.py` (binding,
units and EC1 after an immediately applied or replayed open, and preservation of earlier dirty state), and
`test_host_state.py` (complete and incomplete handoffs, lost or reopened pending opens, legacy starts, and actual
writes and revision checks on the original and copy). The existing cycle and crash matrix verify that the original
is handed off to the copy without a spurious original content check or a repeated applied write. Exercise the
existing engineer decision for unreconciled or unknown outcomes, and the existing host-state baseline choice for
an applied save without read-back evidence when required (AC36). Add these regressions in the implementation
commits. Keep the `tests_first` list and its existing first commit.

**Session budget (B-563).** The first implementation, the environment handoff and resume, and the isolated
stale CSI process identity fix used all three B-138 writer sessions before the owner paused the build. One
additional writer session may complete the work already scoped by B-562 after the owner resumes the build.

**T19b Command-line tools in the port wiring** (split from T19 by amendment B-475; spec §4.7, AC43). `build_ports`
routes each `[cli_tools.*]` entry to the command-line tool adapter of T16, so `ToolPort.describe` and `ToolPort.call`
of such a tool reach it (`test_build_ports.py::test_cli_tool_routed_through_build_ports`); it replaces T19a's H-G8
refusal and its gap test, because the specified behavior changes (spec AC43; a spec change, not a test changed to
pass). The SAFE engine stop of spec 0008 AC4 (`test_session.py::test_safe_build_mismatch_stops_run`), which T19 held
(B-413), is plan 0008 T3's, not T19b's: once T19a has merged `build_ports`, the stop fails at 0008 T3's base for want
of the SAFE entries and the pinned SAFE fingerprint that 0008 T3 adds. Its expected error, which that tests-first test
asserts: the run stops before any write with `RunRefused` whose code is the existing harness code
`SERVER_CHECK_FAILED` (engine AC44, `eng_harness.errors`; no new code), with the SAFE server section as its evidence,
and that server's `ServerCheck` has `ok` false with the reason "tool-list fingerprint differs from the allowlist's"
(the merged `check_build`, spec §4.3.4 item 4).

**T22 Platform launcher, ports lifetime, server sections, host program** (amendment B-541; spec §4.1, §4.2 rule 6,
§4.3.5, §4.9; AC48 to AC50). (1) `servers/_platform.py`: `platform_inspector()` answers `PosixProcessInspector()` on
POSIX and, on Windows, `WindowsProcessInspector(CtypesKernel32(PROCESS_SIGNATURES))` (doctor's private `_inspector`
moves here); `platform_launcher(inspector: ProcessInspector)` answers `PosixLauncher(inspector)` on POSIX, after
narrowing the type with `isinstance(inspector, PosixProcessInspector)` (any other inspector raises `TypeError`,
because `PosixLauncher` takes only the POSIX inspector and mypy strict needs the narrowing), and, on Windows, the Job
Object launcher over a `CtypesKernel32` with the process and job signatures and that inspector (what
`windows_launcher()` builds, with the given inspector); both are exported from `eng_harness.servers`; the Windows
branches are imported through `importlib` as the doctor does today, so mypy checks both platforms.
`test_platform.py::test_platform_pair` checks the POSIX pair (the launcher holds the given inspector); the Windows pair
is checked by `tests/windows/test_platform_windows.py` in the Windows job and in the owner's local test (spec §12 item
12). (2) `doctor.py`: `default_deps` takes its inspector from `platform_inspector()`, and `LiveRoles` builds its
`ServerManager` with `launcher=platform_launcher(inspector)` over that inspector, passed to `_gather` as a parameter;
`LiveRoles.__init__(inspector: ProcessInspector | None = None)` keeps a default (`platform_inspector()`), so the merged
`doctor.LiveRoles()` call of `test_doctor.py` stays valid (`test_doctor.py::test_live_roles_use_platform_launcher`); `run` accepts `config_path=None` (no section is checked)
and a keyword `env` that replaces `deps.env` for the workspace and lock-directory rows
(`test_doctor.py::test_no_config_file_and_environment`). (3) `servers/_config.py`: `servers_config(data)` validates the
three sections of parsed tables (one mapping holding the `servers`, `cli_tools` and `host_programs` tables; plan
0006 T18b passes those three fields of the command line's `HarnessConfig`) with the error mapping of
`load_servers_config`, which now reads the file as
`utf-8-sig` and calls it; `ServersConfig.host_program(product)` answers `host_programs[product.lower()]` or raises
`ConfigError("host_programs.<name>", ...)` (`test_config.py::test_servers_config_from_tables`,
`::test_byte_order_mark_accepted`, `::test_host_program_of_product`). (4) `adapters/__init__.py`: the frozen dataclass
`AdapterPorts(tool_port, host_port, servers)` whose `__aenter__` enters `servers` and returns itself and whose
`__aexit__` leaves it with the same exception; `test_ports.py::test_ports_enter_and_leave_server_manager` checks, with
a `ServerManager` subclass that records both calls, that entering the ports enters the manager and that leaving them,
normally and by an exception, leaves it with that exception. Every test fails at the base, where these names do not exist or the doctor
passes no launcher. The local-testing entry: doctor on the owner's Windows machine fills the tool-list rows through
the Job Object launcher.

**T20 Framework additions for the IDEA adapter** (AC40 to AC42, spec §11 A3, B-085). `audit_log` on the server
section (default true) and the argv builder `servers/_launch_args.py`, wired into `_session.py`, so the CSI argv stays
as it is and a section with `audit_log = false` gets no `--audit-log`; the `route` key and the allowlist header
`routes` with the entries' `routes` and loading for one route; the header `[[unit]]` entries with `unit_status` on the
descriptors and `Allowlist.units`, where a `missing` entry may name an unserved tool. Product-neutral: no module names IDEA. The IDEA server section, its options and its allowlist are plan
0014 T1 and T3, which start after this task; the issue codes, host codes and harness kinds of A3 are implemented where
they are used (plan 0014 T5, T7, T8).

**T21 CSI kinds in a kinds module** (amendment B-503; spec AC46, §4.1; spec 0003 §4.3). The payload models of the
harness kinds of spec A1 that T11 and T13 put in `adapters/csi/_replies.py` move unchanged to
`src/eng_harness/kinds/csi.py`, which imports `pydantic` only: `CsiModelStatus`, `CsiAnalysisRun`, `CaseStatus`,
`CsiAnalysisStatus`, `CsiDesignRun`, `CsiRows` (with their private base) and `CSI_KINDS`. `_replies.py` imports them
from there and re-exports them under the same names, so `_state.py`, `_tools.py` and the merged tests keep their
imports; its mappers (which use `pathlib` and convert host replies) stay. `_kinds.py` extends `HARNESS_KINDS` with
`CSI_KINDS`, so the run's store keeps the analysis, design and result-message results (today it refuses them).
`tests/rules/test_calc_modules.py` admits `eng_harness.kinds.csi` (spec 0003 §4.3), and the three tests that
build `HARNESS_KINDS.extend(CSI_KINDS)` (`test_reconcile.py`, `test_csi_analysis.py` and plan 0007 T5's
`test_csi_read_state_tool.py`) use `HARNESS_KINDS`, since `extend` refuses a kind already registered
(`ContractDefinitionError`); T21 therefore lands after plan 0007 T5 (section 3). `tests/contract/test_csi_kinds.py::test_csi_kinds_registered` checks that
each of the six kinds in `HARNESS_KINDS` is the model of `eng_harness.kinds.csi` and is the model `_replies.py`
answers; it fails at the base, where `eng_harness.kinds.csi` does not exist. No calc imports the module yet, so no
calc hash changes here; once plan 0007 T4's calcs import it, it enters their `modules` (spec 0003 §4.5).

**T23 Opening the original, visible launch** (amendment B-543; spec §4.5.9 "Opening the original", AC51; spec 0007
§4.5 step 2). `AdapterHostPort.open_original(model_key)` does what `restore` does without the hash check: the file of
the key, `CsiSession.open_file` on the reusable owned instance (or a launch), `_keep`, the units read and `_persist`.
`AdapterHostPort` and `CsiSession` take `visible: bool = False`; `_launch` sends it to `csi_launch`, to
`record_launch` and to the `OpenedInstance`. `CsiToolPort` takes `opener` (like `reopened`); in `call`, the
`csi_open_model` branch moves inside the `try`: with a `path` it answers `INVALID_ARGUMENT` as today, without one it
validates the arguments (`OpenModelArgs.path` becomes optional), calls `opener(key)` (`INTERNAL` when the port has
none), takes the binding of the key and answers a success envelope of kind `harness.run_output/1` with the key and the
file's base name; it writes no ledger entry (the open is not reconciled, `_UNRECONCILED`). `csi_open_revision` keeps
sending its `path` through `super().call`. `test_open_original_then_working_copy` runs, against the CSI fake server
process, the open through a tool port whose opener is the host port's `open_original` and whose binder is a test
binder (as `tests/workflow/adapters/test_csi_reopened.py` builds one; the production binder `AdapterHostPort.binding`
is T19a's, B-530, which comes after T23), then `locate`, `read_units` and `working_copy` (one
launch, the copy in the same instance); `test_open_refusals_are_envelopes` checks the three refusals of AC51 return
failure envelopes; `test_visible_launch` checks the fake's recorded `visible` flag, the run state's and the default.

## 3. Dependencies

- Runtime: `mcp` 2.x (package ADR in T1, owner queue); `eng-contract`, `pydantic` as in the engine plan. No other.
- Development: the root workspace group; no new development dependency.
- Work items: the engine plan's ([0001-engine](0001-engine.md)) T1 (package skeleton) before this plan's T1; its T6
  (ports, port data types and fakes) before T8; its run loop, invariants and replay tasks before the workflow and
  replay tests that run the real engine: T19a waits for engine 0001 T13, T15, T16, T16b and T19 (T13 brings in T9 to
  T12; B-413; T16b is the promotion half of the former T16, B-499). No earlier task of this plan runs the real engine. T19a waits for no task of plan
  [0008-safe-adapter](0008-safe-adapter.md): the SAFE engine stop of spec 0008 AC4 is 0008 T3's, after T19a (B-475).
  T19a also waits for T19c (amendment B-530), T21, T22 (amendment B-541) and T23 (amendment B-543: T23 edits `_hostport.py` and
  `csi/_tools.py` first, and T19a wires its opener and `visible`), and for edit-cycle plan [0007](0007-model-edit-cycle.md) T5
  (`Revisions`, the revision
  tools) and T13 (the `reopened` hook), whose wiring it adds (amendment B-503); neither of those waits for T19a.
  Plan 0007 T4 waits for T21 (its calcs import `eng_harness.kinds.csi`). T21 waits for plan 0007 T5, whose
  `test_csi_read_state_tool.py` it adapts to `HARNESS_KINDS` holding `CSI_KINDS`. T19b waits for T16 and T19a. T19a and
  plan [0006](0006-cli-progress-pages-report.md) T16 (the doctor's new arguments) wait for T22 (amendment B-541). T22 and T23 share only `CHANGELOG.md` and are not ordered.
  Every later task whose tests run the real engine over `build_ports` (T19b, plan 0008 T1 and T3, plan 0012 T1) enters
  the returned `AdapterPorts` around `Engine.start` and `Engine.resume` in its tests, as T19a does (spec AC48). `eng-contract`
  0.1.0 merged. T15 waits for ADR-0031 and an `eng-contract` minor release.
- External amendment (B-581, from plan 0008 T3 / the B-212 writer): plan 0008 T3 amends
  `packages/eng-harness/src/eng_harness/adapters/_hostport.py` so `AdapterHostPort._record_save` skips the table read
  when `profile.tables` is empty (SAFE before plan 0008 T5), keeping the prior fingerprint; required for SAFE AC6
  (`working_copy` on `.FDB`) and AC7 (session-operation suite with `product = SAFE`). Recorded in this plan's
  `_hostport.py` serialization above.
- External amendment (B-584, from plan 0014 T3 / the B-302 writer): plan 0014 T3 amends
  `packages/eng-harness/src/eng_harness/servers/_session.py` so `ServerManager._verify` calls `expected.status_tool`
  (`BuildExpectation.status_tool`, default `csi_status`; IDEA `idea_status`) instead of the hardcoded `csi_status`, and
  names that tool in the error message; required for IDEA AC3 workflow stops (`test_idea_script_enabled_stops_run`,
  `test_idea_listed_run_script_stops_run`). Recorded in this plan's `_session.py` serialization above.
- External amendment (B-586, from plan 0012 T3 / the B-247 writer): plan 0012 T3 amends
  `packages/eng-harness/src/eng_harness/adapters/csi/products/__init__.py` so `ProductProfile` carries the gap and
  step-gap registries (`profile(product).step_gaps`), and may amend `tests/fakes/sasaah_csi/server.py` only to record
  `product` on `csi_launch` and `confirm` on `csi_open_model` (test only); required for spec 0008 AC2
  (`test_no_product_branches_in_shared`) and optional launch/open call-log asserts. Recorded in this plan's
  `products/__init__.py` and fake serialization above. Plan 0008 records the matching external amendment for
  `products/_safe.py` and `products/__init__.py`.
- External amendment (B-588, from plan 0008 T7 / the B-216 writer): plan 0008 T7 amends
  `packages/eng-harness/src/eng_harness/adapters/csi/_tools.py` so it may only merge the SAFE result-reader tokens,
  argument models and readers from `products/_safe_results.py` into the shared registries (`TOKENS`, `ANALYSIS_MODELS`,
  `READERS`; the T6 pattern for `_safe_loads`); required for SAFE AC23 (base and joint reactions through the CSI tool
  port / `tool_allowlist()`). Recorded in this plan's `csi/_tools.py` serialization above.
- External amendment (B-589, from plan 0011 T6 / the B-235 writer): plan 0011 T6 amends
  `packages/eng-harness/src/eng_harness/_kinds.py` so it may only register `REVIT_KINDS` on `HARNESS_KINDS`, and adds
  the kinds contract fixtures under `packages/eng-harness/tests/data/kinds/revit/**`; required for Revit AC33 (kinds
  usable through the registry; the same `_kinds.py` listing as plan 0008 T4 for SAFE / B-216). Recorded in this plan's
  `_kinds.py` serialization above.
- External amendment (B-590, from plan 0012 T4 / the B-248 writer): plan 0012 T4 amends
  `packages/eng-harness/src/eng_harness/adapters/_hostport.py` so it selects the absences-aware state reader when
  `profile.declared_absences` is non-empty and records the fingerprint on save when absences or tables are set;
  amends `packages/eng-harness/src/eng_harness/adapters/csi/products/__init__.py` so `ProductProfile` carries
  `declared_absences` (wired from `_sap2000.DECLARED_ABSENCES`); and amends
  `packages/eng-harness/src/eng_harness/adapters/csi/_reconcile.py` for the same reader selection; no product-name
  branch (spec 0008 AC2). Recorded in this plan's `_hostport.py`, `products/__init__.py` and `csi/_reconcile.py`
  serialization above. Plan 0008 records the matching external amendment for `products/__init__.py` and
  `csi/_reconcile.py`.
- External amendment (B-594, from plan 0012 T5 and T6 / the B-249 and B-250 writers): plan 0012 T5 amends
  `packages/eng-harness/src/eng_harness/adapters/csi/_tools.py` so it may only merge the SAP2000 add-frame builders
  and tokens, the section check and the reply-name retarget into the shared registries (no product-name branch), and
  amends `packages/eng-harness/src/eng_harness/adapters/csi/products/__init__.py` so `ProductProfile` carries
  `add_frame_naming` (wired from `_sap2000`; spec 0008 AC2); plan 0012 T6 amends the same `_tools.py` so it may
  only merge the SAP2000 analysis, result-reader and design BUILDERS, TOKENS and READERS (the B-588 pattern);
  T5 and T6 both edit `_tools.py` (serialize T5 then T6, or either order with the integrator merging); required for
  SAP2000 AC11–AC13 and AC14–AC16 through the CSI tool port. Recorded in this plan's `csi/_tools.py` and
  `products/__init__.py` serialization above. Plan 0008 records the matching external amendment for `_tools.py` and
  `products/__init__.py`.
- First live run (amendment B-475, lead decision D-32: the edit cycle of spec 0007 on a copy of a real ETABS model
  comes first). T16, T17 and T19b are off its path, and so are plan 0008 T1 to T3; none is deleted or weakened. Each
  returns before the first task that depends on it: T16, then T19b, with the first workflow that names a command-line
  tool (the DXF start, which spec 0007 §7 leaves out; no task of plans 0007 and 0010 depends on them); T17 before plan
  0008 T8, plan 0011 T13 and plan 0012 T1, which depend on it (record mode is not available at the first live run);
  plan 0008 T1 to T3 before plan 0008 T4, which the footing workflow (plan 0010 T10 and T11, through 0008 T5 to T7) and
  plan 0012 T1 need.

## 4. Verification

- Local gate per task (`uv run eng-gate check` once available; until then ruff, mypy strict and pytest with coverage
  from `packages/eng-harness/`); the pull request links its CI run.
- Windows CI job: `tests/windows/` (jobs, breakaway, inspector, doctor integrity level in `test_doctor_windows.py`).
- Needs local test (spec §12, listed in `docs/local-testing.md`): everything that drives `sasaah-csi-mcp`, ETABS or
  the PowerShell tools, including the breakaway of a server-launched ETABS, the long-role attach, the live
  fingerprint, the table keys, timeouts and reconciliation with S-02, fingerprint stability with S-04, the doctor and
  record mode on the owner's machine.
- Review: correctness, Python, type-design, silent-failure and test lenses on every task; the security lens on T1
  (configuration), T3 (process creation, handle inheritance), T7 (locks, terminating processes), T16 (running scripts
  with arguments) and T17 (sanitizing recordings); R1 review against the spec's reconciliation and units rules on T9,
  T11, T11b, T12, T12b, T14. Second-family review and owner approvals are `awaiting owner` (ADR-0028 §4).

## 5. Rollback

Each task is one squash-merged pull request into `build/v1`; reverting it removes it and its dependants. Nothing here
writes to a host program in CI. The allowlist and its fingerprint are data: a wrong pin is fixed forward by a new
header, and a run against an untested build is refused by the build check rather than run.
