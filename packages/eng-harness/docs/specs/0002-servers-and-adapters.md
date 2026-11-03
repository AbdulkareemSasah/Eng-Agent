---
id: spec-0002-servers-and-adapters
issue: "B-061"
status: draft        # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1, r3]
---

# Spec 0002: eng-harness servers and adapters

Package: `eng-harness` (import package `eng_harness`) · Author: agent identity (bootstrap mode,
[ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §4) · Date: 2026-11-03

This spec implements the `ToolPort` and `HostPort` of the
[engine spec](0001-engine.md) ("engine §n") for the Sasaah servers and command-line tools
([ADR-0024](../../../../design/docs/adr/0024-harness-on-existing-sasaah-servers.md)): `harness.toml` server sections,
server processes and Job Objects, the MCP sessions, the build check, the host-instance lock and process guard, the
adapter framework, the CSI adapter for the edit cycle on ETABS, the command-line tool adapter, record mode and the test
fakes, and `eng-harness doctor`. It follows [11](../../../../design/docs/architecture/11-harness-engine.md) ("11 §n")
§6 items 2, 6, 8, 9, 10 and §9, with [ADR-0030](../../../../design/docs/adr/0030-replay-by-step-path-and-reconciliation.md)
decisions 7 and 8, and proposes [ADR-0031](../../../../design/docs/adr/0031-model-locked-after-analysis.md)
(`model_locked`) and [ADR-0032](../../../../design/docs/adr/0032-harness-side-model-identity.md) (model identity).
Tool facts come from the [S-12 report](../../../../spikes/S-12-sasaah-tool-inventory/REPORT.md) ("S-12 §n") and its
`inventory/*.json` at Sasaah commit `61da80f61a6562c8e3553168056bc107e3f93013`; the Job Object facts from the
[S-10 report](../../../../spikes/S-10-replay/REPORT.md) ("S-10"). The contract API is
[eng-contract spec 0001](../../../eng-contract/docs/specs/0001-eng-contract-0.1.md) ("contract §n"). Details that the
architecture leaves open are marked **[added]** and listed in §11.

## 1. Problem

The session review behind ADR-0024 (Sasaah `agent-sessions/_baseline/REPORT.md` §5 and §6) lost most host time to
deployment and session failures, not to the servers' tools: a server build older than its own fix failed 7 of 7 design
runs with `model_locked`; 10 of 74 analysis runs timed out with an unknown outcome; `csi_attach` failed with
`target_disconnected`; more than 8 ETABS instances were left orphaned by scripts; one session killed a process that
belonged to another session and an engineer's SAP2000 session disappeared; an unlock reached the engineer's own
instance and deleted its results; thicknesses came out 1000 times too large from an unintended unit in a
`define_*_section` call. The Sasaah servers do not guard any of this themselves (S-12 §3 to §7). The harness has to:
start and stop them so nothing is orphaned, refuse a server build it was not tested with, keep one driver per host
instance, close only what it started, speak the contract on their behalf, report honest outcomes after timeouts, and
check units and read back after every write.

## 2. Reuse research

| Candidate | Finding | Decision |
|---|---|---|
| Official MCP Python SDK 2.x (`mcp` 2.3.0, MIT; read from the installed package) | `mcp.Client(server, mode=..., cache=..., read_timeout_seconds=...)` accepts any `Transport` (an async context manager yielding the read and write streams, `mcp/client/_transport.py`); `call_tool(name, arguments, read_timeout_seconds=...)` raises `MCPError` with `REQUEST_TIMEOUT` after sending a courtesy `notifications/cancelled` (`mcp/shared/jsonrpc_dispatcher.py`); `list_tools(cursor=, cache_mode=)`; `server_info` after the handshake. Its own `stdio_client` on Windows creates a Job Object with kill-on-close **after** the spawn and without breakaway (`mcp/os/win32/utilities.py`: "if that ever bites, the fix is a CREATE_SUSPENDED spawn") | Used for the client session and message types (`mcp_types.jsonrpc_message_adapter`, `mcp.shared.message.SessionMessage`). Its `stdio_client` and `StdioServerParameters` are **not** used: the race and the missing breakaway contradict ADR-0030 decisions 7 and 8. The harness supplies its own `Transport` over its own process (§4.3.3). New runtime dependency: package ADR (plan T1) |
| S-10 `jobobject.py` | Proves the job mechanism; uses `Popen`, a thread scan to resume and a PID lookup to assign | Design reused, code not (S-10 "PID use"): `CreateProcessW` with handles in hand |
| S-02 and S-04 scripts | Call sequences against the real server (launch, open copy, save, analysis, design, unlock probe, model-state reads, table keys) | The call sequences and the read set are reused as the basis of the CSI adapter and of the record-mode scripts; code not copied |
| `ctypes`, `msvcrt`, `fcntl`, `tomllib`, `hashlib`, `subprocess` (standard library) | Win32 calls, OS locks, configuration, hashes, the POSIX launcher | Used; no `pywin32` import (it is a transitive dependency of `mcp` on Windows only) |
| `eng-contract` 0.1 | Envelopes, `ResultStore`, `ModelStateStore`, `validate_input`, `ParamModel`, `eng_param`, `units.csi_unit_system`, `convert`, `extract_raw_reply`, kinds, `resolve_workspace` | Used; no logic re-implemented |
| Sasaah's own audit log (`--audit-log`, `CsiAuditJournal.cs`) | Records Write, Destructive and Code calls with an argument hash and result code (S-12 §5) | Pointed at the run folder; read as reconciliation evidence only (a call completing on an abandoned thread is not recorded as completed) |

## 3. Acceptance criteria

Test paths are relative to `packages/eng-harness/`. "Synthetic CSI fake" is the test-only MCP server of §4.8.3 (lead
decision D-5), run as a real process over stdio. "Fake-host workflow test" is a test block run by the real engine
with the real `ToolPort` and `HostPort` of this spec against synthetic fakes.

### 3.1 `harness.toml`

- AC1. Given a `harness.toml` with every required key, when loaded, then `ServersConfig` holds each server's command,
  arguments, environment, roles with their call timeouts, pinned build and toolsets, and each command-line tool's
  shell, script, declared inputs and outputs and timeout. Test: `tests/unit/servers/test_config.py::test_load_full`.
- AC2. Given a server or tool without a timeout, a role without `call_timeout_s`, or no `client_grace_s`, when
  loaded, then `ConfigError` names the key; no timeout has a default. Test:
  `tests/unit/servers/test_config.py::test_timeouts_required`.
- AC3. Given arguments or environment that enable scripts, generic invoke, attached writes or read-only mode
  (§4.2 forbidden list), or a toolset that includes an escape hatch, when loaded, then `ConfigError`. Test:
  `tests/unit/servers/test_config.py::test_forbidden_options`.

### 3.2 Processes and Job Objects

- AC4. Given the POSIX launcher, when a server is stopped, then `terminate_job` ends it and its children (one process
  group per server) while a host stand-in it started in a new session survives; when the engine process is killed,
  the server exits on stdin end-of-file. Tests: `tests/unit/servers/test_launcher_posix.py::test_group_terminated`,
  `::test_server_exits_when_engine_killed`.
- AC5. Given Windows, when a server is started, then it is created suspended, assigned to its own job with
  kill-on-close and silent breakaway, resumed, and the job handle is not inheritable; killing the engine ends the
  server and its non-breakaway children, while a child the server starts survives (silent breakaway). Tests:
  `tests/windows/test_jobs.py::test_suspended_assign_resume`, `::test_kill_on_close`, `::test_breakaway_survives`.
- AC6. Given a command-line tool job (no breakaway), when the step times out, then every process of the job ends and
  the step fails `TIMEOUT_NO_EFFECT`. Tests: `tests/unit/servers/test_launcher_posix.py::test_tool_timeout_kills_group`,
  `tests/windows/test_jobs.py::test_tool_job_no_breakaway`.
- AC7. Given a running process, when `ProcessInspector.identity(pid)` is read twice, then the start time is equal;
  given a pid reused by a new process, then `alive(pid, started_at)` is false; `terminate(pid, started_at)` ends the
  process only if both match. Tests: `tests/unit/servers/test_procinfo.py::test_identity_stable`,
  `::test_terminate_checks_start_time`, `tests/windows/test_procinfo.py::test_identity_windows`.

### 3.3 MCP session and build check

- AC8. Given a synthetic CSI fake, when the session starts, then the MCP handshake runs over the harness transport,
  `tools/list` is read uncached and completely (all pages), and a `tools/call` round trip returns the raw reply. Test:
  `tests/workflow/servers/test_session.py::test_start_list_call`.
- AC9. Given the pinned build, when the build check runs, then the executable SHA-256, `serverInfo` (recorded), the
  allowlist's Sasaah commit and the tool-list fingerprint all match and `ServerCheck.ok` is true; given any one of
  them different, or an allowlisted tool missing, or a script or generic-invoke tool listed, then `ok` false with the
  reason, and the engine stops before any write (engine AC44). Tests:
  `tests/unit/servers/test_buildcheck.py::test_fingerprint_definition`, `::test_each_mismatch`,
  `tests/workflow/servers/test_session.py::test_build_mismatch_stops_run`.
- AC10. Given the S-12 inventory, when the fingerprint of the CSI allowlist is computed from it, then it equals the
  value pinned in the allowlist data (`fingerprint_source = "s12-inventory"`). Test:
  `tests/contract/test_csi_allowlist.py::test_pinned_fingerprint_from_inventory`.
- AC11. Given a server that exits during a call, then a read returns `HOST_NOT_CONNECTED` and a write, analysis,
  design or save returns `TIMEOUT_UNKNOWN_OUTCOME`; the session epoch increases; the next call restarts the server
  (at most `max_restarts_per_run`), repeats the build check, re-attaches to the bound instance by process id, and the
  engine reads units before the next step (engine AC45). Test: `tests/workflow/servers/test_session.py::test_crash_restart`.
- AC12. Given engine shutdown, then each session closes, each server process is waited for up to its grace time and
  then its job is terminated; no host instance is ended by it. Test:
  `tests/workflow/servers/test_session.py::test_shutdown_leaves_hosts`.

### 3.4 Host-instance lock and process guard

- AC13. Given a host instance locked by another live engine process, when this engine addresses it, then
  `ContractError` `HOST_LOCKED` names the holder's run id, and no call is sent; the engine does not retry. Test:
  `tests/unit/servers/test_hostlock.py::test_second_driver_refused`.
- AC14. Given a lock file whose holder has died, then the lock is acquired (the OS released it) and the takeover is
  logged; given the same pid with a different start time, then it is a different lock. Test:
  `tests/unit/servers/test_hostlock.py::test_stale_and_pid_reuse`.
- AC15. Given instances this run launched (journaled `host_started`) and an instance it attached to, when
  `close_started` runs, then only launched instances whose pid and start time still match are closed: through
  `csi_exit` on the launching session, else, for an instance launched hidden, by terminating the process; a visible
  instance that cannot be exited gracefully is left running and reported; the attached instance is never closed.
  Test: `tests/workflow/servers/test_guard.py::test_close_only_started`.

### 3.5 Adapter framework

- AC16. Given the allowlist data, when loaded, then every entry has a kind, timeout class, effect, action, units
  handling and canonical argument model; any name in the escape-hatch deny list, any tool the S-12 inventory marks
  `excluded_from_allowlist`, or a tool absent from the pinned build is refused at load. Tests:
  `tests/unit/adapters/test_allowlist.py::test_entries_complete`, `::test_escape_hatches_refused`,
  `tests/contract/test_csi_allowlist.py::test_against_inventory`.
- AC17. Given a tool outside the allowlist, then `ToolPort.describe` and `call` raise `INVALID_ARGUMENT` and nothing
  is sent. Test: `tests/unit/adapters/test_toolport.py::test_not_allowlisted`.
- AC18. Given canonical arguments with `$ref`s, when called, then references resolve through `eng_contract` (kind,
  pointer, unit, staleness), the input is validated before any host call, values are converted to the units token
  the call passes, and provenance records the references, never the values. Test:
  `tests/unit/adapters/test_args.py::test_refs_resolved_converted_recorded`.
- AC19. Given a host reply, then the envelope carries the canonical-unit payload in the store, a summary of at most
  4096 bytes, inline data only if at most 16384 bytes, `complete` false with `PARTIAL_DATA` when the server reported
  `truncated`, and provenance with tool, build, host program, model id and revision. Test:
  `tests/unit/adapters/test_envelope.py::test_limits_and_provenance`.
- AC20. Given each Sasaah error code of the S-12 table (§4.5.5), then the mapped contract code, `retryable`,
  `host_code`, `host_method` and precondition are as tabled; unexpected text with no code maps to `INTERNAL` with an
  `incident_id`. Test: `tests/unit/adapters/test_csi_errors.py::test_mapping_table` (parametrized over the table).
- AC21. Given a server `timeout` or a client backstop timeout, then a read gives `TIMEOUT_NO_EFFECT`, and a write,
  save, analysis, design or unlock gives `TIMEOUT_UNKNOWN_OUTCOME` with the `op_id`; the host is marked wedged and the
  epoch increases. Test: `tests/unit/adapters/test_timeouts.py::test_timeout_mapping`.
- AC22. Given a timeout on a host whose units were left changed (synthetic fault `units_left_changed`), when the next
  step on that host runs, then `read_units` reports the mismatch and the engine stops with `PRECONDITION_FAILED`
  (`units_verified`) before reconciliation. Test: `tests/workflow/adapters/test_units_after_timeout.py::test_units_trap`.
- AC23. Given a write in flight, when reconciled, then the adapter reads the object's state and answers `applied`,
  `not_applied`, `partial` or `unknown` per §4.5.7, with the evidence stored as a result. Test:
  `tests/workflow/adapters/test_reconcile.py::test_outcomes_per_tool` (parametrized over the write tools).
- AC24. Given a successful write, when the engine's `check_model` runs, then every written item is read back and
  compared; a mismatch (including a thickness written in the wrong units, the x1000 case) is an `error` issue
  `READBACK_MISMATCH`, and a read-back that is not available is `READBACK_UNAVAILABLE` (error). Test:
  `tests/workflow/adapters/test_readback.py::test_mismatch_detected`.

### 3.6 CSI adapter (ETABS)

- AC25. Given the edit-cycle steps of §4.6.1, when each step's tool is called against the synthetic CSI fake, then the
  arguments sent equal the mapping (names, explicit `target`, `units` token, `confirm` only under an approval) and the
  reply becomes the stated kind. Test: `tests/workflow/adapters/test_csi_steps.py::test_step_mapping` (parametrized).
- AC26. Given each edit kind of §4.6.2, then the canonical arguments map to the S-12 tool; an edit kind or direction
  marked "not implemented" raises `NotImplementedGap` (`NOT_IMPLEMENTED`) with its gap id. Tests:
  `tests/workflow/adapters/test_csi_edits.py::test_edit_kinds`, `::test_gaps_not_implemented`.
- AC27. Given the model-state reader, when it reads a model, then it produces `model.stories/1`,
  `model.grid_system/1`, `model.frame_placements/1`, `model.area_placements/1`, `model.load_set/1` and
  `model.joint_restraints/1` payloads that validate, the status (`units`, `locked`, counts), and a fingerprint that
  is the same for the same state read twice and differs after any edit kind; a read that is `truncated` raises
  `LIMIT_EXCEEDED`. Tests: `tests/workflow/adapters/test_csi_state.py::test_kinds_and_fingerprint`,
  `tests/property/test_fingerprint.py::test_order_independent_and_edit_sensitive`.
- AC28. Given analysis or design, then the call goes to the `long` role server with its own call timeout, after the
  engine's save (engine AC43). Test: `tests/workflow/adapters/test_csi_analysis.py::test_long_role_and_save_first`.
- AC29. Given `model_locked` from a write, then until ADR-0031 is accepted the code is `HOST_LOCKED` and no unlock is
  offered; after the switch task, `PRECONDITION_FAILED` (`model_unlocked`), and `csi_unlock_model` runs only under an
  approval. Tests: `tests/unit/adapters/test_csi_errors.py::test_model_locked_interim`,
  `tests/workflow/adapters/test_csi_unlock.py::test_unlock_under_approval` (plan task T15, blocked on ADR-0031).
- AC30. Given a model file at first use, then its identity resolves per ADR-0032 (content hash, path hash, new); a
  working copy gets a new identity `derived_from` the original; every save writes the new content hash before
  `model_saved`; no path is stored. Test: `tests/unit/adapters/test_identity.py::test_resolution_rules`.

### 3.7 Command-line tools

- AC31. Given `dxf-prep/prepare` with input files, when run, then inputs are hashed (`FileSource`), the process runs
  in a tool job in a fresh attempt folder, the declared outputs are hashed into `harness.cli_run/1`, the exit code
  maps per §4.7, and the step is journaled. Test: `tests/workflow/adapters/test_cli.py::test_prepare_outputs_hashed`.
- AC32. Given `etabs-model/build`, then the configuration is copied with `outputFolder` set to the attempt folder and
  relative input paths made absolute; an output that already exists is never overwritten; a pinned build artifact
  whose hash changed during the call fails the step. Test: `tests/workflow/adapters/test_cli.py::test_build_config_and_pins`.

### 3.8 Record mode and fakes

- AC33. Given record mode, when a session runs, then every `tools/list` and `tools/call` request and reply is written
  as a fixture with paths outside the run folder and user names replaced, Project Information reads dropped, and a
  manifest of SHA-256 hashes; the manifest verifies. Test: `tests/unit/servers/test_record.py::test_sanitized_and_manifest`.
- AC34. Given recordings, when the recorded-reply fake serves a session, then the adapter's contract tests pass on
  them, and the synthetic fake gives the same reply shape and error codes for every recorded operation (fake
  fidelity, process/05 §4). Tests: `tests/contract/test_csi_recordings.py::test_adapter_on_recordings`,
  `::test_synthetic_matches_recordings` (skip with reason when no recording exists).
- AC35. Given the synthetic CSI fake, then its tool list equals the S-12 inventory schemas for every allowlisted tool
  (so its fingerprint equals the pinned one) and it is never part of the built package. Tests:
  `tests/contract/test_csi_allowlist.py::test_fake_schemas_match_inventory`,
  `tests/unit/test_package_contents.py::test_fakes_not_shipped`.

### 3.9 Engine integration, replay and doctor

- AC36. Given a test block that runs launch, open copy, read state, unlock-free edits, save, analysis, design and
  results through the real engine and real server processes, then the journal holds every step, check and save, and
  a kill of the engine at each write step followed by a resume reconciles and completes without a repeated write.
  Tests: `tests/workflow/test_csi_cycle.py::test_cycle_steps`, `tests/replay/test_csi_resume.py::test_crash_matrix`.
- AC37. Given `eng-harness doctor`, then it reports uv and Python, each server executable and its hash against the
  pin, each live tool-list fingerprint, installed host programs, the integrity level (warning when not medium), and
  the workspace class, as a table and as JSON with base names only, exit code 0 without failures and 1 with any.
  Tests: `tests/unit/test_doctor.py::test_checks_and_output`, `tests/windows/test_doctor.py::test_integrity_level`.

## 4. Design

### 4.1 Package layout and public API

`packages/eng-harness/src/eng_harness/`, extending the engine layout (engine §4.1.1).

| Module | Public names | Who may import |
|---|---|---|
| `eng_harness.servers` | `ServersConfig`, `ServerConfig`, `RoleConfig`, `CliToolConfig`, `ConfigError`, `load_servers_config`, `ServerManager`, `ServerCheck` (re-export of the port type), `RecordMode` | engine wiring (0006), doctor, tests |
| `eng_harness.adapters` | `build_ports(config, workspace, store, run_dir, clock, ids) -> AdapterPorts` (`tool_port`, `host_port`), `Allowlist`, `ToolDescriptor`, `AdapterError` | engine wiring (0006), tests |
| `eng_harness.doctor` | `run(config_path, *, json_output, show_paths) -> int`, `DoctorReport`, `Check` | CLI (0006) |

Internal modules (planned): `servers/_config.py`, `servers/_launcher.py` (ports, POSIX), `servers/_launcher_windows.py`,
`servers/_procinfo.py`, `servers/_transport.py`, `servers/_session.py`, `servers/_buildcheck.py`,
`servers/_hostlock.py`, `servers/_guard.py`, `servers/_record.py`; `adapters/_descriptors.py`, `adapters/_allowlist.py`,
`adapters/_args.py`, `adapters/_envelope.py`, `adapters/_errors.py`, `adapters/_ledger.py`, `adapters/_toolport.py`,
`adapters/_hostport.py`, `adapters/_identity.py`, `adapters/csi/` (`_allowlist.toml`, `_tools.py`, `_errors.py`,
`_edits.py`, `_replies.py`, `_state.py`, `_reconcile.py`, `_checks.py`, `_session_ops.py`, `products/_etabs.py`),
`adapters/cli/_adapter.py`. Fakes live in `tests/fakes/` only.

### 4.2 `harness.toml`: server and tool sections

Spec 0006 owns where the file is found and its `[engine]` section; this spec owns `[servers.*]`, `[cli_tools.*]` and
`[host_programs.*]`. Example (placeholders in angle brackets):

```toml
[servers.csi]
adapter = "sasaah-csi-mcp"
command = "<absolute path to sasaah-csi-mcp.exe>"
args = ["--disable-script"]            # the adapter adds --call-timeout-sec and --audit-log per role
env = {}                               # added to a minimal inherited environment
toolsets = []                          # the CSI server has no toolset option; listed tools are filtered by the allowlist
client_grace_s = <required>            # client backstop = role call_timeout_s + client_grace_s
max_restarts_per_run = 1               # software setting
shutdown_grace_s = 10                  # software setting
build = { sasaah_commit = "<40 hex>", exe_sha256 = "<64 hex>", server_info_version = "<optional>" }
host_key = "csi"
mcp_mode = "legacy"                    # §11 Q3

[servers.csi.roles.main]               # one server process per role
classes = ["session", "call"]
call_timeout_s = <required>            # passed as --call-timeout-sec (Sasaah default 120 s, CsiServerConfig.cs:18)

[servers.csi.roles.long]
classes = ["long"]                     # analysis and design
call_timeout_s = <required>            # sized by S-02; no default (OQ-G6)

[host_programs.etabs]
executables = ["ETABS.exe"]            # to recognise host instances among processes
install_dirs = ["<optional install folders, checked by doctor>"]

[cli_tools."dxf-prep/prepare"]
shell = "<absolute path to pwsh.exe>"
script = "<absolute path to tools/dxf-prep/prepare.ps1>"
timeout_s = <required>
build_artifacts = [{ path = "<cached CLI exe>", sha256 = "<64 hex>" }]
```

Rules:

1. **No timeout has a default** (11 §9, OQ-G6): `client_grace_s`, every role's `call_timeout_s` and every tool's
   `timeout_s` are required until S-02 measures them; the doctor prints the Sasaah default for comparison only.
   `max_restarts_per_run` and `shutdown_grace_s` are software settings with defaults.
2. **Roles.** Each role is one server process with one server-wide `--call-timeout-sec` (the Sasaah server has no
   per-call timeout, S-12 §5). Every timeout class of the adapter's descriptors must be served by exactly one role. A
   configuration with only a `main` role serving all classes is allowed (`single` topology) and the doctor warns that
   a hung read then waits as long as an analysis (§11 Q2).
3. **Forbidden options and environment** (S-12 §8, `inventory/sasaah-csi-mcp.json` `server.start_options`):
   `--enable-script`, `--enable-generic-invoke`, `--allow-attached-writes`, `--read-only`, and the variables
   `SASAAH_CSI_ENABLE_SCRIPT` (any value) and `SASAAH_CSI_DISABLE_SCRIPT` other than true. `--disable-script` is
   required for the CSI adapter. `--call-timeout-sec`, `--audit-log` and `SASAAH_CSI_CALL_TIMEOUT_SEC` are set by the
   adapter only. Phase 4 adds `--disable-script` as required for the IDEA server (OQ-G13).
4. Paths are absolute; the loader never resolves against the working directory. The file holds no secrets.

### 4.3 Server lifecycle

#### 4.3.1 Launcher and process inspector (ports)

`ProcessLauncher` (`typing.Protocol`): `start(spec: LaunchSpec) -> LaunchedProcess`. `LaunchSpec`: `argv`, `env`,
`cwd` (the run folder), `stderr_path`, `job: JobPolicy` (`SERVER`: kill on close, silent breakaway; `TOOL`: kill on
close, no breakaway). `LaunchedProcess`: `pid`, `started_at` (from the inspector), `stdin`, `stdout` (binary pipes),
`wait(timeout) -> int | None`, `terminate_job()`, `job_members() -> list[ProcessIdentity]`, `close()`.

`ProcessInspector`: `identity(pid) -> ProcessIdentity | None` (`pid`, `started_at: str`, `exe_name`), `alive(identity)
-> bool`, `children(pid) -> list[ProcessIdentity]`, `snapshot(exe_names) -> list[ProcessIdentity]`,
`terminate(identity) -> bool`. `started_at` is the OS creation time as an opaque string (Windows: the creation
`FILETIME` from `GetProcessTimes` as an integer; Linux: `/proc/<pid>/stat` field 22 plus the boot id from
`/proc/sys/kernel/random/boot_id`). `terminate` opens the process once, compares the start time on that handle and
terminates through the same handle, so a reused pid is never hit.

- **POSIX** (development and Linux CI only; no host program runs there): `subprocess.Popen` with
  `start_new_session=True`; the "job" is the process group and `terminate_job` is `killpg`. POSIX has no kill-on-close
  job: when the engine is killed, a server ends because its stdin reaches end-of-file (the synthetic fakes exit then).
  This is enough for tests; the guarantee for the owner's machine is the Windows job.
- **Windows** (`_launcher_windows.py`, `ctypes` only): `CreateJobObjectW`; `SetInformationJobObject` with
  `JobObjectExtendedLimitInformation` and `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, plus
  `JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK` for `SERVER` jobs (ADR-0030 decision 8); the job handle is created
  non-inheritable. `CreateProcessW` with `CREATE_SUSPENDED | CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT |
  EXTENDED_STARTUPINFO_PRESENT` and a `PROC_THREAD_ATTRIBUTE_HANDLE_LIST` that lets the child inherit only its three
  pipe handles; `AssignProcessToJobObject(job, hProcess)`; `ResumeThread(hThread)`; both handles are kept. Members are
  listed with `QueryInformationJobObject` (`JobObjectBasicProcessIdList`). Flag values come from the Windows SDK
  headers and the Win32 pages "JOBOBJECT_BASIC_LIMIT_INFORMATION", "Process Creation Flags" and
  "UpdateProcThreadAttribute", cited next to each constant in code (software constants, not stated here). If
  `AssignProcessToJobObject` fails, the suspended process is terminated and the start fails.
- **Breakaway choice** (S-10 open risk, ADR-0030 decision 8): `SILENT_BREAKAWAY_OK` for server jobs, because the
  Sasaah server does not pass `CREATE_BREAKAWAY_FROM_JOB` when it launches a host (S-12 shows `csi_launch` goes through
  the CSI helper's `CreateObject`, Sasaah `CsiSession.cs:214-280`), and a host killed with the server would lose an
  engineer's work. Cost: helper processes a server starts also break away; the guard (§4.4.2) lists the children of
  job members after every call and at stop, records those that are not host programs, and terminates them at server
  stop when their identity still matches. `JOB_OBJECT_LIMIT_BREAKAWAY_OK` becomes the target when Sasaah passes the
  flag (owner queue). Tool jobs allow no breakaway: a command-line tool's own hidden ETABS ends with the tool.

#### 4.3.2 Server roles and start

`ServerManager` starts each role lazily before its first call, in the run folder, with
`argv = [command, *args, "--call-timeout-sec", str(role.call_timeout_s), "--audit-log", run_dir/"servers"/f"{server}-{role}-audit.jsonl"]`
and stderr to `run_dir/servers/<server>-<role>.stderr.log`. Integrity level (16 §6): the server inherits the
engine's; nothing elevates or lowers it.

#### 4.3.3 Transport and MCP session

`ProcessTransport(launched)` implements the SDK's `Transport`: two worker threads (through `anyio.to_thread`) read
`stdout` lines and write `stdin` lines, parse with `mcp_types.jsonrpc_message_adapter` into `SessionMessage`, as the
SDK's `stdio_client` does; EOF or a broken pipe closes the read stream, which the session sees as the connection
ending. The session is `mcp.Client(transport, mode=config.mcp_mode, cache=None, read_timeout_seconds=None)`:
`cache=None` so every `tools/list` reaches the server; timeouts are per call. Each call is
`client.call_tool(name, args, read_timeout_seconds=role.call_timeout_s + config.client_grace_s)`; the server's own
timeout (`timeout`) is expected first and the client one is a backstop (§4.5.6).

#### 4.3.4 Build check (11 §6 item 8)

`ServerManager.preflight(min_builds) -> list[ServerCheck]`, run at run start and at every resume and restart, before
any write. Per server:

1. SHA-256 of `command` equals `build.exe_sha256`.
2. `client.server_info` is recorded (name, version); if `build.server_info_version` is set, it must equal it (Sasaah
   sets none today, S12-G1; what the SDK reports by default needs a local test).
3. `build.sasaah_commit` equals the adapter allowlist's `sasaah_commit` (the build the adapter was tested with) and
   satisfies the workflow's minimum, which names a Sasaah commit; "at least" is not evaluable without a build id
   (S-12 §3), so the minimum is satisfied by equality or by a commit listed in the allowlist's `also_tested_commits`.
4. **Tool-list fingerprint** over the allowlisted tools: `sha256(canonical_json(sorted([{"name": n, "input_schema":
   strip(s)} for each allowlisted n])))`, where `strip` removes every `description` and `title` member whose value is
   a string, except members of a `properties` object (a property may be named `description`). It must equal the
   allowlist's `tool_fingerprint`. Every allowlisted tool must be listed. A listed `csi_run_script`, `csi_invoke` or
   `csi_object_*` fails the check (they are hidden by the required start options; seeing one means the options
   failed); `csi_db_tables_apply` is always listed (S12-G7) and is tolerated but never callable. The full-list
   fingerprint is recorded too, for diagnosis.
5. `csi_status.read_only` and `script_enabled` are false.

A failure returns `ServerCheck(ok=False, reason=...)`; the engine stops with `SERVER_CHECK_FAILED` (engine §4.6
item 8). `ServerCheck.build` is `"<commit[:12]>+<exe sha256[:12]>"`, also used as `provenance.tool_version`.

#### 4.3.5 Crash, reconnect, restart, shutdown

- **Crash**: the process exited or the transport closed. In-flight call outcome per §4.5.6; the role is marked
  `crashed`; `session_epoch(host_key)` increases.
- **Restart**: before the next call to that role, if fewer than `max_restarts_per_run` restarts were made: terminate
  the old job, start the role again, run the build check, then `csi_attach` with the bound instance's `pid` and
  `product` (S-12: attached instances are `launched: false`, so `csi_open_model`, `csi_new_model` and `csi_exit` are
  refused afterwards; the guard and `restore` account for it). The epoch increases. Beyond the limit: the call fails
  `HOST_NOT_CONNECTED` and the engine escalates. Restarting a role never touches another role or a host instance.
- **Reconnect** (11 §6 item 9): `no_target` or `target_disconnected` on a read → `csi_attach` by pid once on the same
  role, epoch increases, then the read is retried by the engine (retry rule `always`). The engine reads units before
  the next step on that host because the epoch changed (engine §4.6 item 9 (c)).
- **Long role attach**: the `long` role attaches by pid to the instance the `main` role launched, before its first
  call. An attach failure (`target_disconnected`, as in the baseline when the instance is not registered for COM) is
  `HOST_NOT_CONNECTED`; whether a server-launched instance can be attached by a second server is a local test (§12).
- **Shutdown**: close each `Client`, wait `shutdown_grace_s` for the process, then `terminate_job`; then the guard
  terminates recorded helpers (§4.4.2). Host instances are closed only by `close_started`.

### 4.4 Host-instance lock and process guard (11 §6 item 10)

#### 4.4.1 Lock

- A machine-level lock per host instance, keyed by program, pid and start time:
  `<lock_dir>/host-<program>-<pid>-<started_at>.lock`, where `lock_dir` is `%LOCALAPPDATA%\eng\locks` on Windows and
  `$XDG_STATE_HOME/eng/locks` (else `~/.local/state/eng/locks`) on POSIX **[added]**: not the workspace, because two
  workspaces can drive one instance (Sasaah `DESIGN-NOTES.md` ج6).
- Acquire: open or create the file, then an exclusive non-blocking OS lock (`msvcrt.locking(LK_NBLCK)` on byte 0,
  `fcntl.flock(LOCK_EX | LOCK_NB)`), held by the engine process until release or exit; the OS releases it when the
  process dies, so a lock whose holder died is acquired normally (stale handling) and the previous holder record is
  logged. After acquiring, the holder record (`engine_pid`, its `started_at`, `run_id`, `acquired_at`) is written to
  the file. Lock files are never deleted (deleting a lock file others may hold races); a new instance with a reused
  pid has another start time, so another file.
- Refusal: `ContractError(HOST_LOCKED, message="host instance driven by run <run_id>")`, never retried (04 §8.1).
- `HostPort.acquire(host_key)` returns a `HostLease` for the server group; the lease locks each instance before the
  first call addressed to it: after `csi_launch` returns (and before any other call), or before `csi_attach` to an
  existing instance. At resume, `acquire` re-locks every instance in the adapter's run state that is still alive.
  Limitation: a program that drives a host without this lock (another tool on the same machine) is not stopped;
  the adapter therefore writes only to instances it launched.

#### 4.4.2 Process guard

- **Which instances the run started.** For `csi_launch`, the adapter snapshots processes of the host program's
  executables before and after the call; the instance is the pid the reply or `csi_status` names, confirmed by
  appearing in the "after" snapshot only, with a start time after the call began. Zero or several candidates →
  `ContractError(CONFLICT, "launched instance not identified")`, and the run escalates; the instance is not adopted.
  (Sasaah's own pid detection is the same diff and can pick another session's new instance, `CsiSession.cs:282-300`.)
  The identity (`pid`, `started_at`, program, `visible`) goes to `HostPort.started_instances`, which the engine
  journals as `host_started` (engine §4.6 item 10).
- **Closing** (`close_started(host_key, instances)`, at run end only): for each instance whose pid and start time
  still match: `csi_exit(confirm=true)` through the role session that launched it, if that session is alive and was
  not restarted; otherwise, if the instance was launched with `visible: false`, `ProcessInspector.terminate`;
  otherwise it is left running and listed in `run_dir/hosts/left_open.json` for the run report (0006). An instance
  whose identity no longer matches is ignored. Instances the run did not start are never closed. Idempotent.
- **Helpers**: children of job members that are not host executables are recorded with their identity at each
  observation and terminated at server stop if they still match (ADR-0030 decision 8 trade-off).

### 4.5 Adapter framework

#### 4.5.1 Tool descriptors and the allowlist (data)

An adapter's allowlist is a TOML file in the package (`adapters/csi/_allowlist.toml`), pinned with the server build:
header `adapter`, `sasaah_commit`, `also_tested_commits`, `tool_fingerprint`, `fingerprint_source` (`s12-inventory`
until a recording replaces it, then `recording`), and one `[[tool]]` entry per tool:

| Field | Values |
|---|---|
| `name` | the server's tool name |
| `kind` | `read`, `write`, `analysis`, `design`, `session` (S-12 classification, reviewed) |
| `timeout_class` | `session`, `call`, `long` |
| `effect`, `action` | engine `ToolInfo` (engine §4.8): effect `read` or `write`; action `plain`, `open`, `save`, `analysis`, `design`, `delete`, `unlock` |
| `args_model` | name of the canonical argument model (`ParamModel`, contract §5) in the adapter's Python code |
| `result_kind` | the kind the reply becomes |
| `units` | `token` (the tool takes `units` and restores them: the adapter passes a token), `none`, `present` (quantities follow present units: only allowed for tools without quantity arguments in v1), `declared_ignored` (the reply is in present units whatever `units` says: `csi_get_assigned_loads`) |
| `confirm` | `never`, `approved` (the adapter sets `confirm: true` only for a step under an approval or an engine-inserted always-ask approval), `owned` (also needs a server-launched instance) |
| `readback` | the read-back helper name, required for every `write` |
| `products` | products the entry applies to (`ETABS` in v1; SAFE and SAP2000 later) |

`ToolInfo.engineering_params` are the `args_model` fields declared `engineering_quantity`; references are required
for them (11 §6 item 2). **Escape hatches never**: the loader refuses a name in the deny list (`csi_run_script`,
`csi_db_tables_apply`, `csi_invoke`, `csi_object_add`, `csi_object_delete`, `csi_object_set`, `csi_object_get`, and
for later adapters `idea_run_script`, `compile_and_run`, `revit_send_code_to_revit`, `dev_hot_run`, `dev_hot_unload`,
`run_baked_tool`, the bake-suggestion tools, `batch_execute`, `run_synapse_command`), any name containing `script`,
`invoke`, `eval` or `tables_apply`, and any tool the S-12 inventory marks `excluded_from_allowlist`; a contract test
checks the file against the inventory. Tools with an untyped `spec` (`csi_define_material`,
`csi_define_frame_section`, `csi_define_area_section`, `csi_define_load_case`) are not on the v1 allowlist (§4.6.2,
gap H-G1).

#### 4.5.2 Arguments from neutral kinds and references

`ToolPort.call(tool, args, op_id=, model=)`: (1) look up the descriptor; (2) `validate_input(args_model, args,
source=store, current_revision=<adapter revisions>, policy=InputPolicy(require_refs=True))` (contract §5): shape,
policy, references (kind, pointer, unit, staleness), units, bounds, cross-field rules, never changing a value; (3)
the host preconditions (§4.5.8); (4) the tool's builder turns the validated canonical model into host arguments:
quantities converted with `eng_contract.units.convert` from the canonical unit to the units of the token the call
passes (`csi_unit_system(token)`), the explicit `target` (`product`, `pid` of the model's bound instance, never
omitted: Sasaah `TargetResolver.cs` otherwise uses the session's current target), and `confirm` per the descriptor;
(5) append the op to the ledger (§4.5.7) and send.

#### 4.5.3 Envelopes, provenance and storage

Every reply is parsed with `eng_contract.mcp.extract_raw_reply` (the Sasaah servers send one JSON text block, with
`isError: true` and `{code, message, data}` on failure, S-12 §6) and becomes a contract envelope:

- the payload, in canonical units, validated against `result_kind`, stored with `ResultStore.put`; `parents` are the
  results of the resolved references;
- `summary` at most 4096 bytes and inline `data` only when at most 16384 bytes (contract §4.2.5); larger data is in
  the store and `data` is null;
- `complete: false` and `PARTIAL_DATA` when the reply says `truncated: true` (lists are capped at 2000 with no paging,
  S-12 §2);
- provenance: `tool = "<adapter>/<tool>"` (for example `sasaah-csi-mcp/csi_assign_frame_section`), `tool_version`
  the build string (§4.3.4), `host` (`program`, `version` from `csi_model_info.program_version`, `model_id`,
  `model_revision`), `files` for file inputs, `inputs` (references as references), `started_at`, `duration_ms`.

#### 4.5.4 Units handling

The adapter never relies on the present units being canonical. For a `token` tool it chooses the token whose units
make the conversion simplest for the call's quantities and always passes it; for `declared_ignored` and for
interpreting reply values of `none` tools it reads `csi_model_info.units` first (one read per batch) and labels the
values with that system. A model in a `Ton_*` system is refused (`UnitGapError`, contract G-1). Expected units of a
model are its units when the adapter first opened it, kept in the run state (§4.5.9); `read_units` compares
`csi_model_info.units` of the bound instance with them (11 §6 item 9).

#### 4.5.5 Error mapping (S-12 §6, ADR-0031)

| Sasaah code | Contract code | Rule |
|---|---|---|
| `no_target` | `HOST_NOT_CONNECTED` | reconnect once (§4.3.5) |
| `ambiguous_target` | `INVALID_ARGUMENT` | should not occur: `target` always carries `pid` |
| `target_disconnected` | read: `HOST_NOT_CONNECTED`; write, save, analysis, design, unlock: `TIMEOUT_UNKNOWN_OUTCOME` | the code also covers bridge timeouts |
| `timeout` | read: `TIMEOUT_NO_EFFECT`; others: `TIMEOUT_UNKNOWN_OUTCOME` | host marked wedged, epoch increases |
| `com_worker_recycled` | `TIMEOUT_NO_EFFECT` | the call never started (its message says so) |
| `unsupported_by_version`, `api_not_available` | `NOT_SUPPORTED_BY_VERSION` | |
| `confirmation_required` | `CONFIRMATION_REQUIRED` | an adapter bug: confirm is set only under approval |
| `model_locked` | interim `HOST_LOCKED`; after ADR-0031 `PRECONDITION_FAILED` (`model_unlocked`) | never retried; certain not-applied |
| `not_launched_by_server` | interim `CONFLICT`; after ADR-0031 `PRECONDITION_FAILED` (`server_owned_instance`) | |
| `read_only`, `script_disabled`, `generic_invoke_disabled`, `unsupported_operation` | `INTERNAL` | a configuration or allowlist bug |
| `csi_error` with `data.member`, `data.return_code` or `data.hresult` | `HOST_ERROR`, `host_code` from `return_code` or `hresult`, `host_method` from `member`, `retryable: false` | |
| `csi_error` without such data | `NOT_FOUND` when the message matches one of the adapter's listed "not found" texts (for example "was not found", "does not exist"), else `INVALID_ARGUMENT` | the texts are listed in `csi/_errors.py` with their Sasaah source lines |
| no code (unexpected-error text) | `INTERNAL` with a new `incident_id`; on a write, `TIMEOUT_UNKNOWN_OUTCOME` when the text says the call timed out | `Program.cs:102-106` |

The original code and message are kept in the stored failure evidence (never in a summary beyond 2000 characters).

#### 4.5.6 Timeouts

- The server's `timeout` arrives within the role's `call_timeout_s`; the client backstop
  (`call_timeout_s + client_grace_s`) covers a server that never answers. A backstop on a read is
  `TIMEOUT_NO_EFFECT`; on a write, save, analysis, design or unlock it is `TIMEOUT_UNKNOWN_OUTCOME`. After a backstop
  the role is restarted before its next call (the SDK has cancelled the request; the server's worker may still hold
  the host).
- After any `timeout`, backstop, crash or reconnect, the host is "wedged" for the adapter: `session_epoch` increases,
  and the engine's reconciliation (invariant 6) and units read (invariant 9) run before the next step on that host.
  Until `reconcile` has run for the in-flight op, `ToolPort.call` on that host returns `HOST_WEDGED` without sending;
  the `HostPort` reads the engine runs first (`read_units`, `model_state`) and `reconcile` itself are allowed.

#### 4.5.7 Write ledger and reconciliation by reading model state

Before sending a write, the adapter appends `{op_id, tool, args_sha256, target, pre_image_ref, sent_at}` to
`run_dir/adapter/ops.jsonl` (flushed and `fsync`ed), where `pre_image_ref` points to the last model-state read of the
object (the adapter's state cache, refreshed by `check_model` and `model_state`). `reconcile(tool, args, op_id)`
first waits for the host to answer `csi_model_info` within the `call` class (a timeout → `unknown`), then reads the
object with the tool's read-back helper and decides:

| Tool kind | `applied` | `not_applied` | `partial` / `unknown` |
|---|---|---|---|
| Setters (`csi_assign_frame_section`, `csi_assign_area_section`, `csi_set_point_restraint`, `csi_set_frame_load_distributed`, `csi_set_area_load_uniform`, `csi_define_wall_section`) | the state equals the requested state | the state equals the pre-image and differs from the request | anything else: `unknown` |
| `csi_add_load_pattern` | present with the requested type and self-weight | absent | present with other values: `unknown` |
| `csi_add_load_combo` (delete then re-add, not atomic, S-12 §2) | present with the requested type and components | absent and absent before | absent but present before: `partial` (`missing: [name]`); present with other components: `unknown` |
| `csi_delete_load_combo` | absent | present | — |
| `csi_save_model` | the file exists and its hash differs from the pre-save hash | the file is unchanged and the model is dirty | otherwise `unknown` |
| `csi_unlock_model` | `locked` false | `locked` true | — |
| `csi_run_analysis`, `csi_design_run` | — | the host answers and units match: a re-run recomputes the same results, so the step runs again (§11 Q4) | the host does not answer: `unknown` |

The evidence (reads, the Sasaah audit-log lines for the op, if any) is stored as a result and referenced from the
`Reconciliation`. A read-back that is not available for the tool gives `unknown` (the engineer decides, engine §4.5.3).

#### 4.5.8 Host preconditions, read-back and check after write

- Before a write: the model is bound and its instance locked; units were verified in this epoch; for `owned` tools
  the role session launched the instance and was not restarted (else the interim `CONFLICT` or, after ADR-0031,
  `server_owned_instance`).
- `HostPort.check_model(model_key)` (engine invariant 1): reads back every item written since the last check with the
  read-back helpers, compares with the requested state, and returns `issues.model_check/1` with `READBACK_MISMATCH`
  or `READBACK_UNAVAILABLE` (error), plus the integrity checks that need no tolerance: frames or areas whose section is
  not defined (`SECTION_UNDEFINED`), combinations naming a missing pattern or combination (`COMBO_REFERENCE_MISSING`),
  the model locked (`MODEL_LOCKED`, info). Quantities read back are compared within the design basis field
  `checks.readback_relative_tolerance` (required by every workflow that writes quantities; never a constant here,
  §11 G-2). The 06 §7 list is otherwise not implemented in v1 (gap H-G4).
- **Save before analysis** (11 §6 item 7): `HostPort.save(model_key, role)` calls `csi_save_model(path=<current>,
  confirm=true)` on the `main` role, hashes the file, updates the identity store (ADR-0032) and returns `SavedModel`;
  the engine journals `model_saved` before the analysis.

#### 4.5.9 HostPort and ToolPort mapping

| Port method | Implementation |
|---|---|
| `preflight` | §4.3.4 |
| `acquire`, `release` | §4.4.1 |
| `session_epoch` | per host key, increased on timeout, crash, restart, reconnect |
| `locate(model_key)` | the bound instance if alive and its `csi_model_info.model_path` (normalized) is the model's file, else `None`; an instance the run did not launch or bind is never searched |
| `model_state(model_key, instance_id)` | §4.6.4; `loaded: false` when the instance is not running or holds another file |
| `check_model`, `save` | §4.5.8 |
| `read_units` | §4.5.4 |
| `working_copy(model_key, folder)` | copy the model file into `folder` (hash before and after the copy must match), launch a hidden instance on the `main` role if the host has none for this run, lock it, `csi_open_model(copy, confirm=true)`, record expected units, identity `derived_from` the original (ADR-0032); returns `<model_key>@copy` |
| `restore(model_key, saved)` | check the saved file's hash equals `saved.file_sha256` (else `CONFLICT`); `csi_open_model` on the bound instance if its launching session is alive and not restarted, else launch a new hidden instance (reported by `started_instances`) and open it there |
| `model_files` | the model file only (`.EDB`); companion files are the host's |
| `started_instances`, `close_started` | §4.4.2 |
| `describe`, `call`, `preview`, `read_back`, `supports_reconcile`, `reconcile` | §4.5.1, §4.5.2, preview from the canonical arguments and the pre-image, read-back helpers, true for every `write`, §4.5.7 |

Adapter run state (`run_dir/adapter/state.json`, written atomically): instances, bindings, expected units, the
`visible` flag of launches. It is a cache: where it disagrees with the journal (`host_started`, `model_bound`), the
journal wins.

### 4.6 CSI adapter for the edit cycle on ETABS

Product-specific parts (tool availability, design kinds, result tools that exist only for ETABS such as story
drifts) are in `adapters/csi/products/_etabs.py`; the rest is shared, so SAFE (phase 2) and SAP2000 (phase 3) add a
product module and allowlist entries, not a new adapter.

#### 4.6.1 Steps of the cycle (18 §4; S-12 §1)

| Step | Tools (role) | Mapping |
|---|---|---|
| 1 Server builds | `csi_status` (main), `tools/list` | §4.3.4 |
| 2 Open a working copy | `csi_launch` (main; `product`, `version` from the basis or the configured product, `visible: false` unless the workflow needs an engineer turn in that instance), `csi_open_model` (`confirm`), `csi_save_model` with a new `path` | `HostPort.working_copy`; never on an instance the run did not launch (S-12 §1 step 2) |
| 3 Read the model state | `csi_model_info`, `csi_list_stories`, `csi_list_grids`, `csi_list_points`, `csi_list_frames`, `csi_list_areas`, `csi_list_frame_sections`, `csi_list_area_sections`, `csi_list_materials`, `csi_list_load_patterns`, `csi_list_load_combos`, `csi_db_table_read` (tables of §4.6.4) | §4.6.4 |
| 7, 10 Save | `csi_save_model` | `HostPort.save` |
| 8 Apply the edits | §4.6.2 | one call per object (no batch tool, OQ-G7) |
| 9 Read back and check | read-back helpers | §4.5.8 |
| 11 Analysis | `csi_run_analysis` (`confirm`; long role) | synchronous; no start-and-poll (OQ-G6); result `harness.csi_analysis_run/1`; then `csi_analysis_status` (main), raw per-case codes, not decoded, `harness.csi_analysis_status/1` |
| 12 Design | `csi_design_run` (`kind` `steel` or `concrete`, `confirm`; long role) | `harness.csi_design_run/1`; aluminum and cold-formed are `NOT_SUPPORTED_BY_VERSION` |
| 13 Results | `csi_results_joint_reactions` → `forces.joint_reactions/1`; `csi_results_frame_forces` → `forces.member_end/1` (`host_local/1`, contract G-3); `csi_results_story_drifts` → `forces.story_drifts/1`; `csi_design_results` → `harness.csi_design_results/1` (raw host output, never a verdict, 06 §9); table `Analysis Messages` → `harness.csi_analysis_messages/1` | `units` token `kN_m_C` for forces; conversion to canonical by `eng_contract.units` |
| Unlock (ADR-0031) | `csi_unlock_model` (`confirm`) | after the switch task only |

Steps 4 to 6 and 14 to 17 are harness work (workflow spec 0007).

#### 4.6.2 Edit kinds (18 §2; S-12 §2)

| Edit kind | Tool and argument mapping | Read-back | Status |
|---|---|---|---|
| Assign a section to frames | `csi_assign_frame_section(name=frame, section)`, one call per frame; the section must exist (checked against the state) | `csi_list_frames` `section` of the frame | implemented |
| Assign an area section | `csi_assign_area_section(name=area, section)` | table `Area Assignments - Section Properties` | implemented; table key needs local test |
| Change a wall thickness | `csi_define_wall_section(name, material, thickness, wall_type="Specified", shell_type, units)`: `thickness_mm` (engineering quantity) sent with `units="kN_mm_C"`, so the value is millimetres; `shell_type` from the canonical enum `ShellThin`, `ShellThick`, `Membrane` (the schema's values) | table `Wall Property Definitions - Specified` | implemented; table key needs local test |
| Change a slab thickness, define a frame or slab section, define a material | `csi_define_area_section`, `csi_define_frame_section`, `csi_define_material` take an untyped `spec` whose keys are CSi API parameter names not in the schema (S-12 §2) | — | **not implemented**, gap H-G1 (OQ-G11) |
| Uniform load on frames | `csi_set_frame_load_distributed(name, load_pattern, value, direction="gravity", units="kN_m_C")`: `w_kN_m` (engineering quantity) in kN/m; replaces that pattern's load on the frame (`Replace` true, S-12 §2) | table `Frame Loads Assignments - Distributed` | implemented for `gravity`; other directions **not implemented**, gap H-G2 (S12-G9) |
| Uniform load on areas | `csi_set_area_load_uniform(name, load_pattern, value, direction="gravity", units="kN_m_C")`: `q_kPa` in kN/m² | table `Area Load Assignments - Uniform` | implemented for `gravity`; other directions gap H-G2 |
| Point loads on frames | `csi_set_frame_load_point` passes `direction` unmapped (S-12 §2) | — | **not implemented**, gap H-G2 |
| Add a load pattern | `csi_add_load_pattern(name, type, self_weight)`: `type` from `model.load_set/1` pattern types `dead`→`Dead`, `live`→`Live`, `seismic`→`Quake`, `wind`→`Wind`, `snow`→`Snow`, `other`→`Other` (the values the tool's schema names); `superimposed_dead` and `roof_live` not mapped (gap H-G3); `self_weight_ratio` (engineering quantity) | `csi_list_load_patterns` (names) plus table `Load Pattern Definitions` for type and self-weight (key needs local test) | implemented for the mapped types |
| Change or delete a load pattern | no tool | — | **not implemented** (OQ-G8) |
| Add or replace a load combination | `csi_add_load_combo(name, combo_type, components)`: `linear_add`→0, `envelope`→1, `absolute_add`→2, `srss`→3 (the schema's codes); `range` not mapped (gap H-G3); components `{name, factor, kind}` from `CaseRef` (`load_combination`→`combo`, others→`case`) and `scale_ratio` (engineering quantity) | `csi_list_load_combos` plus table `Load Combination Definitions` (key needs local test) | implemented; replace is not atomic (§4.5.7) |
| Delete a load combination | `csi_delete_load_combo(name, confirm=true)`, action `delete` (always ask) | `csi_list_load_combos` | implemented; `owned` |
| Change restraints | `csi_set_point_restraint(name, values=[ux, uy, uz, rx, ry, rz])` from `model.joint_restraints/1` (never the presets) | table `Joint Assignments - Restraints` | implemented; table key needs local test |
| Seismic load parameters | no tool (S12-G5) | — | **excluded** (OQ-G8) |

The table keys are those of Sasaah `docs/csi-mcp-server/reference/etabs22-all-tables.json` as used by the S-04 script;
they are confirmed at the first local run (OQ-G10).

#### 4.6.3 Units, timeouts, `model_locked`, identity

- Units: tokens `kN_mm_C` for lengths and thicknesses, `kN_m_C` for loads and forces; values converted from the
  canonical units by `eng_contract.units`, never by hand. The model's present units are left to the server's restore
  and verified by `read_units` (§4.5.4).
- Timeouts: classes from the descriptors; seconds from `harness.toml` (§4.2), never defaulted.
- `model_locked`: §4.5.5 and ADR-0031; the model state reports `locked`.
- Identity: ADR-0032, implemented in `adapters/_identity.py` for every adapter.

#### 4.6.4 Model-state reader and fingerprint

`model_state` reads (all with `units` tokens where the tool takes them, every list with `limit` 2000):

| Kind | Source |
|---|---|
| `model.stories/1` | `csi_list_stories` (`name`, `elevation`, `height`, `is_master`, `similar_to`; Sasaah `CsiModel.cs` story list) |
| `model.grid_system/1` | `csi_list_grids` Cartesian systems (`origin`, `rotation_deg`, `x_lines` and `y_lines` with `id`, `ordinate`, `visible`); other grid types are skipped and listed as `info` issues |
| `model.frame_placements/1` | `csi_list_frames` (`point1`, `point2`, `section`, `label`, `story`); `kind` is `other` (the reply has no design orientation; gap H-G5) |
| `model.area_placements/1` | `csi_list_areas` plus area-section types from `csi_list_area_sections` |
| `model.load_set/1` | patterns (`csi_list_load_patterns` plus the pattern table), combinations (`csi_list_load_combos` plus the combination table), frame and area uniform loads from their tables |
| `model.joint_restraints/1` | table `Joint Assignments - Restraints` |
| status (`harness.csi_model_status/1`) | `csi_model_info`: `units`, `locked` (absent when the host getter failed: then `None`, and any write is refused until it reads), `object_counts`, `program_version`, file base name only |

A list or table read with `truncated: true` raises `LIMIT_EXCEEDED` (the v1 reader cannot see the whole model,
S-12 §2). **Fingerprint**: `sha256(canonical_json({...}))` over the six payloads in the host units tokens used for the
reads (before conversion, so no conversion rounding enters it), with every list sorted by its name or id, plus
`object_counts`; the file save time is not included (it changes on save without a model change). It is stable when
the same state is read twice (property test) and S-04 measures it on real models (§12). `HostModelState`:
`model_id` and `revision` from the identity store and `ModelStateStore`, `fingerprint`, `file_sha256` of the last
save. A fingerprint that changed with no adapter write since the last read increments the revision and adds
`MODEL_CHANGED_OUTSIDE` (04 §3.4).

#### 4.6.5 Fit for phases 2 to 4

| Adapter | What it adds to the framework |
|---|---|
| SAFE, SAP2000 (phases 2, 3) | product modules and allowlist entries in the CSI adapter; the same error table, units, roles and reader structure |
| `sasaah-revit-mcp` (phase 3, 07) | its error parser (one text `"<code> <message> <hint>"`, S-12 §6), the timeout text rule (never started → no effect, executing → unknown outcome), `catalog_version` recorded beside the harness fingerprint, no `units` tokens (mm and degrees in schemas), no save tool (gap OQ-G12) |
| `sasaah-idea-mcp` (phase 4, 08) | `--disable-script` required (scripts are on by default), stub results of `idea_calculate` refused, the missing load unit of `idea_set_loads` (OQ-G13) |

### 4.7 Command-line tool adapter

Tools: `dxf-prep/prepare` and `dxf-prep/inspect` (effect `read`: they write only into the attempt folder) and
`etabs-model/build` (effect `write`, action `plain`: it creates a model in its own hidden ETABS and runs an analysis,
S-12 §12). `etabs-model/classify-columns` is not adopted (engineering thresholds, OQ-G14); the Python helpers are not
tools.

- Invocation: `[shell, "-NoProfile", "-NonInteractive", "-File", script, *named arguments]` in a `TOOL` job, cwd and
  `-OutDir` the attempt folder `run_dir/tools/<step path>/<attempt>/`, bounded by `timeout_s`. Arguments come from a
  canonical model per tool: file inputs as references to `harness.file_input/1` results (engineer-provided files,
  hashed as `FileSource`) or as engineer-chosen paths that are hashed before the run; numeric options (`SnapTol`,
  `BeamSpacing`, `ColumnGrow`) are engineering quantities from the design basis in millimetres, converted to the
  metres the tool takes; options not in the model cannot be passed. The cached CLI executables in `build_artifacts`
  are hashed before and after the call; a mismatch fails the step (`ToolFailed`, harness code `BUILD_CHANGED`
  **[added]**) because the wrappers rebuild from source when it is newer (S-12 §3).
- `etabs-model/build`: the configuration (an engineer input file) is copied into the attempt folder with
  `outputFolder` set to the attempt's output folder, and relative `templateE2k` and `dxf` values made absolute against
  the original file's folder (Sasaah `docs/etabs-model/README.md`: "Relative `dxf`/`templateE2k` paths resolve against
  the config file's folder"); every input it names is hashed. Output files are never written outside the attempt
  folder, so nothing is overwritten.
- Result `harness.cli_run/1`: exit code, duration, declared outputs found (base name, SHA-256, size), the tails of
  stdout and stderr (stored, not in the summary). Exit 0 → success; the tool's documented failure codes (S-12 §12:
  dxf-prep CLI 1 usage, 2 unreadable input, 3 failed; etabs-model 1 failure, 2 usage) → `INVALID_ARGUMENT` for usage
  and unreadable input, `HOST_ERROR` (`host_code` the exit code) otherwise. Timeout → the job is terminated,
  `TIMEOUT_NO_EFFECT` (nothing outside the discarded attempt folder changed). New host-program processes that appear
  during the step and outlive it (a COM-started ETABS outside the job) are reported as a warning, never killed.
- Reconciliation of an in-flight `etabs-model/build`: `applied` when the attempt folder holds the completion record
  the adapter writes after the process ends, else `not_applied` (the next attempt uses a new folder).

### 4.8 Record mode, recorded-reply fakes and synthetic fakes

#### 4.8.1 Recording proxy

`RecordMode` wraps the `ProcessTransport` of a session: every `tools/list`, `tools/call` request and the matching
reply (and the `initialize` result) is written to `acceptance/recordings/<adapter>-<build>/<seq>-<tool>.json`
(process/05 §4). Sanitizing before writing: absolute paths inside the run folder become `<run>/<relative>`, any other
absolute path becomes `<path>/<base name>`; the user name (from the environment) and the home folder become `<user>`
and `<home>`; reads of `Project Information` are dropped entirely (S-04 practice). A `manifest.json` lists every
file with its SHA-256, the adapter, the build string, the tool fingerprint of the recorded `tools/list`, and the
harness version. The owner reviews recordings for client or project names in host messages before committing them
(free text cannot be sanitized mechanically). Record mode is a `harness.toml` switch for live runs and is used by the
record scripts in `acceptance/scripts/` (owner only).

#### 4.8.2 Recorded-reply fake and contract tests

`tests/fakes/recorded/` serves a session from recordings: requests are matched by tool and canonical sanitized
arguments in recorded order; an unmatched request fails the test. Contract tests (`tests/contract/`, marker
`recorded`) run every recorded reply through the adapter (parse, map, envelope, kinds) and compare the recorded
`tools/list` fingerprint with the allowlist's. When a recording exists for a build, the allowlist's
`fingerprint_source` becomes `recording` and its fingerprint is the recorded one.

#### 4.8.3 Synthetic fakes (test-only MCP servers, lead decision D-5)

`tests/fakes/sasaah_csi/server.py`: an MCP server built with the SDK's server API, started as a real process over
stdio by the harness launcher. Its tool list is generated from `tests/fakes/sasaah_csi/schemas.json`, a copy of the
S-12 inventory's names and input schemas (a contract test keeps it equal to the inventory). It holds an in-memory
model (stories, grids, points, frames, areas, sections, materials, patterns, combinations, loads, restraints, units,
`locked`, file path), answers in the Sasaah reply shape (one JSON text block; `isError` with `{code, message,
data}`), and implements the S-12 behaviors the adapter relies on: per-call `units` set and restore, `model_locked`
after analysis, `not_launched_by_server` after attach, `truncated` at `limit`, `com_worker_recycled`. Faults are set
by a control file named in its environment: `timeout_before_apply`, `timeout_after_apply`, `crash_during_call`,
`units_left_changed`, `slow_analysis`. A recording replaces a synthetic fixture per operation: the fake-fidelity test
(AC34) compares the synthetic reply with the recorded one and a mismatch is fixed in the fake first. A synthetic
command-line tool (`tests/fakes/sasaah_cli/`, Python) stands in for the PowerShell scripts on Linux. Nothing under
`tests/` is packaged (AC35).

### 4.9 `eng-harness doctor`

Logic in `eng_harness.doctor`, registered as a subcommand by spec 0006. Checks, each `ok`, `warn`, `fail` or
`skip` with a detail:

| Check | How |
|---|---|
| uv and Python | `uv --version` on PATH; the interpreter is CPython 3.14 (ADR-0028 §5) |
| Server executables and hashes | exists; SHA-256 equals `build.exe_sha256` |
| Tool-list fingerprints | starts each server role briefly (no host program is launched; only `tools/list` and `csi_status`), compares with the allowlist; reports `read_only`, `script_enabled` and installed products from `csi_status` |
| Installed host programs | behind an `InstalledProgramsProbe` interface: v1 checks the declared `install_dirs` and the installed products `csi_status` reports; a registry probe is not implemented until its keys are confirmed (gap H-G6) |
| Integrity level (16 §6) | Windows: the process token's mandatory integrity level (`GetTokenInformation`, `TokenIntegrityLevel`; RID constants cited from the SDK headers); `warn` when not medium; running host instances whose token cannot be read are `skip`. Nothing is changed |
| Workspace | `eng_contract.store.resolve_workspace` with the default location probe: `fail` unless `LOCAL` |
| Timeouts | `warn` for a `single` topology; prints configured values beside the Sasaah default |
| Lock directory | writable; lists lock files whose host instance no longer runs (information only) |

Output: a table, or JSON with `--json`; paths shown as base names unless `--show-paths`. Exit 0 when no check is
`fail`, 1 otherwise.

## 5. Inputs and outputs

| Name | Type | Unit | Bounds | Ref-capable | Source |
|---|---|---|---|---|---|
| `thickness_mm` (wall section) | float | mm | > 0 (a thickness is positive) | yes, engineering quantity | design basis or change set |
| `w_kN_m` (frame uniform load) | float | kN/m | finite | yes, engineering quantity | change set (`model.load_set/1`) |
| `q_kPa` (area uniform load) | float | kPa | finite | yes, engineering quantity | change set |
| `self_weight_ratio`, `scale_ratio` | float | 1 | ≥ 0 | yes, engineering quantity | change set |
| `SnapTol_mm`, `BeamSpacing_mm`, `ColumnGrow_mm` (dxf-prep) | float | mm | ≥ 0 | yes, engineering quantity | design basis |
| `call_timeout_s`, `client_grace_s`, `timeout_s` | int | s | ≥ 1 | no | `harness.toml`, required |
| `checks.readback_relative_tolerance` | float | 1 | > 0 | basis field | design basis (required by writing workflows) |
| Outputs | envelopes of the kinds in §4.6 and §4.7 | canonical | — | — | adapters |

## 6. Errors

| Condition | Code | Fields |
|---|---|---|
| Tool not on the allowlist | `INVALID_ARGUMENT` | `field: tool` |
| Literal for an engineering quantity; reference errors; units; bounds | contract §5 codes | `field` |
| Host instance driven by another engine | `HOST_LOCKED` | message names the run |
| Server build, fingerprint or options mismatch | `ServerCheck.ok` false → engine `SERVER_CHECK_FAILED` | `reason` |
| Launched instance not identified | `CONFLICT` | message |
| Model list truncated at 2000 | `LIMIT_EXCEEDED` | `received` (the count) |
| Model in a `Ton_*` unit system | `UNIT_MISMATCH` (`UnitGapError`) | `received` |
| Edit kind or direction not implemented | `NotImplementedGap` (`NOT_IMPLEMENTED`) | gap id |
| Sasaah error codes, timeouts, crashes | §4.5.5, §4.5.6 | as tabled |
| Pinned command-line build artifact changed | `ToolFailed` (`BUILD_CHANGED`) | artifact base name |
| Configuration invalid or forbidden | `ConfigError` (before any run) | key |

## 7. Non-goals

- Any MCP server for a host program (ADR-0024); the fakes under `tests/` are test doubles only.
- Scripts, generic invoke, table writes or any escape hatch, including as a workaround for a gap.
- The `spec`-based define tools, seismic parameters, load-pattern change or delete, non-gravity load directions,
  point loads on frames (gaps H-G1 to H-G3, OQ-G8).
- Start-and-poll analysis (OQ-G6); batch edit tools (OQ-G7).
- Revit and IDEA adapters (phases 3 and 4; §4.6.5 only shows the fit); SAFE and SAP2000 product modules.
- `harness.toml` discovery, the `[engine]` section and the `eng-harness` command dispatch (spec 0006).
- Engineering checks beyond read-back equality within a basis tolerance; the 06 §7 `check_model` list (gap H-G4).

## 8. Risks

| Risk | Class | Mitigation |
|---|---|---|
| A write repeated or lost after a timeout because reconciliation by reads decides wrongly | R1 | Pre-images, per-tool rules (§4.5.7), `unknown` → engineer; crash matrix (AC36); live test (§12) |
| Units left changed after a timeout produce wrong values (the x1000 class) | R1 | Explicit tokens, units read after every timeout or reconnect, read-back of every written quantity (AC22, AC24) |
| A host program killed with the engine, or an orphaned instance | R1 | Silent breakaway for server jobs, guard closes only identified launched instances (AC5, AC15) |
| Another session's process closed | R1 | Identity by pid and start time, terminate through one handle (AC7) |
| A Sasaah behavior change behind an unchanged schema passes the fingerprint (the baseline's `model_locked` fix) | R1 | Executable hash and pinned commit beside the fingerprint (AC9) |
| The SDK's client API changes in a minor release | R3 | Version range pinned in the package ADR; the transport is ours; contract tests on recordings |
| Windows-only code untested on Linux CI | R3 | `windows` marker in the Windows CI job (AC5, AC6, AC7, AC37) |

## 9. Test strategy

| Criteria | Layer | Location |
|---|---|---|
| AC1 to AC3, AC7, AC13, AC14, AC16, AC17 to AC21, AC29 (interim), AC30, AC33, AC37 | Unit | `tests/unit/` |
| AC4, AC6 (POSIX) | Unit with real processes | `tests/unit/servers/` |
| AC5, AC6, AC7, AC37 (Windows) | Unit, marker `windows` | `tests/windows/` |
| AC10, AC16, AC34, AC35 | Contract (inventory, recordings; markers `synthetic`, `recorded`) | `tests/contract/` |
| AC8, AC9, AC11, AC12, AC15, AC22 to AC29, AC31, AC32, AC36 | Fake-host workflow (real engine, real server processes of the synthetic fakes) | `tests/workflow/` |
| AC36 (crash matrix) | Replay | `tests/replay/` |
| AC27 (fingerprint) | Property (Hypothesis, derandomized in CI) | `tests/property/` |

No golden engineering tests: the adapters compute no engineering value (conversions are the contract's). Coverage
floors 85% line and 75% branch (process/05 §2); mutation testing on `adapters/_errors.py`, `adapters/csi/_errors.py`,
`adapters/csi/_reconcile.py`, `adapters/_args.py`, `servers/_buildcheck.py`, `servers/_hostlock.py` and
`servers/_guard.py` (R1).

## 10. Version impact

Part of `eng-harness` 0.1.0. The allowlist data and its fingerprint are versioned with the package; a new Sasaah
build is a new allowlist header (and recordings) in a minor release. The ADR-0031 switch changes an error mapping: a
minor release with a changelog entry, after the `eng-contract` minor that adds the precondition values.

## 11. Open questions, gaps and additions

| Id | Question or gap | Owner | Recommendation |
|---|---|---|---|
| Q1 | ADR-0031: `model_locked` as `PRECONDITION_FAILED` (`model_unlocked`), `server_owned_instance`, unlock under approval, `unlock` always-ask (engine spec 0001 §4.7 needs the same addition) | Owner | Accept; until then the interim mapping holds and the cycle stops at the second cycle's first edit |
| Q2 | Timeout topology: a dedicated `long` role attached to the `main` role's instance (OQ-Q21), or one role with the analysis timeout | Owner | Dedicated role; fall back to `single` only if the local test shows a second server cannot attach to a server-launched instance |
| Q3 | MCP protocol mode with the Sasaah servers (C# SDK 1.1.0): `legacy` (initialize handshake) or `auto` (probe, then fall back) | Owner | `legacy`, so recordings are deterministic; configurable |
| Q4 | Analysis and design reconcile as `not_applied` (re-run) once the host answers, because re-running recomputes the same results | Owner | Accept; the re-run is journaled as a new attempt; if S-02 shows a re-run can differ (for example after a partial run), switch to `unknown` |
| Q5 | ADR-0032: harness-side identity by content and path hash | Owner | Accept; ask Sasaah for a typed `csi_set_project_info` (S12-G6) |
| Q6 | Silent breakaway lets server helpers escape; the guard terminates recorded helpers | Owner | Accept; ask Sasaah to start hosts with `CREATE_BREAKAWAY_FROM_JOB`, then switch to `BREAKAWAY_OK` |
| Q7 | A launched instance that cannot be exited gracefully and was visible is left running | Owner | Accept: an engineer may be using a visible instance; the run report lists it |
| H-G1 | `csi_define_area_section`, `csi_define_frame_section`, `csi_define_material` need CSi API `spec` keys not in the schema; slab thickness change is therefore not implemented | Owner | Confirm the keys locally and pin a method and key list (OQ-G11), or a Sasaah typed slab tool (the engine's `DefineSlabSection` exists unexposed); test `test_gaps_not_implemented` expects `NOT_IMPLEMENTED` |
| H-G2 | Load directions other than `gravity` and frame point loads (S12-G9) | Owner | Local test of the direction codes, then a Sasaah fix |
| H-G3 | Load pattern types `superimposed_dead`, `roof_live` and combination type `range` have no documented Sasaah value | Owner | Confirm the host names locally; until then refused |
| H-G4 | The 06 §7 `check_model` list beyond tolerance-free checks | Owner | Later minor; duplicates need a basis tolerance |
| H-G5 | `model.frame_placements/1` `kind` cannot be read from `csi_list_frames` | Owner | Read design orientation through `csi_frame_details` after a local check of its reply |
| H-G6 | Registry keys of installed CSI programs | Owner | Not needed while `csi_status` lists installed products |
| G-2 | Read-back of quantities needs a tolerance | Owner | A design basis field `checks.readback_relative_tolerance` with a source; no constant in code |
| A1 | **[added]** machine-level `lock_dir`; harness code `BUILD_CHANGED`; harness kinds `harness.csi_model_status/1`, `harness.csi_analysis_run/1`, `harness.csi_analysis_status/1`, `harness.csi_analysis_messages/1`, `harness.csi_design_run/1`, `harness.csi_design_results/1`, `harness.cli_run/1`, `harness.file_input/1` | Owner | Accept with this spec |
| C1 | Conflict: 11 §9 says analysis may be "started and then followed through `csi_analysis_status`"; S-12 §5 shows the call is synchronous | Owner | This spec follows S-12; amend 11 §9 and 18 step 11 (S-12 "Consequences") |
| C2 | Conflict: 11 §9 and ADR-0008 name two excluded CSI tools; S-12 §8 finds seven, and `DisableScript` does not hide `csi_db_tables_apply` | Owner | This spec excludes all seven; amend 11 §9 and ADR-0008 |
| C3 | The SDK's `stdio_client` on Windows assigns its job after the spawn and allows no breakaway | Owner | Not used (§2); recorded here so a later SDK upgrade is checked against it |

## 12. Needs local test

Listed in `docs/local-testing.md` by the plan (no host program runs in CI): (1) `csi_launch` on the owner's machine:
which process is the ETABS parent (server child or COM activation), the pid the reply names, and that the instance
survives the server job's closure (silent breakaway); (2) a second server (`long` role) attaching by pid to a
server-launched instance; (3) the live `tools/list` fingerprint against the allowlist's (replace the S-12 value with
a recording); (4) `serverInfo` the Sasaah server reports; (5) every table key of §4.6.2 and §4.6.4 and their reply
fields; (6) the reply fields of every list tool mapped in §4.6.4; (7) a server `timeout` during a write and during an
analysis, the units afterwards, and each reconciliation rule of §4.5.7 (with S-02); (8) fingerprint stability and the
blind spots of the read set (S-04); (9) `close_started` closing a hidden launched instance and leaving a visible one;
(10) the host-instance lock across two engine processes; (11) `dxf-prep/prepare` and `etabs-model/build` through the
adapter, including the configuration rewrite and the build-artifact hash; (12) `eng-harness doctor` on the owner's
machine, including the integrity level and installed products; (13) record mode on a copy, and the owner's review of
the recordings before commit.
