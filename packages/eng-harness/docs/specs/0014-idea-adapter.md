---
id: spec-0014-idea-adapter
issue: "B-090"
status: draft        # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1]
---

# Spec 0014: eng-harness, the `sasaah-idea-mcp` adapter (connection checks)

Package: `eng-harness` (import package `eng_harness`) · Author: agent identity (bootstrap mode,
[ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §4) · Date: 2026-11-04

This spec adds the adapter for `sasaah-idea-mcp` to the framework of [spec 0002](0002-servers-and-adapters.md) ("0002
§n") for phase 4 ([19](../../../../design/docs/architecture/19-roadmap-and-spikes.md) §1). It follows
[ADR-0024](../../../../design/docs/adr/0024-harness-on-existing-sasaah-servers.md): the harness is a client of the Sasaah
server; no IDEA server is built, and the target of [08](../../../../design/docs/architecture/08-ideastatica-mcp.md)
(typed edit tools, `check_model`, stress-strain results, a server that starts the REST service) is **not met by the
server and is not built**. Tool facts come from the [S-12 report](../../../../spikes/S-12-sasaah-tool-inventory/REPORT.md)
§11 ("S-12 §n") and `inventory/sasaah-idea-mcp.json` (58 tools) at Sasaah commit
`61da80f61a6562c8e3553168056bc107e3f93013`, and from a read-only reading of the Sasaah sources at that commit that S-12
did not cover (the session, the REST client, the native backend, the stub). In this document `E/` is
`02_Engines/Sasaah.Idea.Engine/` and `S/` is `04_Deployments/Sasaah.Mcp.Idea.Server/` (paths in Sasaah, never copied; line
numbers are at the pinned commit). The contract API is
[eng-contract spec 0001](../../../eng-contract/docs/specs/0001-eng-contract-0.1.md) ("contract §n"). Nothing here was run
against IDEA StatiCa; everything that needs it is "needs local test" (§12, spike S-08). Details the architecture
leaves open are marked **[added]** and listed in §11.

## 1. Problem

The first IDEA use is a connection check: take the member-end forces ETABS computed ([04](../../../../design/docs/architecture/04-tool-contract.md)
§6 `forces.member_end/1`), put them into an IDEA connection by reference, let IDEA run its own code checks, and bring
IDEA's verdicts back as `source: host` verdicts that are never merged with code-pack verdicts (08 §3, 04 §5). The
reading of the Sasaah sources shows that the server does not offer this as the catalog suggests:

1. **Two families, two routes.** The project-model tools (`idea_*`) work on an in-memory model of the server process and,
   for `.ideaCon` files, on the REST service (24.1 and newer). The file-direct tools (`idea_native_*`) drive the hidden
   calculator on a `.ideaCon` file (their descriptions say 21.x) and write a new file.
2. **Edits of the in-memory model do not reach a real calculation.** `IIdeaRestClient` has no method that sends an edit
   to the service (`E/IdeaRestClient.cs:10-20`); `idea_calculate` posts only connection ids to the service
   (`E/IdeaRestClient.cs:158-185`) or runs the hidden calculator on the **source file** of a native project
   (`E/IdeaHiddenCalcClient.cs:186-199`). `idea_set_loads` writes only the in-memory list (`E/IdeaSession.cs:849-873`), which
   only the stub reads. An opened REST project holds only the connection ids and names and the default design code
   `ECEN` (`E/IdeaSession.cs:296-310`, `E/IdeaProject.cs:246`), so its reads (`idea_get_connection`,
   `idea_get_project_settings`) describe Sasaah's defaults, not the host's model. A project "created" through the
   service holds only the design code on the service; the template connection stays in memory (`E/IdeaSession.cs:157-176`).
3. **The stub.** When the service is not reachable, `idea_calculate` returns deterministic, invented utilizations
   (35, 42, 51, 47, 10 percent) marked `offline_stub: true`, `backend: "file"` and a `notice`
   (`E/IdeaSession.cs:1119-1137`, `2165-2190`, `2192-2243`); a failed live project creation silently stays offline
   (`E/IdeaSession.cs:166-181`).
4. **One process holds the project.** The current project, its live id and the results are fields of the server process
   (`E/IdeaSession.cs`), so a second server process (a `long` role as for CSI) cannot calculate what the first one
   opened.
5. **Scripts are on by default** (`E/IdeaModels.cs:435`, S-12 §8), the load effects of `idea_set_loads` carry no unit
   (S-12 §4), `idea_get_check_results` returns utilization "percentages", and the server defaults the design code to
   `ECEN` (`idea_create_project*`).

The adapter must therefore serve a small, evidenced allowlist, build loads only through the one route on which they
provably reach the calculation, refuse every stub, and mark the rest `NotImplementedGap`, never improvise.

## 2. Reuse research

| Candidate | Finding | Decision |
|---|---|---|
| 0002 framework (allowlist data, build check, error mapping, ledger, reconciliation, `ToolPort`, `HostPort`) | Product-neutral; `single` role topology is allowed (0002 §4.2 rule 2); `--disable-script` already named as required for IDEA (0002 §4.2 rule 3, §4.6.5) | Reused unchanged except the **[added]** items A1 (§11) |
| 0011 Revit adapter (error parser, no `units` tokens, timeout text rules, server section shape) | The closest non-CSI adapter; its attended dialog class does not apply | Followed for structure; nothing shared by copying |
| S-12 inventory (58 tools) and §11 | Gives the classification inputs; its note that `idea_set_loads` covers "set load effects" is incomplete (§1 item 2, C1) | Per-tool table §4.4 |
| Sasaah `idea_native_loads_from_frame_forces` and the joint-bundle tools (`idea_native_create_from_joint`, `_link`, `_sync_from_joint`) | They map ETABS forces to IDEA loading inside Sasaah (axis and sign rules, kN to N, `E/IdeaFrameForces.cs`) | Not adopted: engineering content (S-12 §11, risk R1); the owner may review them as a lead for the load map (§4.7, IG-2) |
| 08 §2 target tools (`set_plate_thickness`, `check_model`, `get_stress_strain_results`, ...) | Not in the server; plate, bolt and weld edits go through the untyped `idea_update_operation` | Gaps IG-3, IG-6; no workaround |
| Python package `ideastatica_connection_api` (08 §1) | Superseded by ADR-0024; the harness calls the Sasaah server | Not used |

## 3. Acceptance criteria

Test paths are relative to `packages/eng-harness/`. "Synthetic IDEA fake" is the test-only MCP server of §4.12 (lead
decision D-5), a real process over stdio; "fake-host workflow test" runs the real engine with the real `ToolPort` and
`HostPort` against it.

### 3.1 Server section, allowlist, build check

- AC1. Given a `harness.toml` with `[servers.idea]` (`adapter = "sasaah-idea-mcp"`, one role `main`, `route`, `service_url`,
  `host_key`, required timeouts), when loaded, then it is accepted; a second role, `--read-only`, `--default-project`,
  a missing `--disable-script` requirement, a `service_url` whose host is not loopback, a missing `route`, or any
  `SASAAH_IDEA_*`, `SASAH_IDEA_*` or `IDEA_*` key in `env` gives a load error naming the field. Tests:
  `tests/unit/servers/test_config.py::test_idea_server_section`, `::test_idea_forbidden_options`,
  `::test_idea_service_url_loopback_only`, `::test_idea_env_keys_refused`,
  `tests/unit/servers/test_launch_args.py::test_idea_argv_has_no_audit_log` (no `--audit-log` is built for this server).
- AC2. Given the allowlist data, when loaded, then exactly the 9 tools marked `serve` in §4.4 are served, each with the
  fields of 0002 AC16 plus `routes`; the 20 `gap` tools, the 28 `not served` tools and `idea_run_script` are refused with
  `INVALID_ARGUMENT` (`field: tool`) and nothing is sent; any name containing `script`, `invoke`, `eval` or
  `tables_apply` is refused at load. Tests: `tests/unit/adapters/test_allowlist.py::test_idea_entries_match_classification`,
  `::test_idea_gap_and_not_served_refused`, `::test_idea_run_script_refused`,
  `tests/contract/test_idea_allowlist.py::test_against_inventory` (the four classes partition the 58 inventory names).
- AC3. Given a started server, when the build check of 0002 §4.3.4 runs with the IDEA items of §4.3, then it passes only
  if the executable hash, the Sasaah commit, the tool-list fingerprint over the 9 served tools, `idea_status.read_only ==
  false` and `idea_status.script_enabled == false` hold; a listed `idea_run_script` or `script_enabled: true` stops the run
  before any write. Tests: `tests/contract/test_idea_allowlist.py::test_fingerprint_from_inventory`,
  `tests/unit/servers/test_buildcheck.py::test_idea_status_flags`,
  `tests/workflow/servers/test_session.py::test_idea_script_enabled_stops_run`, `::test_idea_listed_run_script_stops_run`.

### 3.2 Session, files, routes

- AC4. Given a `.ideaCon` model, when `working_copy` runs, then the file is copied into the run folder (hash before and
  after equal), the model identity is `derived_from` the original (ADR-0032), and every path passed to the server is inside
  the run folder; `out_path` is always a new file distinct from `path`; `confirm: true` is set only under an approval; no
  tool that overwrites its input is served. Tests: `tests/workflow/adapters/test_idea_session_ops.py::test_working_copy_hash`,
  `::test_out_path_new_and_distinct`, `::test_no_path_outside_run_folder`,
  `tests/unit/adapters/test_idea_args.py::test_confirm_only_under_approval`.
- AC5. Given route `rest`, when `idea_open_project` returns anything other than `backend: "rest"` with
  `live_project: true`, or `idea_status.service.reachable` is false, then `HOST_NOT_CONNECTED` is raised before any
  calculation and the project is closed; given route `native`, when the working copy is not a `.ideaCon` the native tools
  accept, or no installed version reports a hidden calculator, then the same code. Tests:
  `tests/workflow/adapters/test_idea_session_ops.py::test_rest_route_requires_live_project`,
  `::test_service_unreachable_host_not_connected`, `::test_native_route_requires_hidden_calculator`.
- AC6. Given a step that creates a project or edits the in-memory model (`idea_create_project`,
  `idea_create_project_from_template`, `idea_set_loads`, and the other tools marked `gap`), then `NotImplementedGap` is
  raised with its gap id (IG-1, IG-3, IG-4) and nothing is sent. Tests:
  `tests/workflow/adapters/test_idea_gaps.py::test_create_project_gap`, `::test_set_loads_gap`,
  `::test_project_model_edits_gap` (parametrized over the `gap` tools).

### 3.3 Loads by reference (route `native`)

- AC7. Given the shipped load map (§4.7) whose signs are unset, when a load step runs, then `NotImplementedGap` (IG-2) is
  raised before any call; given a synthetic confirmed map from the test fixtures, the step proceeds. Tests:
  `tests/unit/adapters/test_idea_loads.py::test_unconfirmed_map_gap`, `::test_synthetic_map_proceeds`.
- AC8. Given a load plan whose entries carry `$ref`s to rows of a `forces.member_end/1` result, when the step runs, then each
  reference resolves through `eng_contract` (kind, pointer, unit, staleness), a literal force is refused
  (`require_refs`), a reference to another kind gives `REF_KIND_MISMATCH`, a stale one `REF_STALE`, forces are converted
  exactly from `kN` and `kN.m` to the load unit of §4.6, and provenance records the references, never the values. Tests:
  `tests/unit/adapters/test_idea_loads.py::test_refs_resolved_converted`, `::test_literal_force_refused`,
  `::test_stale_ref_refused`, `::test_wrong_kind_refused`.
- AC9. Given the loading read by `idea_native_get_loads`, when the adapter builds the new loading, then only the six force
  fields of mapped segments differ from the read loading; a segment not named by the plan, an effect with a non-empty
  `forcesPercentageOnSegments`, a plan entry naming a segment that does not exist, or a member-end row whose member is not
  in the plan's member map is refused with `INVALID_ARGUMENT` (`field`) or `NotImplementedGap` (IG-8) before the write.
  Tests: `tests/unit/adapters/test_idea_loads.py::test_only_force_fields_change`, `::test_unmapped_segment_refused`,
  `::test_percentage_forces_gap`, `::test_unknown_segment_refused`,
  `tests/property/test_idea_loads_props.py::test_structure_preserved`.
- AC10. Given the write, when `idea_native_set_loads` is sent with `out_path` in the run folder, then the model is rebound
  to the new file (new revision, new hash, the old file kept), the read-back (`idea_native_get_loads` on the new file)
  equals the requested forces within the basis field `checks.readback_relative_tolerance`, a mismatch is
  `READBACK_MISMATCH` (error), a reply with a non-empty `dropped_zero` is the warning `LOAD_EFFECT_ZERO_DROPPED` naming the
  effects, and a plan whose every effect is zero is `HOST_ERROR` (`idea_error`) with no new file. Tests:
  `tests/workflow/adapters/test_idea_loads.py::test_set_loads_writes_new_file`, `::test_readback_mismatch_detected`,
  `::test_zero_effect_dropped_warning`, `::test_all_zero_loads_host_error`.

### 3.4 Calculation, stub refusal, verdicts

- AC11. Given any reply of `idea_calculate` or `idea_get_check_results`, when it carries a stub marker (`offline_stub` absent
  or not `false`, `backend` not `"rest"`, a `notice`, or a check whose `unity_check_message` is `"Offline stub."`), then
  the call fails `HOST_ERROR` with `host_code: OFFLINE_STUB`, no verdict is produced and the reply is stored only as
  failure evidence; given `idea_status.service.reachable == false` before the call, then `HOST_NOT_CONNECTED` without
  calling. Tests: `tests/unit/adapters/test_idea_stub.py::test_stub_markers` (parametrized),
  `tests/workflow/adapters/test_idea_calculate.py::test_stub_refused_rest`, `::test_service_stopped_preflight`,
  `::test_live_create_fallback_offline_refused`.
- AC12. Given route `native`, when `idea_native_calculate` runs with `save` false and no `out_path`, then each result row
  becomes verdicts; a non-empty `errors` list gives one verdict `idea:connection` with status `ERROR` and the host text
  (cut to 500 characters) in `assumptions`; a reply of an unexpected shape, or with a stub marker, is `HOST_ERROR`
  (`host_code: UNEXPECTED_REPLY`). Tests: `tests/workflow/adapters/test_idea_calculate.py::test_native_checks_to_verdicts`,
  `::test_native_errors_are_error_verdicts`, `::test_unexpected_shape_host_error`.
- AC13. Given a check row, when mapped (§4.5), then `source` is `host`, `ratio = check_value / 100`, `status` follows
  `check_status`, `skipped` gives `NOT_APPLICABLE`, and any disagreement between `check_status` and `ratio` against
  `ratio_limit` (1.0), a negative or non-finite value, or an unread design code gives `NEEDS_ENGINEER` (non-finite: `ERROR`);
  the adapter never recomputes a status and never changes a host `FAIL` to `PASS`. Hand-derived cases: 87.5 and true gives
  `PASS` (0.875); 103 and true, 80 and false give `NEEDS_ENGINEER`; 112 and false gives `FAIL`; skipped gives
  `NOT_APPLICABLE`. Tests: `tests/golden/test_idea_verdicts.py::test_mapping_cases`,
  `tests/property/test_idea_verdicts_props.py::test_no_status_upgrade`.
- AC14. Given the verdicts of one call, then they form one `verdicts.set/1` whose verdicts are all `source: host`, with
  `counts` matching, `draft: true` while the load map is unconfirmed (and for route `rest` always, §4.5), `governing` on the
  largest-ratio non-skipped verdict per connection (ties all), `trace_ref` null, the raw reply in a parent
  `harness.idea_check_raw/1`; a code-pack verdict in the set is a construction error; a reply with no calculated
  connection gives `PRECONDITION_FAILED` (`analysis_current`), never an empty passing set; a connection `passed` that
  disagrees with its checks adds one `idea:connection` verdict `NEEDS_ENGINEER`. Tests:
  `tests/unit/adapters/test_idea_verdicts.py::test_set_properties`, `::test_host_only`, `::test_empty_is_precondition`,
  `::test_passed_disagreement`.
- AC15. Given the design basis field `connection.design_code`, when verdicts are built, then `code` is its value; the host's
  own code setting is never read on route `rest` (IG-5), so its verdicts say so in `assumptions` and are `draft`; if the
  field is missing or unconfirmed the step fails before any write (`design_basis.missing`, contract §4.10.2). The adapter
  never passes a design code it did not receive and never relies on the server default `ECEN`. Tests:
  `tests/unit/adapters/test_idea_args.py::test_design_code_from_basis_only`,
  `tests/unit/adapters/test_idea_verdicts.py::test_code_label_and_assumptions`.

### 3.5 Units

- AC16. Given the allowlist header, then it declares for the native loads `N` and `N.m` with status `declared` (from the
  tool descriptions) and for `idea_set_loads` no unit with status `missing`; stored read-back loads are converted to
  `kN` and `kN.m` through `eng_contract.units`; `check_value` is read as a percentage (division by 100, the definition
  of percent) and recorded with status `declared`; the run report says "unit declared by the tool, not confirmed by a live
  run" until L2 and L6 are recorded. Tests: `tests/unit/adapters/test_idea_units.py::test_declared_units_and_status`,
  `::test_read_back_loads_canonical`, `tests/contract/test_idea_allowlist.py::test_unit_header`.

### 3.6 Errors, timeouts, licensing

- AC17. Given each Sasaah code of §4.8, then the contract code, `retryable`, `host_code`, `host_method` and precondition are as
  tabled; a text with no code is `INTERNAL` with an `incident_id`. Test:
  `tests/unit/adapters/test_idea_errors.py::test_mapping_table` (parametrized over the table).
- AC18. Given a `timeout` on a read, then `TIMEOUT_NO_EFFECT`; on `idea_calculate` or `idea_native_set_loads`, then
  `TIMEOUT_UNKNOWN_OUTCOME` with the `op_id`, the host is wedged and the epoch increases; reconciling
  `idea_native_set_loads` answers `applied` when the `out_path` file exists and reads back as requested, `not_applied` when
  it does not exist, else `unknown`; reconciling `idea_calculate` always answers `unknown` and the adapter re-runs nothing.
  Tests: `tests/unit/adapters/test_idea_timeouts.py::test_timeout_mapping`,
  `tests/workflow/adapters/test_idea_reconcile.py::test_set_loads_outcomes`, `::test_calculate_unknown_no_rerun`.
- AC19. Given a service or calculator that cannot get a license seat (synthetic faults `license_refused`, `license_hang`),
  then a refusal arrives as `HOST_NOT_CONNECTED` (`service_unavailable`) or `HOST_ERROR` with the host text, a hang ends at
  the server's `timeout` or the client backstop as in AC18, the run stops with a message naming the license as a possible
  cause, and no call waits beyond `call_timeout_s + client_grace_s`. Tests:
  `tests/workflow/adapters/test_idea_license.py::test_refusal_maps`, `::test_hang_bounded`.

### 3.7 End to end, recordings, doctor

- AC20. Given a test block that copies a `.ideaCon`, reads its loading, writes loads from `forces.member_end/1` references,
  calculates and reads host verdicts (route `native`), and a second block that opens, lists, calculates and reads (route
  `rest`), then the journal holds every step and only the files of the run exist; when the engine is killed at each write
  step and resumed, it reconciles and completes without a repeated write. Tests:
  `tests/workflow/test_idea_cycle.py::test_native_cycle_steps`, `::test_rest_cycle_steps`,
  `tests/replay/test_idea_resume.py::test_crash_matrix`.
- AC21. Given IDEA recordings, the adapter's contract tests pass on them and the synthetic fake gives the same reply shapes
  and error codes for every recorded operation; the fake's tool schemas equal the S-12 inventory. Tests:
  `tests/contract/test_idea_recordings.py::test_adapter_on_recordings`, `::test_synthetic_matches_recordings` (skip with
  reason when none exists), `tests/contract/test_idea_allowlist.py::test_fake_schemas_match_inventory`,
  `tests/unit/test_package_contents.py::test_idea_fake_not_shipped`.
- AC22. Given `eng-harness doctor`, then it prints the pinned build facts, `idea_status` (installed versions, service
  state, `read_only`, `script_enabled`), the route's prerequisites, the Sasaah default timeout (120 s) for comparison, and
  warns that the single role's `call_timeout_s` also bounds every read. Test:
  `tests/unit/test_doctor.py::test_idea_section`.

## 4. Design

### 4.1 Package layout

`packages/eng-harness/src/eng_harness/adapters/idea/`: `_allowlist.toml`, `_tools.py` (argument models and builders),
`_replies.py`, `_stub.py`, `_verdicts.py`, `_errors.py`, `_loads.py`, `_load_map.toml`, `_gaps.py`, `_session_ops.py`,
`_reconcile.py`, `_checks.py`; the kinds are `eng_harness/kinds/idea.py`. Shared modules (`adapters/_*.py`) are used as 0002
§4.1 lists; no shared module names IDEA.

### 4.2 `harness.toml`: the IDEA server section

```toml
[servers.idea]
adapter = "sasaah-idea-mcp"
command = "<absolute path to sasaah-idea-mcp.exe>"
route = "native"                       # "native" (loads by file, hidden calculator) or "rest" (check as is, REST service)
service_url = "http://127.0.0.1:<port>"  # loopback only; required for route "rest", used by the server's heartbeat probe
idea_dir = "<optional absolute install folder>"
client_grace_s = <required>
max_restarts_per_run = 1
shutdown_grace_s = 10
build = { sasaah_commit = "<40 hex>", exe_sha256 = "<64 hex>" }
host_key = "idea"
audit_log = false                      # [added] the IDEA server has no --audit-log option (S/IdeaServerConfig.cs)

[servers.idea.roles.main]              # one role: the server process holds the open project (§1 item 4)
classes = ["session", "call", "long"]
call_timeout_s = <required>            # passed as --call-timeout-sec (Sasaah default 120 s, S/IdeaServerConfig.cs:13)

[host_programs.idea]
executables = ["IdeaStatiCa.ConnectionRestApi.exe"]   # to recognise the service among processes; the harness never starts it
```

Rules (in addition to 0002 §4.2): (1) no timeout has a default; the one `call_timeout_s` also bounds the hidden-calculator
process, which the server kills with its tree when the budget ends (`E/HiddenCalcProcess.cs:23-80`), and the REST client
timeout (`E/IdeaRestClient.cs:42-50`); it must exceed the longest expected calculation (sized by S-08), and the doctor warns
that every read then waits as long. (2) **Required start options**, passed by the adapter: `--disable-script`,
`--call-timeout-sec`. (3) **Permitted, from the section**: `--idea-dir` (absolute) and `--service-url` (loopback). (4)
**Forbidden**: `--read-only` (it hides the write tools the route needs; the allowlist is the filter), `--default-project`,
any other argument (the server ignores unknown arguments with a warning, `S/IdeaServerConfig.cs:64`, so a typo would
pass silently), and any `SASAAH_IDEA_*`, `SASAH_IDEA_*`, `IDEA_*` variable (the three aliases of each option,
`E/IdeaModels.cs:441-452`; the adapter sets the timeout by argument only). (5) The harness starts neither the REST
service nor IDEA; the engineer does. Route `rest` needs the service running; route `native` needs the hidden calculator of
an installed version. (6) The server writes diagnostics to stderr only; the harness stores them in `run_dir/servers/`.

### 4.3 Build check (extends 0002 §4.3.4)

(1) SHA-256 of `command` equals `build.exe_sha256`; (2) `server_info` recorded; (3) `sasaah_commit` equals the allowlist's;
(4) the tool-list fingerprint over the 9 served tools equals the allowlist's, every served tool is listed, and a listed
`idea_run_script` fails the check (`--disable-script` hides it, `E/IdeaToolCatalog.cs:516-522`); (5) `idea_status.read_only`
is false and `script_enabled` is false (`E/IdeaToolService.cs:365-395`); (6) `idea_status` is recorded in provenance:
`installed[].version`, `installed[].has_rest_api`, `service.reachable`, `service.service_version` (paths in replies
are reduced to base names before storage). There is no server build id (S12-G1); the executable hash and the pinned
commit stand in for it. `ServerCheck.build` is `"<commit[:12]>+<exe sha256[:12]>"`.

### 4.4 Allowlist (the 58 tools)

`routes` is `rest`, `native` or both. `effect` and `action` are as 0002 §4.5.1. All served tools have `units = none`
(the server has no unit switching, S-12 §4) and `confirm` as tabled.

**Served (9)**

| Tool | Routes | Kind | Class | Effect, action | Confirm | Result kind | Read-back |
|---|---|---|---|---|---|---|---|
| `idea_status` | both | session | session | read, plain | never | `harness.idea_status/1` | n/a |
| `idea_open_project` | rest | session | call | write, `open` | never | `harness.idea_project/1` | `idea_list_connections` |
| `idea_close_project` | rest | session | call | write, plain | never | `harness.idea_project/1` | n/a |
| `idea_list_connections` | rest | read | call | read, plain | never | `harness.idea_project/1` | n/a |
| `idea_calculate` | rest | analysis | long | write, `analysis` | approved | `verdicts.set/1` (parent `harness.idea_check_raw/1`) | n/a |
| `idea_get_check_results` | rest | read | call | read, plain | never | `verdicts.set/1` (same) | n/a |
| `idea_native_get_loads` | native | read | call | read, plain | never | `harness.idea_loads/1` | n/a |
| `idea_native_set_loads` | native | write | call | write, plain | approved | `harness.idea_loads/1` | `idea_native_get_loads` |
| `idea_native_calculate` | native | analysis | long | read, `analysis` | never (`save` always false) | `verdicts.set/1` (same) | n/a |

`idea_native_calculate` is annotated read-only by the server and writes only when `save` is true (S-12 §8); the argument
model has no `save` and no `out_path`, and the builder sets `save: false`. `idea_calculate` always passes `connection_ids`
(omitting it calculates every connection). `idea_native_set_loads` is one of the tools S-12 §8 allows only with
conditions: its `loads` are built only by the adapter, from the loading it just read, with the structure preserved (AC9),
and read back (AC10).

**Gap (20)**: the project-model edits whose result never reaches a real calculation (IG-3): `idea_create_connection`,
`idea_set_members`, `idea_add_plate`, `idea_add_bolt_group`, `idea_add_weld`, `idea_add_cut`, `idea_add_stiffener`,
`idea_update_operation`, `idea_delete_operation`, `idea_duplicate_connection`, `idea_rename_connection`,
`idea_delete_connection`, `idea_add_load_case`, `idea_set_load_combinations`, `idea_set_project_settings`,
`idea_add_material`, `idea_add_section`; `idea_set_loads` (IG-1 and IG-3); `idea_create_project` and
`idea_create_project_from_template` (IG-4).

**Not served (28)**: project family: `idea_save_project`, `idea_export_iom`, `idea_import_iom`, `idea_export_report`,
`idea_list_templates`, `idea_list_materials_sections`, `idea_get_connection_stiffness` (not needed, or overwrite
semantics), and `idea_get_connection`, `idea_get_model_info`, `idea_get_project_settings`, `idea_list_operations` (they
read Sasaah's in-memory model, which on route `rest` holds defaults, IG-5). Native family: `idea_native_info` (reply shape
unknown until L3), `idea_native_split_pass_fail`, `idea_native_export_template`, `idea_native_export_iom`,
`idea_native_apply_template`, `idea_native_apply_simple_template`, `idea_native_delete_operations`,
`idea_native_create_from_iom` (file edits beyond this workflow), `idea_native_code_setup`, `idea_native_libraries`,
`idea_native_set_design_subcode`, `idea_native_fix_library_links` (merge-update of arbitrary fields, library or code
changes: engineering choices and the untyped-merge condition of S-12 §8), and `idea_native_loads_from_frame_forces`,
`idea_native_create_from_joint`, `idea_native_link`, `idea_native_sync_from_joint`, `idea_native_link_info` (ETABS to
IDEA mapping inside Sasaah, not adopted, IG-2).

**Excluded (1)**: `idea_run_script` (compiles and runs C#; deny list of 0002 §4.5.1; enabled by default on the server,
hence `--disable-script`).

`tests/contract/test_idea_allowlist.py::test_against_inventory` checks the four lists and the served table against
`inventory/sasaah-idea-mcp.json` (9 + 20 + 28 + 1 = 58).

### 4.5 Replies, kinds, verdicts

The server sends one JSON text block (`isError: true` and `{code, message, data}` on failure, `S/Program.cs:90-110`). Replies
are parsed with `eng_contract.mcp.extract_raw_reply` and stored as in 0002 §4.5.3. Harness kinds (`eng_harness/kinds/idea.py`,
all `extra="forbid"`, versioned `/1`):

| Kind | Payload |
|---|---|
| `harness.idea_status/1` | `installed`: list of `{version, has_rest_api, hidden_calculator: bool}`; `service`: `{reachable, service_version}`; `read_only`, `script_enabled`: bool |
| `harness.idea_project/1` | `backend`, `service_reachable`, `live_project`: from the reply; `connections`: list of `{id: int, name, calculated: bool}`; no paths |
| `harness.idea_loads/1` | `connection`: str; `effects`: list of `{id, name, check_equilibrium: bool, segments: list of {beam_segment_id: int, position_host: float, N_kN, Qy_kN, Qz_kN, Mx_kNm, My_kNm, Mz_kNm}}`; `position_host` is opaque (IG-9); `percentage_segments_present: bool`; `file_sha256` |
| `harness.idea_check_raw/1` | `route`; `backend` (or null on route `native`); `offline_stub: false`; `connections`: list of `{connection_id (str or int), name, passed: bool, calculated: bool, checks: list of {name, check_value (host percent), check_status, skipped, message, load_case_id}, errors: list of str, warnings: list of str}` |
| `verdicts.set/1` | neutral kind (contract §4.10.2) with the mapping below |

Message texts are cut to 500 characters; absolute paths are reduced to base names (A11).

**Verdict mapping** (pure function `_verdicts.py`, a protected-path engineering mapping reviewed by the owner):

- `source = host`; `check_id = "idea:" + slug(name)` (lower case, characters outside `[a-z0-9_.-]` replaced by `_`, `check` when
  empty); `code` = the design basis field `connection.design_code` (AC15); `clause = null`; `subject = {kind: joint, id:
  <connection name>, station_mm: null, case: <load_case_id or null>}`; `demand = capacity = null` (IDEA reports a
  utilization only); `trace_ref = null`; `ratio_limit` is the contract default.
- `ratio = check_value / 100` (the tool describes `check_value` as a utilization percentage; status `declared`, L6).
- `status`: `skipped` gives `NOT_APPLICABLE`; otherwise the host's `check_status` gives `PASS` (true) or `FAIL` (false)
  **only if** it is consistent with the contract rule (`PASS` needs `ratio <= ratio_limit`, `FAIL` needs `ratio >
  ratio_limit`); otherwise `NEEDS_ENGINEER` with the disagreement in `assumptions`. A negative `check_value`, a missing
  one, or an unread design code gives `NEEDS_ENGINEER`; a non-finite one gives `ERROR`.
- `assumptions` always carry: "host-native check of IDEA StatiCa; not merged with code-pack verdicts"; on route `rest`
  also "design code declared in the design basis, not read from the host" and "loads as stored in the opened file".
- `draft = true` while `_load_map.toml` is unconfirmed and always on route `rest` until IG-5 is closed **[added]**: the
  verdicts are watermarked in the run report (10 §4).
- Agreement with future code packs is a verification activity, never a runtime merge (08 §3).

### 4.6 Units

IDEA has no unit state to read or restore; `read_units` returns the fixed declaration and never fails. Declared units
(allowlist header, status `declared`, from the Sasaah tool descriptions, S-12 §4): loads of `idea_native_*` in `N` and
`N.m` (`idea_native_get_loads`, `idea_native_set_loads`); `check_value` as a percentage; lengths in `_mm` and angles in `_deg`
(not used here). `idea_set_loads` forces have no declared unit (S12-G12): that tool is not served (IG-1). The adapter
converts canonical `kN` to `N` and `kN.m` to `N.m` with `eng_contract.units.convert` (exact factors, contract §4.7) and
back for stored read-back. A unit mismatch found by L2 changes one allowlist header value by a reviewed pull request, not
code.

### 4.7 Loads by reference: the plan, the map, the builder

**Load plan** (argument model of `idea_native_set_loads`): `path` (a working copy), `connection` (explicit identifier or
name as the host reports it; never defaulted), `effects`: list of `{name, entries}`, each entry `{beam_segment_id,
position_host, row: Ref[MemberEndRow]}`. `row` points to one row object of a `forces.member_end/1` result
(`res_<id>#/rows/<n>`); the six force fields are `engineering_quantity`, so a literal is refused (contract AC42). Choosing
the members of a joint, the cases and combinations, and the pairing of ETABS member ends with IDEA segments is the
workflow's calc and the engineer's approved map (08 §4), not this adapter.

**Load map** (`_load_map.toml`, protected path, engineering content, **draft**): for each IDEA component `n`, `qy`, `qz`,
`mx`, `my`, `mz` the CSI field it takes (`P_kN`, `V2_kN`, `V3_kN`, `T_kNm`, `M2_kNm`, `M3_kNm`, per
`sign_convention: "host_local/1"`, contract G-3) and a `sign` (+1 or -1) for member end `i` and for `j`. **Every sign ships
unset** and the file's `status` is `unconfirmed`; the adapter raises `NotImplementedGap` IG-2 until the owner commits
confirmed values (with the confirming reference case) through a reviewed pull request. No sign, axis or end rule is guessed
and none is copied from Sasaah. Tests use a synthetic map in `tests/fixtures/idea/` whose header says "synthetic test
values, not engineering".

**Builder** (`_loads.py`): read the current loading with `idea_native_get_loads`; for each plan entry, find the effect by
`name` and the segment by exact equality of `beam_segment_id` and `position_host` (no tolerance, so no engineering
number); replace the six force fields from the resolved row through the map and the unit conversion; leave every other
field untouched; send `idea_native_set_loads(path, loads, connection_id, out_path, confirm)` under an approval; read back.
Sasaah drops all-zero effects before the write (`E/IdeaNativeDigest.cs:8-52`) and reports them (`dropped_zero`); the
adapter turns that into AC10's warning. The effect `name` is the only link between the plan and the host; effects named
twice are refused.

### 4.8 Errors and timeouts

The server code is in `data.code` of the error JSON (S-12 §6, `E/IdeaErrors.cs:31-41`); a text with no code is the
"unexpected error" row.

| Sasaah code | Contract code | Rule |
|---|---|---|
| `no_project` | `PRECONDITION_FAILED` (`model_open`) | route `rest`: the server was restarted; reopen |
| `connection_not_found` | `NOT_FOUND` (`field: connection`) | |
| `service_unavailable` | `HOST_NOT_CONNECTED` | also the form of a refused license or a refused request (§4.9); retry `always`, bounded by the engine's attempt limit |
| `unsupported_by_version`, `api_not_available` | `NOT_SUPPORTED_BY_VERSION` | the service serves none of the API versions (24.1 and newer) |
| `timeout` | read or `native_calculate`: `TIMEOUT_NO_EFFECT`; `idea_calculate`, `idea_native_set_loads`: `TIMEOUT_UNKNOWN_OUTCOME` | the server does not cancel the REST work (S-12 §5, `E/IdeaSession.cs:85-104`); host wedged, epoch increases; the hidden calculator tree is killed by the server, so `native_calculate` left nothing behind |
| `iom_error`, `idea_error` | `HOST_ERROR`, `host_code` the Sasaah code, `host_method` the tool, `retryable: false` | `idea_error` also carries plain argument errors, which the validated arguments should exclude |
| `confirmation_required` | `CONFIRMATION_REQUIRED` | an adapter bug: `confirm` is set only under approval |
| `read_only`, `script_disabled` | `INTERNAL` | a configuration or allowlist bug |
| no code ("The server encountered an unexpected error...", `S/Program.cs:105`) | read: `INTERNAL` with an `incident_id`; write or analysis: `TIMEOUT_UNKNOWN_OUTCOME` | |

After a client backstop the role is restarted (0002 §4.5.6); the restart loses the open project, so route `rest` reopens
the working copy and runs `idea_list_connections` before the next call. Reconciliation (AC18): `idea_native_set_loads` writes a **new file** through a temporary
file and a validated move (`E/IdeaHiddenCalcClient.cs:247-295`), so the state is decidable by the file and its read-back;
`idea_calculate` has no readable state after a timeout (the result is stored in memory only after the call returns,
`E/IdeaSession.cs:1058-1086`), so `unknown`, and a re-run is the engineer's explicit decision after the service is idle.

### 4.9 Licensing (S-08 question, 08 §5)

Sasaah has no license logic (no seat, no activation) in the engine or the server; whatever the REST service or the hidden
calculator does without a seat reaches the harness as: an HTTP refusal (`service_unavailable`, `E/IdeaRestClient.cs:158-185`),
kernel `errors` in a native reply, a process budget that ends (`timeout`), or a hang until `timeout`. The adapter's
rule: **never wait beyond `call_timeout_s + client_grace_s`; never treat the absence of a verdict as a pass.** A refusal is
`HOST_NOT_CONNECTED` or `HOST_ERROR`; a hang cannot be told from a long calculation, so it is `TIMEOUT_UNKNOWN_OUTCOME` for
calculations (Q8). The host's texts are stored verbatim as failure evidence and the run message names "license seat" as a
possible cause when the text contains `licen` or `seat`, as a hint only. The real behavior is L7.

### 4.10 Ports (extends 0002 §4.5.9)

| Port method | IDEA implementation |
|---|---|
| `preflight` | §4.3 |
| `acquire`, `release` | lock key `idea:<hash of service_url>` on route `rest` (the service and its project are shared), `idea:<hash of working copy path>` on route `native` |
| `session_epoch` | increased on timeout, crash, restart, reconnect |
| `locate`, `model_state` | route `native`: the bound file if it exists and its hash equals the journaled hash; route `rest`: the open project if `idea_list_connections` answers and `file_path` equals the working copy |
| `working_copy` | AC4; no host instance is launched |
| `check_model` | the read-back of §4.7 plus integrity checks that need no tolerance: `LOADS_UNCONFIRMED_MAP` (info, load map unconfirmed), `LOAD_EFFECT_ZERO_DROPPED` (warning), `READBACK_MISMATCH`, `READBACK_UNAVAILABLE`; IDEA's own `check_model` does not exist (IG-6) |
| `read_units` | §4.6 |
| `save` | no host call: `SavedModel` of the bound file (hash); every write already produced a file |
| `restore` | rebind to an earlier journaled file whose hash equals `saved.file_sha256`, else `CONFLICT`; on route `rest` close and reopen |
| `model_files` | the bound file; file-copy promotion is possible because no host holds the file open on route `native` (route `rest`: the engineer closes the project in IDEA first, L10) |
| `started_instances`, `close_started` | empty; the harness never starts IDEA or the service |
| `describe`, `call`, `preview`, `read_back`, `supports_reconcile`, `reconcile` | §4.4, §4.7, §4.8; `preview` shows the plan, the map and the forces to be written, in canonical units |

### 4.11 Permission modes

Every write produces a new file in the run folder, so `work_on_copy` and `approve_each_write` both hold and the original
is never touched; promotion by file copy is the engine's (11 §7). `idea_native_set_loads` and `idea_calculate` are
approved steps (the loads change what IDEA checks; a calculation is the long, unreliable call).

### 4.12 Synthetic IDEA fake and recordings

A test-only MCP server in `tests/fakes/sasaah_idea/` (D-5), built from the inventory schemas of the 9 served tools and
`idea_run_script` (listed or hidden by a switch): a `.ideaCon`-like file with connections, effects and segments (invented
numbers), `idea_native_get_loads`/`_set_loads` through a temp file and move, native and REST calculations returning checks
with a deterministic rule that is **not** engineering (documented in the fake), and the stub reply of the real server when
the service is "stopped". Faults, selected by the test: `service_stopped` (stub reply), `live_create_fallback`,
`license_refused`, `license_hang`, `timeout_calculate`, `timeout_set_loads` (file written or not, reply lost),
`unexpected_shape`, `errors_in_reply`, `all_zero_loads`, `passed_disagrees`, `script_enabled`, `read_only_listed_wrong`,
`zero_connections_calculated`. Record mode (0002 §4.8.1) gets an IDEA scenario that drops paths and names.

## 5. Inputs and outputs

| Name | Type | Unit | Bounds | Ref-capable | Source |
|---|---|---|---|---|---|
| `row` forces of a load entry (`P_kN`, `V2_kN`, `V3_kN`, `T_kNm`, `M2_kNm`, `M3_kNm`) | float | kN, kN.m | finite | yes, engineering quantity | `forces.member_end/1` result |
| `beam_segment_id`, `position_host` | int, float | host (opaque) | exact match | no | engineer-approved map from the workflow |
| `connection` | str | | non-empty | no | workflow |
| `design_code` | str | | 1 to 100 | basis field `connection.design_code` | design basis (13 §2), no default |
| `checks.readback_relative_tolerance` | float | 1 | > 0 | basis field | design basis (0002 G-2) |
| `call_timeout_s`, `client_grace_s` | int | s | >= 1 | no | `harness.toml`, required |
| Outputs | envelopes of the kinds of §4.5 | canonical | | | adapter |

## 6. Errors

| Condition | Code | Fields |
|---|---|---|
| Tool not allowlisted; unmapped or unknown segment; unnamed effect; duplicate effect name; design code missing | `INVALID_ARGUMENT` | `field` |
| Literal for an engineering quantity; reference errors | contract §5 codes | `field` |
| Service unreachable; route prerequisites missing; REST project not live | `HOST_NOT_CONNECTED` | message |
| No current calculation | `PRECONDITION_FAILED` (`analysis_current`) | message |
| Stub reply; unexpected reply shape | `HOST_ERROR` (`OFFLINE_STUB`, `UNEXPECTED_REPLY`) | `host_method` |
| Read-back mismatch | issue `READBACK_MISMATCH` (error) via `check_model` | |
| Load unit, load map, in-memory edits, creation, percentage forces | `NotImplementedGap` (`NOT_IMPLEMENTED`) | gap id |
| Server and IDEA errors, timeouts | §4.8 | as tabled |
| Build, fingerprint, option mismatch | `ServerCheck.ok` false, engine `SERVER_CHECK_FAILED` | `reason` |

## 7. Non-goals

- Any IDEA server, REST client or add-in change (ADR-0024); fakes under `tests/` are test doubles only.
- Scripts, `idea_run_script`, code setup merges, library edits, design-subcode changes, or any escape hatch, including as
  a workaround for a gap.
- Creating or editing connections (members, plates, bolts, welds, cuts, stiffeners, operations, materials, sections,
  project settings, load cases, combinations) in IDEA; reports, IOM exchange, stiffness, stress-strain results.
- Selecting the members of a joint, the cases and combinations, and pairing ETABS ends with IDEA segments (workflow calcs,
  08 §4); the ETABS-to-IDEA mapping inside Sasaah (IG-2); the sign and axis rules (owner).
- Starting or stopping the REST service or IDEA; installing or licensing IDEA; versions other than those tested (L1).
- Interpreting IDEA's checks, merging them with code-pack verdicts, or recomputing a host status.

## 8. Risks

| Risk | Class | Mitigation |
|---|---|---|
| A stub or a stale result is read as an IDEA verdict | R1 | Stub markers refused (AC11); route `rest` preflight; empty or uncalculated results are a precondition failure (AC14); every reply shape-checked (AC12); L8 |
| Loads sent in the wrong unit, axis or sign, or to the wrong segment | R1 | Declared unit with status in the report (AC16); map unconfirmed means gap (AC7); exact segment match, structure-preserving build, read-back (AC9, AC10); L2, L9 |
| Edits believed applied but not part of the calculation | R1 | In-memory edit tools not served (AC6); loads only through a file the calculator reads; L4 |
| Verdict relabelled or recomputed by the adapter | R1 | Host status wins; disagreement is `NEEDS_ENGINEER`; property test of no upgrade (AC13) |
| Design code wrong or defaulted | R1 | Taken from the basis only (AC15); server default never used |
| A hang on a missing license seat blocks the run | R2 | Backstop and server timeout (AC18, AC19); doctor warning; L7 |
| Scripts left enabled | R1 | Required `--disable-script`, status check, fingerprint (AC1, AC3) |
| A calculation re-run while the abandoned one still runs | R2 | `unknown`, no adapter re-run, engineer decision (AC18) |
| Sasaah behavior changes behind an unchanged schema | R2 | Pinned commit and executable hash; L1 |

## 9. Test strategy

| Criteria | Layer | Location |
|---|---|---|
| AC1, AC2, AC4 (args), AC7 to AC9, AC11 (markers), AC14, AC15, AC16, AC17, AC18 (mapping), AC22 | Unit | `tests/unit/` |
| AC2, AC3, AC16 (header), AC21 | Contract (inventory, fake schemas, recordings; markers `synthetic`, `recorded`) | `tests/contract/` |
| AC3, AC4, AC5, AC6, AC10 to AC12, AC18, AC19, AC20 | Fake-host workflow (real engine, real fake process) | `tests/workflow/` |
| AC20 | Replay (crash matrix) | `tests/replay/` |
| AC13 | Golden (hand-derived, synthetic reply rows) | `tests/golden/` |
| AC9, AC13 | Property (Hypothesis, derandomized in CI) | `tests/property/` |

Coverage floors 85% line and 75% branch (process/05 §2); mutation testing on `adapters/idea/_errors.py`, `_stub.py`,
`_verdicts.py`, `_loads.py` and `_reconcile.py` (R1). `_verdicts.py` and `_load_map.toml` are engineering content: they stay
draft for the owner and are not run on real projects until confirmed.

## 10. Version impact

Part of `eng-harness` 0.1.0. New harness kinds and the IDEA allowlist (with its pinned Sasaah commit and fingerprint) are
versioned with the package; a new Sasaah build is a new allowlist header and new recordings in a minor release. Changes to
0002 (A1 in §11: `routes` on allowlist entries, `audit_log` on the server section, a `single` role serving `long`) need an
amendment of 0002; plan T1 carries them.

## 11. Open questions, gaps and additions

| Id | Question or gap | Owner | Recommendation |
|---|---|---|---|
| Q1 | Route for loads: the file route (native, hidden calculator, tools described as 21.x) is the only one where loads provably reach the calculation; the REST route can only check a project as it is | Owner | Accept the two routes as specified; ask Sasaah (project lane, ADR-0026) for a typed tool that sends loads to the REST service, then serve it on route `rest` (plan T9, blocked) |
| Q2 | One server role (the process holds the project) instead of `main` and `long` | Owner | Accept; the doctor warns about the shared timeout |
| Q3 | Host status wins; a disagreement with `ratio` against 1.0 is `NEEDS_ENGINEER` | Owner | Accept: never recompute, never relabel |
| Q4 | `check_value` read as percent | Owner | Accept as `declared`; confirm at L6 |
| Q5 | Verdicts are `draft` while the load map is unconfirmed, and on route `rest` always | Owner | Accept; lift when IG-2 and IG-5 close |
| Q6 | `idea_native_set_loads` served under the S-12 §8 conditions (adapter-built, structure-preserving, read back) | Owner | Accept; otherwise the route has no way to load |
| Q7 | Design code in verdicts comes from the design basis, not from the host | Owner | Accept; add a host read when a served tool reports the project's real code |
| Q8 | A license hang is `TIMEOUT_UNKNOWN_OUTCOME`, not `HOST_NOT_CONNECTED` | Owner | Accept: a hang cannot be told from a long calculation; revisit after L7 |
| Q9 | "Create a connection project" means: copy an engineer-prepared `.ideaCon` (working copy); creation through the server is IG-4 | Owner | Accept; a template `.ideaCon` is the engineer's input |
| Q10 | The engineer starts the REST service and IDEA; the harness does not (08 §1 said the server would) | Owner | Accept (A9, 16 §5); the doctor reports the state |
| Q11 | The load map (signs per component and member end) and its confirming case are engineering content | Owner | Owner commits the confirmed map after L9; the build ships it unset |
| IG-1 | `idea_set_loads` forces have no unit (S12-G12) | Owner | Not served; ask Sasaah for a unit field; L2 |
| IG-2 | ETABS to IDEA axis, sign and member-end mapping unconfirmed (contract G-3) | Owner | `_load_map.toml` unset, `NotImplementedGap`; Q11 |
| IG-3 | In-memory edit tools do not reach a real calculation (§1 item 2) | Owner | Not served; L4 confirms; Sasaah change (Q1) |
| IG-4 | Project creation through the server leaves the connection in memory only | Owner | Not served; Q9 |
| IG-5 | Reads of the opened REST project are Sasaah defaults (design code `ECEN`, no members) | Owner | Not served; verdicts on route `rest` are `draft` and say so |
| IG-6 | No `check_model` and no `get_stress_strain_results` (08 §2; S12-G12) | Owner | `check_model` is the adapter's read-back and integrity set; stress-strain is out of scope |
| IG-7 | No server build id (S12-G1); `service_version` exists on the service | Owner | Hash and commit pin; record `service_version` |
| IG-8 | Effects with `forcesPercentageOnSegments` are not supported | Owner | `NotImplementedGap`; extend after L3 shows their meaning |
| IG-9 | The meaning of `position` and `beamSegmentId` in the loading JSON | Owner | Opaque keys matched exactly; L3 and the workflow's map decide |
| C1 | **Addition to S-12 §11:** `idea_set_loads` is present but its result never reaches a real calculation; an opened REST project holds defaults; creation leaves content in memory | Owner | Amend S-12 §11 and the inventory notes in a spikes change; this spec follows the source |
| C2 | Conflict: 08 §1 and §2 describe a Python server with typed tools, `check_model` and a service it starts | Owner | ADR-0024 makes 08 a target; this spec follows Sasaah |
| A1 | **[added]** `routes` field on allowlist entries; `audit_log` on the server section (false for IDEA, so no `--audit-log` argument); a `single` role serving `session`, `call` and `long`; allowlist header `unit_status` entries; harness kinds of §4.5; issue codes `LOADS_UNCONFIRMED_MAP`, `LOAD_EFFECT_ZERO_DROPPED`; host codes `OFFLINE_STUB`, `UNEXPECTED_REPLY` | Owner | Accept with this spec |

## 12. Needs local test

Spike S-08 (readiness of `sasaah-idea-mcp`: coverage and licensing behavior) is entirely a local test. No CI job runs IDEA.
The plan writes the steps into `docs/local-testing.md` and a record script under `acceptance/scripts/`; the owner runs
them on a copy of a connection project, in an attended session:

L1 the live `tools/list` against the allowlist fingerprint, `idea_status` per installed version (`has_rest_api`,
hidden calculator present, `service_version`), `script_enabled`, which of the two routes each installed version offers;
L2 the unit of loads: a known load written through `idea_native_set_loads`, read back, and compared with the same
effect in IDEA's own interface and with `idea_set_loads` plus an IOM export (evidence for IG-1); L3 the shapes of
`idea_native_get_loads` and `idea_native_calculate` replies (checks, errors, warnings, digest), the effect and segment
fields, `forcesPercentageOnSegments`, the meaning of `position` and `beamSegmentId`; L4 whether in-memory edits reach a
calculation on either route (set a load, calculate, compare with the file route; IG-3); L5 timeouts: a calculation longer
than `call_timeout_s` (does the service keep running, what the next call sees, process cleanup of the hidden calculator),
a timed-out `idea_native_set_loads` (file written or not); L6 `check_value` scale against `check_status`, `skipped`,
multi-case results, limits other than 100 percent; L7 licensing: no seat for the REST service and for the hidden
calculator, the error text, the time to fail, any hang; L8 the stub: service stopped, failed live creation, the exact
markers; L9 the load map: the owner's reference connection with a hand-verifiable load, to confirm the component, sign
and end rules (Q11); L10 route `rest` file handling: whether the service keeps the uploaded file open, whether the
engineer's close is needed before promotion; L11 repeated open and close of the same file in one server process.
