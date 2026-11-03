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
    title: Process transport, MCP client session, crash detection, restart and shutdown
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/servers/__init__.py"
      - "packages/eng-harness/src/eng_harness/servers/_transport.py"
      - "packages/eng-harness/src/eng_harness/servers/_session.py"
      - "packages/eng-harness/tests/workflow/servers/__init__.py"
      - "packages/eng-harness/tests/workflow/servers/test_session.py"
      - "packages/eng-harness/tests/workflow/conftest.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/servers/test_session.py::test_start_list_call"
      - "packages/eng-harness/tests/workflow/servers/test_session.py::test_crash_restart"
      - "packages/eng-harness/tests/workflow/servers/test_session.py::test_shutdown_leaves_hosts"
    covers: [AC8, AC11, AC12]
    depends_on: [T2, T4]
  - id: T6
    title: Tool descriptors, allowlist data with escape-hatch refusal, build check and fingerprint
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/pyproject.toml"
      - "packages/eng-harness/src/eng_harness/servers/_buildcheck.py"
      - "packages/eng-harness/src/eng_harness/servers/_session.py"
      - "packages/eng-harness/src/eng_harness/adapters/__init__.py"
      - "packages/eng-harness/src/eng_harness/adapters/_descriptors.py"
      - "packages/eng-harness/src/eng_harness/adapters/_allowlist.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/__init__.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_allowlist.toml"
      - "packages/eng-harness/tests/unit/servers/test_buildcheck.py"
      - "packages/eng-harness/tests/unit/adapters/__init__.py"
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py"
      - "packages/eng-harness/tests/contract/test_csi_allowlist.py"
      - "packages/eng-harness/tests/workflow/servers/test_session.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/servers/test_buildcheck.py::test_fingerprint_definition"
      - "packages/eng-harness/tests/unit/servers/test_buildcheck.py::test_each_mismatch"
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py::test_entries_complete"
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py::test_escape_hatches_refused"
      - "packages/eng-harness/tests/contract/test_csi_allowlist.py::test_pinned_fingerprint_from_inventory"
      - "packages/eng-harness/tests/contract/test_csi_allowlist.py::test_against_inventory"
      - "packages/eng-harness/tests/workflow/servers/test_session.py::test_build_mismatch_stops_run"
    covers: [AC9, AC10, AC16]
    depends_on: [T5]
  - id: T7
    title: Machine-level host-instance lock and process guard
    files:
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
    covers: [AC13, AC14, AC15]
    depends_on: [T6]
  - id: T8
    title: Adapter framework - arguments and references, envelopes, write ledger, ToolPort describe and call
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/__init__.py"
      - "packages/eng-harness/src/eng_harness/adapters/_args.py"
      - "packages/eng-harness/src/eng_harness/adapters/_envelope.py"
      - "packages/eng-harness/src/eng_harness/adapters/_ledger.py"
      - "packages/eng-harness/src/eng_harness/adapters/_toolport.py"
      - "packages/eng-harness/src/eng_harness/_kinds.py"
      - "packages/eng-harness/tests/unit/adapters/test_toolport.py"
      - "packages/eng-harness/tests/unit/adapters/test_args.py"
      - "packages/eng-harness/tests/unit/adapters/test_envelope.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/adapters/test_toolport.py::test_not_allowlisted"
      - "packages/eng-harness/tests/unit/adapters/test_args.py::test_refs_resolved_converted_recorded"
      - "packages/eng-harness/tests/unit/adapters/test_envelope.py::test_limits_and_provenance"
    covers: [AC17, AC18, AC19]
    depends_on: [T6]
  - id: T9
    title: Error and timeout mapping, the CSI error table (interim model_locked)
    files:
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
    depends_on: [T8]
  - id: T10
    title: Harness-side model identity (ADR-0032), CSI session operations, HostPort file and instance methods
    files:
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
    covers: [AC30]
    depends_on: [T7, T9]
  - id: T11
    title: CSI model-state reader, model kinds, fingerprint and units read
    files:
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
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_reconcile.py"
      - "packages/eng-harness/src/eng_harness/adapters/_toolport.py"
      - "packages/eng-harness/src/eng_harness/adapters/_ledger.py"
      - "packages/eng-harness/tests/workflow/adapters/test_reconcile.py"
    max_changed_lines: 350
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/adapters/test_reconcile.py::test_outcomes_per_tool"
    covers: [AC23]
    depends_on: [T13]
  - id: T15
    title: ADR-0031 switch - model_locked as model_unlocked precondition and the approved unlock step (blocked until accepted)
    files:
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
    covers: [AC31, AC32]
    depends_on: [T14]
  - id: T17
    title: Record mode, sanitizer and manifest, recorded-reply fake, contract tests on recordings
    files:
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
    covers: [AC37]
    depends_on: [T7]
  - id: T19
    title: Port wiring, edit-cycle step sequence and crash matrix against real fake-server processes
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/__init__.py"
      - "packages/eng-harness/docs/local-testing.md"
      - "packages/eng-harness/tests/workflow/test_csi_cycle.py"
      - "packages/eng-harness/tests/replay/test_csi_resume.py"
    max_changed_lines: 200
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/test_csi_cycle.py::test_cycle_steps"
      - "packages/eng-harness/tests/replay/test_csi_resume.py::test_crash_matrix"
    covers: [AC36]
    depends_on: [T17, T18]
---

# Implementation plan: eng-harness servers and adapters

## 1. Approach

Bottom-up, in the order the code imports itself, with the risky parts early: configuration (T1); processes and Job
Objects (T2, T3), because a wrong breakaway choice either kills an engineer's ETABS or orphans instances; the
synthetic fake (T4), which every later workflow test runs as a real process; the MCP session (T5); the build check
and allowlist (T6), the first safety gate of a run; the host-instance lock and guard (T7); the adapter framework (T8,
T9); then the CSI adapter in the order of the cycle: identity and session operations (T10), model state (T11), edits
and read-back (T12), analysis and design (T13), reconciliation (T14); the blocked ADR-0031 switch (T15); the
command-line tools (T16); record mode (T17); the doctor (T18); and an end-to-end task (T19) that wires the ports into
the engine and runs the crash matrix.

Every task is test-first: its first commit is `test:` with the tests in `tests_first`, failing on `build/v1`
([process/05](../../../../design/process/05-testing-and-verification.md) §9). Each task adds a `CHANGELOG.md` line and
any public module to `[tool.eng-gate] public_modules`. Workflow tests start the synthetic fakes through the harness's
own launcher (POSIX in Linux CI); `tests/windows/` runs in the Windows CI job. Tasks that share a source file are
serialized by `depends_on`: `_session.py` (T5, T6, T7), `_toolport.py` (T8, T9, T14, T16), `_hostport.py` (T10, T11,
T12), `csi/_tools.py` and `_allowlist.toml` (T12, T13, T15), `servers/__init__.py` (T1, T5, T17). Parallel tasks
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
in-memory model, Sasaah reply shapes, faults from a control file. Its contract test keeps the schemas equal to the
inventory; a packaging test proves `tests/` is not in the wheel.

**T5 Session** (§4.3.2, §4.3.3, §4.3.5). `ProcessTransport`, roles, `Client(mode, cache=None)`, per-call backstop
timeouts, crash detection, restart with re-attach, shutdown. Uses the synthetic fake.

**T6 Allowlist and build check** (§4.3.4, §4.5.1). Descriptors, the TOML allowlist with the deny list and pattern
refusal, the CSI allowlist header pinned to the S-12 commit and the fingerprint computed from the inventory, the build
check and `ServerCheck`; the workflow test stops a run through the engine's preflight.

**T7 Lock and guard** (§4.4). OS locks in the machine-level lock folder, holder records, stale handling; launched
instance identification by snapshot diff; `close_started` rules; helper tracking.

**T8 Framework** (§4.5.2, §4.5.3, §4.5.7 ledger). `validate_input` with `require_refs`, conversion by token,
explicit target, envelopes within the limits, provenance, the write ledger with `fsync`, `ToolPort.describe` and
`call`; harness kinds registered in `_kinds.py`.

**T9 Errors and timeouts** (§4.5.5, §4.5.6). The mapping table as data with Sasaah source lines, the timeout and
backstop rules, wedged state and epochs; `model_locked` interim mapping (`HOST_LOCKED`) per ADR-0031 decision 5.

**T10 Identity and session operations** (§4.5.9, ADR-0032). The identity store, launch and open of a working copy,
save with hash and identity update, restore, `locate`, `model_files`.

**T11 Model state** (§4.6.4). The read set, the six model kinds and the status, the fingerprint, `LIMIT_EXCEEDED` on
truncation, outside-edit detection, `read_units`; the units-trap workflow test with the synthetic fault.

**T12 Edits and read-back** (§4.6.1, §4.6.2, §4.5.8). Argument models and builders per edit kind, the
`NotImplementedGap` entries H-G1 to H-G3 and the seismic exclusion, read-back helpers, `check_model` with the basis
tolerance.

**T13 Analysis and design** (§4.6.1 steps 11 to 13). Long-role routing, analysis status, design run and results, the
three force kinds, analysis messages.

**T14 Reconciliation** (§4.5.7). The per-tool rules with pre-images and evidence, `read_back`, `preview`.

**T15 ADR-0031 switch.** Blocked until the owner accepts ADR-0031 and `eng-contract` releases `model_unlocked` and
`server_owned_instance`. Then: the new mappings, `csi_unlock_model` on the allowlist with action `unlock`, and the
interim test replaced, because the accepted ADR changes the specified behavior (a spec change, not a test changed to
pass). The engine's always-ask list gains `unlock` in the engine plan, not here.

**T16 Command-line tools** (§4.7). Tool jobs, attempt folders, hashed inputs and outputs, the configuration rewrite,
build-artifact pins, exit-code mapping, reconciliation by completion record; a Python stand-in for the scripts.

**T17 Record mode** (§4.8.1, §4.8.2). The recording transport wrapper, the sanitizer, the manifest, the recorded-reply
fake, the contract and fidelity tests (skipped with a reason until the owner commits recordings), the owner's record
script and its README.

**T18 Doctor** (§4.9). The checks behind interfaces (installed programs, integrity level, location probe), table and
JSON output, exit codes.

**T19 End to end.** `build_ports` wiring; a test block that runs the cycle's steps through the real engine and real
fake-server processes; the crash matrix that kills the engine at each write step and resumes. Completes
`docs/local-testing.md`.

## 3. Dependencies

- Runtime: `mcp` 2.x (package ADR in T1, owner queue); `eng-contract`, `pydantic` as in the engine plan. No other.
- Development: the root workspace group; no new development dependency.
- Work items: the engine plan's ([0001-engine](0001-engine.md)) T1 (package skeleton) before this plan's T1; its T6
  (ports, port data types and fakes) before T8; its run loop, invariants and replay tasks before the workflow and
  replay tests that run the real engine (T6's `test_build_mismatch_stops_run`, T11's units trap, T19). `eng-contract`
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
