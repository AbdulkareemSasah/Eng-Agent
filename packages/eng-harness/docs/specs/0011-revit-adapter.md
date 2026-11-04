---
id: spec-0011-revit-adapter
issue: "B-080"
status: draft        # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1]
---

# Spec 0011: eng-harness, the `sasaah-revit-mcp` adapter (column workflow scope)

Package: `eng-harness` (import package `eng_harness`) · Author: agent identity (bootstrap mode,
[ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §4) · Date: 2026-11-04

This spec adds the adapter for `sasaah-revit-mcp` to the framework of [spec 0002](0002-servers-and-adapters.md) ("0002
§n"), for phase 3 ([19](../../../../design/docs/architecture/19-roadmap-and-spikes.md) §1) and the column workflow
(separate spec). It follows [ADR-0024](../../../../design/docs/adr/0024-harness-on-existing-sasaah-servers.md): the
harness is a client of the Sasaah server and add-in; no Revit server is built, and the target of
[07](../../../../design/docs/architecture/07-revit-agent-bridge.md) (typed tools, `$ref` inputs, dry runs, `reconcile_operation`,
a journal of `op_id`s, `check_model`, a stamped identity) is **not met by the server and is not built**. Tool facts come
from the [S-12 report](../../../../spikes/S-12-sasaah-tool-inventory/REPORT.md) §10 ("S-12 §n") and
`inventory/sasaah-revit-mcp.json` (258 entries) at Sasaah commit `61da80f61a6562c8e3553168056bc107e3f93013`, and from a
read-only reading of the Sasaah sources at that commit that S-12 did not cover (handlers, the destructive-call gate, the
request queue, specs 008 and 009). In this document, `A/` is `04_Deployments/Sasaah.Agent.Revit.Bridge/Handlers/`, `E/`
is `02_Engines/Sasaah.Mcp.Bridge.Engine/`, and `S/` is `04_Deployments/Sasaah.Mcp.Revit.Server/` (paths in Sasaah, never
copied; line numbers are at the pinned commit). The contract API is
[eng-contract spec 0001](../../../eng-contract/docs/specs/0001-eng-contract-0.1.md) ("contract §n"); the engine ports are
in [spec 0001](0001-engine.md) ("engine §n"); calcs are in [spec 0003](0003-calcs.md) ("0003 §n"). Everything that
needs Revit is "needs local test" (§12): **all of spike S-05** is a local test. Details the architecture leaves open are
marked **[added]** and listed in §11.

## 1. Problem

The column workflow reads the structural columns and framing of a Revit model, maps ETABS frames to Revit elements, and
changes the type or parameters of the mapped columns after ETABS has designed new sections. Reading the Sasaah source
shows what the adapter must do about a server and add-in that were built for an attended engineer, not for a
contract-speaking client:

- Every parameter or type-assignment write of the workflow (all but `duplicate_family_type` and `revit_open_model`) is of bridge kind `destructive`. The MCP server
  fetches a confirmation token automatically (S-12 §10), but fetching it calls `prepare_destructive`, and the add-in
  answers by opening a **modal Yes/No dialog in the engineer's Revit** (default No) that shows the tool and the first
  500 characters of the arguments (`04_Deployments/Sasaah.Agent.Revit.Bridge/RevitDestructiveConfirmationPrompt.cs:19-28`, `E/Handlers/PrepareDestructiveHandler.cs:43-45`).
  S-12's note that the token "is not a human confirmation" is true of the MCP layer and incomplete: a person confirms
  every call. The run is attended, and a dialog left open probably blocks the Revit thread (inferred from the handler registration in
  `04_Deployments/Sasaah.Agent.Revit.Bridge/App.cs`, where handlers run through the Revit-thread decorator; L3).
- Parameters are written by **display name** (`LookupParameter`, `A/Modify/ModifyHandlers.cs:129,137`), which depends on
  the Revit UI language; a double is converted from millimetres only for length parameters (`:166`), and any other
  double is stored raw in Revit's internal units; `Transaction.Commit()` is called and its status is not checked
  (`:138,194`), so a rolled-back write can answer `success: true`.
- Reads return parameter values **raw in internal units** (feet for lengths) next to a display string
  (`A/HandlerHelpers.cs:405-461`); list tools return integer element ids only, and the stable `uniqueId` comes only
  from `get_element_details` (`A/HandlerHelpers.cs:311`).
- `BridgeClient.CallAsync` resends a call once after an `IOException` with a new request id (`S/BridgeClient.cs:71-93`),
  and the bridge has no idempotency key, so a write can be applied twice; a client-side `TimeoutException` loses its
  code (S-12 §6); the add-in's own journal of failed and timed-out writes cannot be read through the MCP server
  (its name is taken by a local tool, `S/Program.cs:121`).
- There is no save, no close, no analytical-model and no move tool (S-12 §10), and the add-in operates on the **active
  document** of a session the engineer is using.

The harness has to stay inside what is allowlisted, make every write verifiable by reading, reconcile after a timeout
by reading (a retry is never trusted), keep the engineer's session safe, and state plainly what the engine cannot do on
Revit until Sasaah offers the missing tools.

## 2. Reuse research

| Candidate | Finding | Decision |
|---|---|---|
| Framework of 0002 | Roles, build check, allowlist, argument builders, envelopes, ledger, reconciliation by reading, `HostPort` mapping, identity (ADR-0032), record mode, fakes, doctor | Reused unchanged; this spec adds a Revit module `adapters/revit/` and the **[added]** extensions of §11 A1 |
| 0002 §4.6.5 "fit for phases 2 to 4" | Revit needs its own error parser, the timeout text rule, `catalog_version` beside the fingerprint, no unit tokens, no save tool | Followed and made precise here |
| Spec 0003 calc `harness.placement_compare` (P2 exact squared distance, P5 renames) | Same-id comparison of two models in one coordinate system | Method reused for the new calc `harness.frame_element_map` (§4.11); code not shared |
| Sasaah `ElementMapping` and `RevitElementMappingService` (shared parameters `Sasaah_EtabsElementId`, `Sasaah_SynapseId`, written by the Synapse sync) | A stored link between an ETABS id and a Revit `UniqueId`, possibly stale | Read as a **hint** only, verified by geometry (§4.11); never written (Q5) |
| Sasaah `get_change_records` (add-in journal, `E/Runtime/ChangeJournal.cs`) | Records every mutating call, failed or not, with tool and argument key names; not reachable through the MCP server | Not used (R-G10); would be the best duplicate-write evidence |
| `eng-contract` 0.1 | `model.frame_placements/1`, `model.sections/1`, units (`ft`, `mm`, `rad`, `deg`), `Quantity`, references, `ParamModel` | Used; no logic re-implemented |

## 3. Acceptance criteria

Test paths are relative to `packages/eng-harness/`. "Synthetic Revit fake" is the test-only MCP server of §4.13 (lead
decision D-5), run as a real process over stdio. "Fake-host workflow test" is a test block run by the real engine with
the real ports of this adapter against the synthetic fake.

### 3.1 Server section, allowlist, build check

- AC1. Given a `harness.toml` with `[servers.revit]` (`adapter = "sasaah-revit-mcp"`, `pipe_name`, roles `read` and
  `write`, required timeouts, a `build` pin and the role-to-class table of §4.2), when loaded, then `ServersConfig` holds
  it; a missing timeout, a role serving a class twice, an option or variable of the forbidden list of §4.2, or a `write`
  role started with `--read-only` gives `ConfigError` naming the key. Tests:
  `tests/unit/servers/test_config.py::test_revit_server_section`, `::test_revit_forbidden_options`.
- AC2. Given the allowlist data, when loaded, then every entry has the fields of 0002 AC16 plus `attended`; any name of
  the deny list of §4.4, any tool the inventory marks `excluded_from_allowlist`, a name containing `script`, `invoke`,
  `eval` or `tables_apply`, or a tool absent from the inventory is refused; the two role fingerprints computed from the
  inventory equal the values pinned in the header. Tests: `tests/unit/adapters/test_revit_allowlist.py::test_entries_complete`,
  `::test_escape_hatches_refused`, `tests/unit/adapters/test_allowlist.py::test_attended_class_and_deny_names`,
  `tests/contract/test_revit_allowlist.py::test_against_inventory`,
  `::test_fingerprints_from_inventory`.
- AC3. Given the build check (§4.3), when the executable hash, the add-in hash, the commit, a role fingerprint, or the
  excluded-tool rule fails, or a write tool is missing because the destructive toolset is off, then the check fails
  with a reason that names the cause (for a missing write tool: the Revit setting `bridgeToolsets`), and the engine
  stops before any write; the `read` role lists no bridge tool that writes. Tests:
  `tests/unit/servers/test_buildcheck.py::test_addin_hashes`,
  `tests/workflow/servers/test_revit_session.py::test_build_check_reasons`, `::test_read_role_has_no_write_tool`.
- AC4. Given the configured `pipe_name`, then the server is started with it, `revit_get_current_target` must return it,
  and `revit_switch_target` is never callable; with two reachable pipes in the fake, only the configured one is used.
  Test: `tests/workflow/adapters/test_revit_target.py::test_pipe_pinned`.

### 3.2 Replies, units, errors

- AC5. Given a reply, then it is parsed with `eng_contract.mcp.extract_raw_reply`; a `_warning` member added by the
  server is recorded as a contract warning and not as data; `truncated: true` gives `complete: false` and
  `PARTIAL_DATA`; the text `RESPONSE_TOO_LARGE` gives `LIMIT_EXCEEDED` with the narrowing hint. Test:
  `tests/unit/adapters/test_revit_replies.py::test_parse_warning_truncated`.
- AC6. Given each error form of §4.7, then the mapped code, `retryable`, `host_code` and the applied/not-applied
  certainty are as tabled, including the case-insensitive code token, the "NOT executed" and "already executing"
  texts, the dialog declined, and the code-less "unexpected error" text on a write (`TIMEOUT_UNKNOWN_OUTCOME`). Tests:
  `tests/unit/adapters/test_revit_errors.py::test_mapping_table` (parametrized), `::test_timeout_text_rule`,
  `::test_unexpected_text_on_write`.
- AC7. Given a parameter with a length specification and a raw value in feet, then the payload value is millimetres
  by `eng_contract.units.convert(value, "ft", "mm")`; a specification with no entry in the spec table is left out and
  listed as an `info` issue `PARAMETER_UNIT_UNMAPPED`; a display string is never parsed. Tests:
  `tests/unit/adapters/test_revit_units.py::test_length_feet_to_mm`, `::test_unmapped_spec_listed`,
  `::test_display_value_never_used`.
- AC8. Given a write of a number, then it is sent with `valueType: "double"` only for a parameter whose specification is
  length (checked on the read of the same epoch), formatted in the shortest round-trip decimal form in millimetres;
  any other double kind raises `NotImplementedGap` (R-G6) and nothing is sent; `valueType` is never `auto` and
  `unit` of `set_parameter_value_by_guid` is never `auto`. Test: `tests/unit/adapters/test_revit_values.py::test_value_encoding`.

### 3.3 State, identifiers, active document

- AC9. Given a model, when the state reader runs (§4.9), then it produces `harness.revit_status/1`,
  `harness.revit_levels/1`, `harness.revit_grids/1` and `harness.revit_structure/1` payloads that validate, every
  element carrying `unique_id` and `element_id`; a list reply with `truncated` is re-read per level, and a level that
  is still truncated raises `LIMIT_EXCEEDED`; a reply over the server budget is halved and retried. Tests:
  `tests/workflow/adapters/test_revit_state.py::test_kinds_and_ids`, `::test_truncation_by_level`,
  `::test_response_too_large_halves`.
- AC10. Given the state, then the fingerprint is the same for the same state read twice and in any element order, and
  differs after any change in the read set (type of an element, a mapped parameter of an instance or type, a location,
  a level elevation, a grid); it excludes the file save time and the total element count. Test:
  `tests/property/test_revit_fingerprint.py::test_order_independent_and_edit_sensitive`.
- AC11. Given elements with all fields of the role map, then `model.frame_placements/1` and `model.sections/1` rows are
  produced for them; a column without a readable rotation, or a section whose roles are not all mapped, is left out of
  the neutral kind and listed as an `info` issue (`ROTATION_UNAVAILABLE`, `SECTION_ROLES_UNMAPPED`), and stays in
  `harness.revit_structure/1`. Test: `tests/workflow/adapters/test_revit_state.py::test_neutral_kinds_complete_rows_only`.
- AC12. Given a write to elements, when called, then the adapter first reads `get_element_details` for the same ids in
  the same epoch and compares each `uniqueId` with the reference; a mismatch is `CONFLICT` and nothing is sent. Test:
  `tests/workflow/adapters/test_revit_identity_check.py::test_unique_id_verified_before_write`.
- AC13. Given any call, then `revit_get_model_metadata` is read first and its path must be the bound working copy; if
  another document is active the call fails `PRECONDITION_FAILED` (`model_open`) and nothing is sent. Test:
  `tests/workflow/adapters/test_revit_active_document.py::test_active_document_checked`.

### 3.4 Edits

- AC14. Given each write tool of §4.8, then the arguments sent equal the mapping (explicit ids, explicit `valueType`
  and `unit`, parameter name taken from the prior read), a batch is the largest whose dialog summary fits 500 characters,
  and each call appends an op to the ledger before it is sent. Test:
  `tests/workflow/adapters/test_revit_edits.py::test_edit_mapping` (parametrized), `::test_batch_fits_dialog_summary`.
- AC15. Given `set_type_parameter_values` on a type, then the adapter reads the instances of that type (same epoch) and
  refuses with `CONFLICT` (nothing sent) unless the argument `expected_instances` equals them exactly. Test:
  `tests/workflow/adapters/test_revit_edits.py::test_shared_type_refused`.
- AC16. Given `duplicate_family_type`, then the call carries no `type_parameter_overrides`; a new name that exists in the
  family (from the last read) is refused `CONFLICT` before the call; the reply's `new_type_id` is returned. Test:
  `tests/workflow/adapters/test_revit_edits.py::test_duplicate_no_overrides`.
- AC17. Given a parameter name, then it must match exactly one parameter on each target in the prior read and not be
  read-only; zero or several matches, a read-only parameter, or a parameter on the other side (type versus instance)
  is `INVALID_ARGUMENT` (`field: parameter`) before any call. Test:
  `tests/workflow/adapters/test_revit_edits.py::test_parameter_resolution`.
- AC18. Given a write, then it is sent on the `write` role in the `attended` class; given the engineer declines the
  dialog in the fake (fault `dialog_declined`), then the result is `CONFIRMATION_REQUIRED`, certain not applied, never
  retried; given the dialog is left open past the timeout (fault `dialog_unanswered`), then the result is `HOST_BUSY`
  (`MODAL_DIALOG`) with no model change. Tests: `tests/workflow/adapters/test_revit_dialog.py::test_declined_not_applied`,
  `::test_unanswered_is_busy`.
- AC19. Given a write whose reply says success but whose state is unchanged (fault `commit_unchecked`), or whose state
  differs from the request, then `check_model` gives `READBACK_MISMATCH` (error); given a read-back that cannot be read,
  `READBACK_UNAVAILABLE`; given an element missing after `change_element_type` (fault `element_replaced`), an error
  issue `ELEMENT_MISSING`; given more Revit warnings than the pre-image, a warning issue `REVIT_WARNINGS_INCREASED`.
  Tests: `tests/workflow/adapters/test_revit_readback.py::test_commit_unchecked_detected`, `::test_mismatch`,
  `::test_check_model_issues`.

### 3.5 Reconciliation

- AC20. Given a timeout on each write tool, then the adapter reads the targets and answers `applied`, `not_applied`,
  `partial` or `unknown` per §4.10, with the evidence stored as a result; a setter applied twice by the server's retry
  (fault `retry_duplicate`) is `applied`. Tests: `tests/workflow/adapters/test_revit_reconcile.py::test_outcomes_per_tool`
  (parametrized), `::test_retry_duplicate_setter_applied`.
- AC21. Given `duplicate_family_type` whose reply is `invalid_request` "already exists" for the name the adapter just
  requested (fault `retry_duplicate`), then the adapter reads the family and answers `applied` when the type exists and
  was absent in the pre-image, and no second type is created; a type that exists with other parameters is `unknown`.
  Test: `tests/workflow/adapters/test_revit_reconcile.py::test_duplicate_type_after_retry`.
- AC22. Given the crash matrix (the engine killed at each write step, then resumed) against the fake with the faults of
  §4.13, then the journal holds every step, no write is repeated, and `unknown` outcomes reach the engineer. Test:
  `tests/replay/test_revit_resume.py::test_crash_matrix`.

### 3.6 Session, identity, ports

- AC23. Given a model file, when `working_copy` runs, then the copy's hash equals the original's, `revit_open_model` is
  called with `path` of the copy and never with `allow_discard_unsaved_changes`, the reply's `path` equals the copy,
  `is_workshared` is false and `local_file_created` is false, and the identity is `derived_from` the original; any
  other reply stops with `PRECONDITION_FAILED` (`model_open`) before any write. Tests:
  `tests/workflow/adapters/test_revit_session_ops.py::test_working_copy`, `::test_workshared_refused`.
- AC24. Given `save`, `restore` or a promotion that needs the host to close the file, then `NotImplementedGap`
  (`NOT_IMPLEMENTED`) is raised with the gap id (R-G1, R-G2), nothing is sent; `started_instances` is empty and
  `close_started` does nothing: the adapter never starts, exits or closes Revit or a document. Test:
  `tests/workflow/adapters/test_revit_session_ops.py::test_gaps_not_implemented`.
- AC25. Given a `.rvt` file at first use, then its identity resolves per ADR-0032; a file whose hash is new but whose
  state fingerprint equals the last one the adapter knows (the engineer saved the harness's edits) is registered
  under the same identity without a revision change; a different fingerprint is `MODEL_CHANGED_OUTSIDE`; no path is
  stored. Tests: `tests/unit/adapters/test_identity.py::test_revit_resolution`,
  `tests/workflow/adapters/test_revit_session_ops.py::test_engineer_save_registered`.
- AC26. Given the host lock, then it is keyed by a hash of the pipe name; a second engine on the same pipe gets
  `HOST_LOCKED`. Test: `tests/workflow/servers/test_revit_hostlock.py::test_pipe_key`.

### 3.7 Mapping ETABS frames to Revit elements

- AC27. Given the golden cases of §4.11 (one-to-one match, offset applied, ambiguous, unmatched on each side, link
  hint and geometry in conflict, an upper end outside the tolerance, a distance exactly at the tolerance), then `harness.frame_element_map`
  returns the expected pairs and lists, and never pairs an element twice. Test:
  `tests/golden/test_calcs_golden.py::test_case[frame-element-map-*]`.
- AC28. Given any permutation of the inputs, then the output is the same; given the same inputs twice, then the output
  and its content hash are the same. Test: `tests/property/test_frame_element_map.py::test_permutation_invariant`.
- AC29. Given a basis without `compare.length` or with an unconfirmed `mapping.offset_*` field, then the calc refuses
  (`CalcRefused`) and no output is stored; given an input whose model revision has changed, then the engine's staleness
  check gives `REF_STALE`. Tests: `tests/unit/calcs/test_frame_element_map.py::test_basis_fields_required`,
  `tests/workflow/adapters/test_revit_map_stale.py::test_map_stale_after_edit`.

### 3.8 Kinds, role map, fakes, recordings, doctor

- AC30. Given the synthetic Revit fake, then its tool list equals the inventory schemas for every allowlisted tool
  (so its fingerprints equal the pinned ones), it implements the faults of §4.13, and it is never part of the built
  package. Tests: `tests/contract/test_revit_allowlist.py::test_fake_schemas_match_inventory`,
  `tests/unit/test_package_contents.py::test_fakes_not_shipped`.
- AC31. Given recordings, then record mode drops model titles and paths and the adapter's contract tests pass on them;
  without a recording the tests skip with a reason. Tests: `tests/unit/servers/test_record.py::test_revit_sanitized`,
  `tests/contract/test_revit_recordings.py::test_adapter_on_recordings`.
- AC32. Given `eng-harness doctor` with a `[servers.revit]` section, then it reports the configured pipe and whether the
  bridge answers, the executable and add-in hashes against the pin, the destructive toolset, the Revit version and
  the open document's base name; a `fail` gives exit 1. Test: `tests/unit/test_doctor.py::test_revit_checks`.
- AC33. Given each Revit kind of §4.5 and §4.11, a valid fixture and one invalid fixture per rule (an unknown field,
  a unit-bearing field without its suffix, counts that do not match rows, an unsorted list) are validated and the invalid
  ones fail; given the role map of §4.8, a role without a name or status, an unknown status, or two roles with one GUID
  gives `ConfigError`. Tests: `tests/contract/test_revit_kinds.py::test_fixtures`,
  `tests/unit/adapters/test_revit_parameters.py::test_role_map_rules`.

## 4. Design

### 4.1 Package layout

`packages/eng-harness/src/eng_harness/adapters/revit/`: `_allowlist.toml`, `_tools.py`, `_replies.py`, `_errors.py`,
`_units.py` and `_specs.toml` (specification identifiers), `_parameters.py` (role map), `_edits.py`, `_state.py`,
`_reconcile.py`, `_checks.py`, `_session_ops.py`; the calc is `eng_harness/calcs/frame_element_map.py`; the kinds are
`eng_harness/kinds/revit.py`. Shared modules (`adapters/_*.py`) are used as 0002 §4.1 lists; no shared module names Revit.

### 4.2 `harness.toml`: the Revit server section

```toml
[servers.revit]
adapter = "sasaah-revit-mcp"
command = "<absolute path to sasaah-revit-mcp.exe>"
pipe_name = "<bridge pipe, for example sasaah.revit.bridge.v1>"
client_grace_s = <required>
build = { sasaah_commit = "<40 hex>", exe_sha256 = "<64 hex>", addin_sha256 = ["<64 hex of each pinned add-in assembly>"], addin_paths = ["<absolute paths>"] }
host_key = "revit"

[servers.revit.roles.read]            # started with --read-only
classes = ["session", "call"]
call_timeout_s = <required>           # passed as --bridge-timeout-ms (Sasaah default 120000, S/ServerConfig.cs:8)

[servers.revit.roles.write]
classes = ["attended"]                # every write and revit_open_model: a person may have to answer in Revit
call_timeout_s = <required>

[servers.revit.parameters]            # §4.8: neutral role -> parameter, per family; data, not code
...
```

Rules (in addition to 0002 §4.2): (1) no timeout has a default; the doctor prints the Sasaah values for comparison
(client 120 s; the add-in's own queue deadline appears to be a fixed 60 s, `E/Runtime/MainThreadRequestQueue.cs:25`,
`A/RevitThreadHandlerDecorator.cs:31-36`, which makes the `attended` timeout longer than 60 s useless unless L3 shows
otherwise). (2) **Required start options**, passed by the adapter: `--pipe-name`, `--bridge-timeout-ms`,
`--disable-send-code`, `--disable-adaptive-bake`, `--no-cache-send-code-bodies`, and `--read-only` on the `read` role only.
The explicit negative options exist because `S/ServerConfig.cs:23-39` also reads `%LOCALAPPDATA%/Sasaah/mcp-server.config.json`
and `SASAAH_MCP_*` variables, which a command-line flag overrides only when given. (3) **Forbidden**: `--enable-send-code`,
`--enable-adaptive-bake`, `--cache-send-code-bodies`, `--toolsets` (the allowlist, not the toolset option, is the filter), any
`SASAAH_MCP_*` variable not set by the adapter, and `--read-only` on the `write` role. (4) The pipe's session token file is
the server's; the harness never reads it. (5) Revit's own settings (`bridgeToolsets`, `bridgeReadOnly`) are the
engineer's: the destructive toolset must be on for writes (`E/Safety/ToolsetFilter.cs:17` defaults it off); the
harness changes no Revit setting (A9).

### 4.3 Build check (extends 0002 §4.3.4)

Per role: (1) SHA-256 of `command` equals `build.exe_sha256`; (2) **the add-in assemblies** named in `build.addin_paths`
hash to `build.addin_sha256` **[added]**: the handlers, transactions and the dialog live in the add-in and the engine
assemblies, not in the MCP server, so the executable hash alone says little about write behavior (a file on disk can
still differ from what Revit loaded, since specs 008 and 009 hot-reload; L1); (3) `sasaah_commit` equals the allowlist's;
(4) the **tool-list fingerprint** of 0002 §4.3.4 item 4 over the allowlisted tools of the role equals `[fingerprint].<role>`
(the `read` role lists only read and session tools because of `--read-only`); every allowlisted tool of the role must be
listed, and a missing write tool fails with the reason "destructive toolset disabled in Revit (`bridgeToolsets`)" when
the missing tools are exactly the bridge-destructive ones; (5) a listed `revit_send_code_to_revit`, `compile_and_run`,
`dev_hot_run`, `dev_hot_unload` or `run_baked_tool` fails the check (the code toolset is on); the other tools of the deny
list (§4.4) that the server lists whatever the options (`batch_execute`, `run_synapse_command`, `shutdown_bridge`,
`authenticate`, `prepare_destructive`, `revit_switch_target`, the local bake-suggestion tools) are tolerated and never
callable, as `csi_db_tables_apply` is for CSI; (6) `revit_connection_status` reports `ping_status` ok and a `catalog_version`, recorded
beside the fingerprint (it covers the whole 248-tool catalog, S-12 §3, and is pinned from the first recording, since
the inventory cannot reproduce the server's schema bytes). `ServerCheck.build` is `"<commit[:12]>+<exe sha256[:12]>"`.
The Revit version is recorded when the first model is bound (`revit_get_model_metadata` needs an open document), and
must equal the version the allowlist header was tested with, **2026** (specs 008 and 009), else
`PRECONDITION_FAILED` (`model_open`) with the message naming both (Q9).

### 4.4 Allowlist (column workflow)

Names are MCP names (`revit_` + bridge name, S-12 §10). `kind` and `class` as 0002 §4.5.1 (`attended` is **[added]**).
"Dialog" is the bridge-kind `destructive` gate of §1. The `units` column is `n/a` (Revit has no unit tokens; §4.6).

| Tool | Kind | Class | Effect and action | Dialog | Result kind | Read-back |
|---|---|---|---|---|---|---|
| `revit_connection_status`, `revit_ping`, `revit_get_current_target`, `revit_list_available_targets` | session | session | read, plain | no | `harness.revit_status/1` (part) | n/a |
| `revit_get_model_metadata` | read | call | read, plain | no | `harness.revit_status/1` | n/a |
| `revit_list_levels` | read | call | read, plain | no | `harness.revit_levels/1` | n/a |
| `revit_list_grids` | read | call | read, plain | no | `harness.revit_grids/1` | n/a |
| `revit_list_elements` | read | call | read, plain | no | `harness.revit_structure/1` (part) | n/a |
| `revit_get_element_details` | read | call | read, plain | no | `harness.revit_structure/1` (part) | n/a |
| `revit_get_element_parameters`, `revit_get_type_parameters` | read | call | read, plain | no | `harness.revit_structure/1` (part) | n/a |
| `revit_get_available_family_types`, `revit_list_family_types_in_family` | read | call | read, plain | no | `harness.revit_structure/1` (types) | n/a |
| `revit_list_worksets`, `revit_get_model_warnings_summary` | read | call | read, plain | no | `issues.model_check/1` input | n/a |
| `revit_open_model` | file | attended | write, `open` | no | `harness.revit_status/1` | `revit_get_model_metadata` |
| `revit_duplicate_family_type` | write | attended | write, plain | no | `harness.revit_write_result/1` | `revit_list_family_types_in_family`, `revit_get_type_parameters` |
| `revit_set_type_parameter_values` | destructive | attended | write, plain | yes | `harness.revit_write_result/1` | `revit_get_type_parameters` |
| `revit_set_element_parameter_values` | destructive | attended | write, plain | yes | `harness.revit_write_result/1` | `revit_get_element_parameters` |
| `revit_set_parameter_value_by_guid` | destructive | attended | write, plain | yes | `harness.revit_write_result/1` | `revit_get_element_parameters` or `_type_` |
| `revit_change_element_type` | destructive | attended | write, plain | yes | `harness.revit_write_result/1` | `revit_get_element_details` |

Every write has `confirm = "host_dialog"` **[added]**: the adapter sets no flag (the server fetches the token); the
engine's approval comes first and the person's answer in Revit second. `ToolInfo.attended` is true for them **[added]**
so the interface can say "waiting for you in Revit".

**Deny list** (refused at load, whatever the inventory says, 0002 §4.5.1 plus **[added]**): `revit_send_code_to_revit`,
`compile_and_run`, `dev_hot_run`, `dev_hot_unload`, `run_baked_tool`, the three bake-suggestion tools, `batch_execute`,
`run_synapse_command` (both forward other tools or commands; S-12 left them for the owner, Q8), `shutdown_bridge`
(served as read-only although it changes bridge state), `authenticate`, `prepare_destructive` (the adapter must never mint
a token or open the dialog itself), `revit_switch_target` (session-wide state; the pipe is pinned), `revit_get_change_records`
and `revit_record_change` (not reconciliation evidence, R-G10). **Not allowlisted for this workflow** (not escape hatches):
`delete_element`, `overwrite_model`, every `create_*`, `set_parameter` (string value by display name), `set_project_info`,
`export_*`, and all tools of other toolsets; adding one is a spec change.

### 4.5 Replies, kinds and storage

Replies are one JSON text block on success (`S/Program.cs:174`); the server adds a `_warning` member to an object larger
than 65536 bytes and refuses one over 716800 bytes (`S/ResponseGuard.cs`). Raw reply models ignore unknown members and
record them. Kinds (all `harness.*` kinds are **[added]**, registered with `KindRegistry.extend`):

| Kind | Content (units in field names) | From |
|---|---|---|
| `harness.revit_status/1` | `title` and file base name, `revit_version`, `is_workshared`, `active_is_bound`, `catalog_version`, `ping_status` | metadata, connection status, `open_model` reply |
| `harness.revit_levels/1` | `levels`: `{element_id, name, elevation_mm}` sorted by elevation | `list_levels` (mm, 3 decimals) |
| `harness.revit_grids/1` | `grids`: `{element_id, name, start, end: Point3 or null, length_mm}` | `list_grids` (no `visible`, so no `model.grid_system/1`) |
| `harness.revit_structure/1` | `elements`: `{unique_id, element_id, category: column or framing, family, type_id, type_name, level_id, level_name, location_kind: point or curve, i, j: Point3 or null, rotation_deg or null, parameters: {role: value with unit}}`; `types`: `{type_id, family, name, instance_ids, parameters}` | lists, details, parameter reads |
| `model.frame_placements/1` | the elements of `harness.revit_structure/1` with every field known (`id` is the `unique_id`, `section` is `<family>: <type>`, `story` the level name) | derived (AC11) |
| `model.sections/1` | `frame_sections` `rectangular {b_mm, h_mm}` or `circular {D_mm}` for the types whose roles are all mapped | derived (AC11) |
| `harness.revit_write_result/1` | `tool`, `op_id`, `targets`: `{unique_id or null, element_id or type_id}`, `reply_summary` | write replies |
| `issues.model_check/1` | read-back and integrity issues (§4.8) | `check_model` |
| `harness.frame_element_map/1` | §4.11 | calc |

`model.stories/1` and `model.grid_system/1` are not produced: Revit levels have no height (the top one has no next level)
and grids no `visible` flag, and a contract kind has no way to say "unknown". Locations: a vertical column answers with
a point location, a sloped one with a curve (`A/HandlerHelpers.cs:542-596`); base and top come from the bounding box
(L6). Rotation has no field in the details reply, so it is read from an instance parameter named in the role map
(`rotation`, a candidate such as the built-in cross-section rotation, confirmed locally, L6). Large lists: element ids
are read in chunks sized by halving on `RESPONSE_TOO_LARGE`; `list_elements` caps at 1000 with no offset, so a truncated
list is re-read per `level_id`; it filters on `LevelId`, so a column is found under its base level only (`A/ElementQueryHandlers.cs:54`).

### 4.6 Units

Revit has no present-units setting that tools honor, so there are no unit tokens and `read_units` returns
`ok: true, present: "revit_schema/1"` (expected equal) **[added]**, plus a check that the bound document is active
(AC13). The traps are different: (1) **raw values are internal units**: a parameter object carries `rawValue` (a double
in feet for a length, `A/HandlerHelpers.cs:428-437`), `displayValue` (formatted in the project's units, never parsed) and
`specId`; the adapter converts by the data file `_specs.toml`, which maps specification identifiers to a contract
quantity kind and internal unit, each with a status (`reference` or `candidate`, as 0008 §4.5): v1 maps **length**
(`ft` to `mm`) and **angle** (`rad` to `deg`), both from `eng_contract.units` (`ft` is the exact international foot, NIST SP 811);
everything else is left out with an `info` issue (AC7). The exact identifier strings are `candidate` until recorded
(L7). (2) **Writes**: length-like doubles are millimetres, all other doubles are raw (R-G6), so v1 writes only lengths and
integers, strings and element ids; areas, volumes, angles and forces are refused. (3) Levels, grids and locations arrive
in millimetres rounded to 3 decimals by the server (`MmRounded`); the fingerprint is taken over the replies as received.

### 4.7 Errors and timeouts

The server answers a failure with `isError` and one string, `"<code> <message> <hint>"` (S-12 §6), where the code is the
snake-case token of `ErrorCode` (`01_Core/Sasaah.Mcp.Protocol/Messages/ErrorCode.cs`); the parser lowercases and
accepts a missing code. Paths in messages are replaced by `<path>` by the server. A rule for every write: **only the
texts below marked "certain" prove that nothing was applied; every other failure of a write is
`TIMEOUT_UNKNOWN_OUTCOME` and goes to reconciliation.**

| Form | Contract code | Rule |
|---|---|---|
| `invalid_request` | `NOT_FOUND` when the text says "was not found" or "not found on element", else `INVALID_ARGUMENT` | write: certain not applied, except `duplicate_family_type` "already exists" (§4.10) |
| `forbidden_destructive` or "Destructive operation was not confirmed in Revit." | `CONFIRMATION_REQUIRED`; message "declined in Revit" when the text says "declined by the user" | certain not applied; never retried; the engine escalates |
| `bridge_busy` | `HOST_BUSY` | certain not applied; retry `always` |
| `timeout`, text contains "was NOT executed" | `TIMEOUT_NO_EFFECT` | certain not applied (a queued call that timed out never runs later, `E/Runtime/MainThreadRequestQueue.cs` stale-command guard) |
| `timeout`, text contains "already executing" and names `prepare_destructive` | `HOST_BUSY`, `host_code: MODAL_DIALOG` | the gate is waiting for a person; no write was sent |
| `timeout`, text contains "already executing" and names a write | read: `TIMEOUT_NO_EFFECT`; write: `TIMEOUT_UNKNOWN_OUTCOME` | host marked wedged, epoch increases |
| `cancelled` | write: `TIMEOUT_UNKNOWN_OUTCOME` unless "NOT executed" (then `TIMEOUT_NO_EFFECT`) | |
| `bridge_unavailable`, "Unknown tool or Revit bridge is not reachable." | `HOST_NOT_CONNECTED` | the second form is certain not applied (nothing was sent) |
| `internal_error` with "did not commit the transaction" | `HOST_ERROR`, `host_code: TRANSACTION_NOT_COMMITTED` | `duplicate_family_type` rolls back: certain not applied |
| `internal_error`, other | read: `INTERNAL` with an `incident_id`; write: `TIMEOUT_UNKNOWN_OUTCOME` | |
| `compile_error`, `runtime_exception` | `INTERNAL` | an allowlist bug |
| `RESPONSE_TOO_LARGE: ...` (no code) | `LIMIT_EXCEEDED` | narrow and retry (§4.5) |
| "The server encountered an unexpected error..." (no code) | read: `HOST_NOT_CONNECTED` when `revit_ping` fails, else `INTERNAL`; write: `TIMEOUT_UNKNOWN_OUTCOME` | covers a client-side `TimeoutException`, a missing token file and an unavailable bridge alike (S-12 §6) |

**Attended timeouts.** The bridge call carries one timeout (client side, `--bridge-timeout-ms`), and the add-in appears
to apply a fixed 60 s deadline to every request on the Revit thread; the gate's dialog probably runs on that thread (L3). A person
who does not answer in time yields the `HOST_BUSY` row, and the dialog may still be open: later calls time out as
"NOT executed" until it is closed, and the answer to a stale dialog mints a token nobody uses. Whether reads that bypass the
queue (spec 009 FR-002: `list_grids`, `list_levels`, `list_elements`, `get_model_metadata`) answer while a dialog is open
is a local test (L3). After any timeout the host is wedged as in 0002 §4.5.6.

### 4.8 Edit kinds and parameter roles

The column workflow writes type or parameter changes only. Targets are always references (`harness.revit_structure/1`
rows or `harness.frame_element_map/1` pairs); quantities (`b_mm`, `h_mm`, `D_mm`, any length) are engineering quantities and
must be references (engine invariant 2).

| Edit kind | Tool and mapping | Status |
|---|---|---|
| Create a column type | `duplicate_family_type(source_type_id, new_type_name)`, **no** overrides (`ApplyTypeParameterOverride` reports a failed override as a warning and still commits, `A/Families/FamilyHelpers.cs:295`); the new name is checked against the last read | implemented |
| Set a type parameter | `set_type_parameter_values(typeIds=[one], parameterName, value, valueType)`; the name comes from the prior read of that type; one type per call | implemented; shared-type rule below |
| Assign a type to columns | `change_element_type(elementIds, typeId)`; the category check is the server's (`A/Modify/ModifyHandlers.cs:190`); elements grouped by target type, batch per §4.4 | implemented; identity after the call is checked (AC19) |
| Set an instance parameter | `set_element_parameter_values(elementIds, parameterName, value, valueType)` | implemented for length, integer, string, element id |
| Set a shared parameter | `set_parameter_value_by_guid(elementIds, guid, value, valueType, unit, target, allOrNothing=true)` | implemented; the GUID is in the role map |
| Materials, rebar, loads, analytical model, delete, move, create | no allowlisted tool | **not implemented** (R-G3 to R-G5); raises `NotImplementedGap` |

**Role map** (`[servers.revit.parameters.<family>]`): `section_b`, `section_h`, `section_D`, `material`, `rotation`,
`etabs_link`, each `{name, guid or null, builtin or null, status}`. It is data about the owner's families (parameter names
differ by family and language), read at the first epoch and checked: the parameter must exist on the type or element, be of
the declared storage and (for a length) the length specification, and not be read-only; a role that fails is `unmapped`
and the dependent outputs are left out with an `info` issue. A parameter is **read** by its built-in id when it has one
(`builtInParameter` in the reply, language-independent) and **written** by the display name read from the same element
(the tools accept nothing else), which is valid only within one document language; the read-back uses the built-in id or
GUID again.

**Shared types (AC15).** `set_type_parameter_values` changes every instance of the type, including columns outside the
workflow. The adapter therefore reads the type's instances in the same epoch (from `harness.revit_structure/1` types) and
refuses unless the caller names exactly that set. The default flow is to create a new type and assign it to the mapped
columns only. Q4.

**Read-back and `check_model`.** After a write, the written items are read back with the read-back tool of §4.4 and
compared: a length within the design basis field `checks.readback_relative_tolerance` (0002 G-2; never a constant here),
an integer, string or element id for equality, a type assignment by `typeId` per `unique_id`. Because the handlers do not
check the commit status (§1), this read is mandatory, not optional. Integrity checks without a tolerance:
`ELEMENT_MISSING` (an element or type of the ledger absent by `unique_id`), `TYPE_UNDEFINED` (an element whose type
is not in the family), `REVIT_WARNINGS_INCREASED` (a warning type new or more frequent than in the pre-image of
`get_model_warnings_summary`), `MODEL_UNSAVED` (info, always, R-G1).

### 4.9 State reader, fingerprint, identity

`model_state` reads, in this order: metadata; levels; grids; the two lists (`OST_StructuralColumns`,
`OST_StructuralFraming`, by built-in category name, which is language-independent, unlike `ai_element_filter`);
details for all ids (chunks); parameters of the mapped roles for instances and types; family types; `list_worksets` once
per binding. **Fingerprint**: `sha256(canonical_json(...))` over the raw replies of these reads restricted to the read
set (type id and name, each mapped parameter's `rawValue`, location, level, `unique_id`, level and grid data), sorted by
`unique_id` or `element_id`; the file save time and the element count are excluded (the count changes with any
annotation, which would stop runs for no reason). The blind spot is every edit outside the read set; the engineer's
edits inside it are seen only at the next read (no change events are exposed). A fingerprint that changed with no
adapter write since the last read increments the revision and adds `MODEL_CHANGED_OUTSIDE`.

**Identity** (ADR-0032, which Revit also needs: S-12 §9, `set_project_info` writes typed fields only): file content hash and
path hash in the harness-side store; the working copy is `derived_from` the original. Two Revit-specific rules **[added]**:
an in-memory edit never changes the file hash (there is no save tool), so the adapter's revision and fingerprint stand for
it; and when the engineer saves, a new hash with the **same** fingerprint is registered under the same identity without
a revision change (AC25). `ElementId` and `UniqueId` of an element are identical in a file and its copy, so the
references of the original's reads stay valid on the copy (L10). Writes address `element_id` (the only thing the tools
accept) after the `unique_id` check of AC12.

### 4.10 Reconciliation by reading (given the duplicate-write risk)

The risk is concrete: after a pipe error the client resends the call once with a new id (S-12 §6, `S/BridgeClient.cs:71-93`),
the bridge cannot recognize it, and the add-in journal that would show two calls is unreachable (R-G10). The adapter
therefore never treats a failed write as not applied, never retries one, and decides from state. Ledger and pre-image as
0002 §4.5.7; `reconcile` first reads `revit_get_model_metadata` (active document is the bound one, else `unknown`).

| Tool | `applied` | `not_applied` | `partial` / `unknown` |
|---|---|---|---|
| `set_type_parameter_values`, `set_element_parameter_values`, `set_parameter_value_by_guid` (setters) | every target equals the requested value | every target equals the pre-image | some of each: `partial` (`missing` lists the targets); anything else: `unknown`. A double application is `applied` (same value) |
| `change_element_type` | every element (by `unique_id`) has the requested type | every element has its pre-image type | mixed: `partial`; an element not found by `unique_id`: `unknown` (Revit may replace it, L8) |
| `duplicate_family_type` | a type of the requested name exists in the family and was absent in the pre-image; its id is returned from the read | absent and absent before | present with other values, or `invalid_request` "already exists" for a name absent in the pre-image and no read to confirm: `unknown`. **A second type is never created by the adapter** |
| `revit_open_model` | `get_model_metadata` path equals the file | the path is another document | otherwise `unknown` |

Reads that need the Revit thread wait behind an open dialog (§4.7): a reconciliation that times out is `unknown`, and the
engineer decides (engine §4.5.3). The result of a reconciled `applied` is built from the read, not from the lost reply.

### 4.11 Mapping ETABS frames to Revit elements, by reference

The mapping is a **result**, not an edit: `harness.frame_element_map/1`, produced by the calc `harness.frame_element_map`
(`verification="draft"`, no constant of its own), stored, referenced by later steps, and approved by the engineer before any
write that uses it (engine approvals).

**Inputs.** `frames`: the ETABS columns the workflow selected (`model.frame_placements/1` with a list of ids; the calc
does not classify frames, since `kind` is `other` from the CSI reader, 0002 H-G5, and the classification script embeds
engineering thresholds, OQ-G14); `elements`: `model.frame_placements/1` from the Revit adapter; optional `links`: a map `unique_id` to the string of the role `etabs_link`; `basis`.
Basis fields (0003 §4.4 style): `compare.length` (mm, ≥ 0; the position and elevation tolerance, already used by
`placement_compare`), and **[added]** `mapping.offset_x`, `mapping.offset_y`, `mapping.offset_z` (mm, signed, confirmed): the
position of the ETABS global origin in Revit model coordinates; no default, no value in code, no rotation (Q6).

**Method** (exact `Fraction` arithmetic as 0003 §4.11 P2). M1 translate each frame's ends by the offset and order the
ends of every frame and element by elevation (lower, upper). M2 a frame and an element are *candidates* when the distance
between their lower ends and the distance between their upper ends are each within `compare.length` (`d² <= t²`). M3
exactly one candidate each way gives `matched`; several give `ambiguous` with all candidates; none gives
`unmatched_frames` or `unmatched_elements`. M4 if a link names the frame id and its element is not the geometric match,
the pair goes to `conflicts` (the link is a hint from a possibly stale sync and never decides). M5 the `basis` of a pair
is `geometry`, or `both` when a link agrees. M6 nothing is paired twice and every list is sorted. Level names are not
compared (Revit and ETABS names differ); the elevations are part of M2.

**Output** `harness.frame_element_map/1`: `pairs`: `{frame_id, unique_id, element_id, type_id, basis, lower_distance_mm, upper_distance_mm}`
(distances are display floats), `ambiguous`, `unmatched_frames`, `unmatched_elements`, `conflicts`, `complete`, and the
`model_revision` of both sides in its provenance. Any change of either model makes it stale (`REF_STALE`). The map is
kept in the harness; nothing is written to Revit (Q5).

### 4.12 Ports (extends 0002 §4.5.9)

| Port method | Revit implementation |
|---|---|
| `preflight` | §4.3 |
| `acquire`, `release` | lock keyed by a hash of `pipe_name` (the bridge reports no process id) |
| `session_epoch` | increased on timeout, reconnect, server restart, `catalog_version` change |
| `locate`, `model_state` | the bound document if `get_model_metadata` path equals the file; `loaded: false` otherwise; `HostInstance.pid` is `None` (Revit is never launched here) **[added]** |
| `working_copy` | copy the file (hashes equal), `revit_open_model(path=copy, activate=true)`; checks of AC23; record identity. The copy stays open in Revit: no close tool (R-G2) |
| `check_model`, `read_units`, `read_back`, `reconcile`, `supports_reconcile`, `preview` | §4.8, §4.6, §4.10; `preview` builds the change set from the arguments and the pre-image |
| `save` | `NotImplementedGap` R-G1 |
| `restore` | `NotImplementedGap` R-G2 (a document cannot be reopened or reverted: `open_model` on an open path returns `was_already_open`, and it refuses while the active document is modified, `A/Meta/OpenModelHandler.cs:33-41`) |
| `model_files` | the model file only |
| `started_instances`, `close_started` | empty; no-op |

**Consequence for the permission modes (R-G1, Q2).** `work_on_copy` inserts a save after every write and file-copy
promotion needs the file saved and closed: neither is possible, so the mode raises `NotImplementedGap` at its first save.
`approve_each_write` works (every change set is approved, then the person confirms in Revit, and Revit's Undo restores
a write); the edited document stays **unsaved** until the engineer saves it, and the run report says so. `restore` after a
host-state mismatch is unavailable: the choices are `accept` or `abandon`.

### 4.13 Synthetic Revit fake and recordings

A test-only MCP server in `tests/fakes/sasaah_revit/` (D-5), built from the inventory schemas of the allowlisted tools:
levels, grids, columns and framing with types and parameters (raw feet values, `specId`, `builtInParameter`), a document
with a path, `open_model`, and the write tools with transactions that validate then apply. Faults, selected by the test:
`dialog_declined`, `dialog_unanswered`, `commit_unchecked` (success reply, nothing applied), `retry_duplicate` (the write
applied twice, or applied once and the first reply lost), `timeout_not_started`, `timeout_executing`, `response_too_large`,
`element_replaced` (`change_element_type` gives the element a new id), `other_document_active`, `workshared_open`,
`lost_pipe`, `destructive_toolset_off`, `code_toolset_on`. Record mode (0002 §4.8.1) gets a Revit scenario that drops
titles, paths and user names.

## 5. Inputs and outputs

| Name | Type | Unit | Bounds | Ref-capable | Source |
|---|---|---|---|---|---|
| `b_mm`, `h_mm`, `D_mm` and any length written (role map) | float | mm | > 0 | yes, engineering quantity | code-pack result or change set |
| `expected_instances` | list of element refs | | non-empty | no | the workflow, from `harness.revit_structure/1` |
| `compare.length` | float | mm | ≥ 0 | basis field | design basis (13 §2), no default |
| `mapping.offset_x`, `_y`, `_z` | float | mm | finite | basis field | design basis or engineer, confirmed |
| `call_timeout_s`, `client_grace_s` | int | s | ≥ 1 | no | `harness.toml`, required |
| `checks.readback_relative_tolerance` | float | 1 | > 0 | basis field | design basis (0002 G-2) |
| Outputs | envelopes of the kinds of §4.5 and §4.11 | canonical | | | adapter, calc |

## 6. Errors

| Condition | Code | Fields |
|---|---|---|
| Tool not allowlisted; parameter unresolved or read-only; wrong parameter side | `INVALID_ARGUMENT` | `field` |
| Literal for an engineering quantity; reference errors; bounds | contract §5 codes | `field` |
| `unique_id` differs; shared type with other instances; type name exists | `CONFLICT` | message names counts, not ids of other people's elements |
| Another document active; workshared or unexpected `open_model` reply; Revit version differs | `PRECONDITION_FAILED` (`model_open`) | message |
| Dialog declined | `CONFIRMATION_REQUIRED` | message "declined in Revit" |
| Dialog unanswered | `HOST_BUSY` (`MODAL_DIALOG`) | |
| Server and Revit errors, timeouts | §4.7 | as tabled |
| List truncated after the per-level read | `LIMIT_EXCEEDED` | `received` |
| Non-length double; unmapped specification on write; edit kind without a tool | `NotImplementedGap` (`NOT_IMPLEMENTED`) | gap id |
| Build, fingerprint, option mismatch | `ServerCheck.ok` false → engine `SERVER_CHECK_FAILED` | `reason` |

## 7. Non-goals

- Any Revit server or add-in change (ADR-0024); fakes under `tests/` are test doubles only.
- Scripts, code execution, `batch_execute`, `run_synapse_command`, baked tools, or any escape hatch, including as a workaround
  for a gap.
- Creating, deleting or moving elements; levels and grids; family editing; materials, rebar, loads, the analytical model;
  sheets, views, export.
- Saving, closing or reverting a document; promotion by file copy; workshared models (R-G9); Revit versions other than the pinned one.
- Writing the ETABS link back into Revit (Q5); classifying frames as columns; the column workflow and the ACI 318-14 column
  clauses (separate specs); engineering checks beyond read-back equality within a basis tolerance.
- Detecting engineer edits outside the read set (§4.9).

## 8. Risks

| Risk | Class | Mitigation |
|---|---|---|
| A write repeated or lost after a timeout or the server's resend; reconciliation decides wrongly | R1 | Setters are idempotent in effect; `duplicate_family_type` never retried; per-tool rules (§4.10); `unknown` goes to the engineer; AC20 to AC22; live test (L5) |
| Writes land in the wrong document because the engineer switched the active one | R1 | Path check before every call (AC13); element ids are per document; the dialog shows the arguments; residual race between check and write is told in the run report; L9 |
| A shared type changed for all its columns | R1 | AC15 rule; default flow creates a new type |
| A value written in the wrong unit (the x1000 class; non-length doubles are raw) | R1 | Length only, explicit `valueType`, read-back of every value (AC8, AC19) |
| Silent rollback behind `success: true` | R1 | Mandatory read-back (AC19); Sasaah fix R-G7 |
| The engineer cannot see what a dialog approves (arguments cut at 500 characters) | R1 | Batch fits the summary (AC14); the harness approval shows the full change set first |
| The run blocks a Revit session on an unanswered dialog | R2 | `HOST_BUSY`, no retry storm; attended runs only; doctor and run report say so |
| Add-in behavior changes behind an unchanged schema (hot reload) | R1 | Add-in hashes beside the fingerprint (§4.3); L1 |
| Edits outside the read set go unseen | R2 | Documented blind spot; check before promotion by the engineer |
| Mapping pairs the wrong column | R1 | Exact arithmetic, ambiguity is never resolved by the calc, links never decide, engineer approves the map |

## 9. Test strategy

| Criteria | Layer | Location |
|---|---|---|
| AC1, AC2, AC5 to AC8, AC25 (resolution), AC29 (basis), AC31 (sanitizer), AC32, AC33 (role map) | Unit | `tests/unit/` |
| AC2, AC30, AC31, AC33 (kinds) | Contract (inventory, fake schemas, recordings, kind fixtures; markers `synthetic`, `recorded`) | `tests/contract/` |
| AC3, AC4, AC9, AC11 to AC21, AC23 to AC26, AC29 (stale) | Fake-host workflow (real engine, real processes of the fake) | `tests/workflow/` |
| AC22 | Replay (crash matrix) | `tests/replay/` |
| AC27 | Golden (synthetic, hand-derived, `method_ref` names §4.11 rules) | `tests/golden/` |
| AC10, AC28 | Property (Hypothesis, derandomized in CI) | `tests/property/` |

Coverage floors 85% line and 75% branch (process/05 §2); mutation testing on `adapters/revit/_errors.py`,
`_reconcile.py`, `_edits.py`, `_units.py` and `calcs/frame_element_map.py` (R1). The calc is under the calc rules of 0003
(protected path `src/eng_harness/calcs/`, draft verification, hand-derived golden cases; engineering content stays draft
for the owner).

## 10. Version impact

Part of `eng-harness` 0.1.0. New harness kinds, one calc and the Revit allowlist (with its pinned Sasaah commit,
fingerprints and add-in hashes) are versioned with the package; a new Sasaah build is a new allowlist header and new
recordings in a minor release. Changes to 0002 (the `attended` class, `ToolInfo.attended`, the deny-list names,
`HostInstance.pid` optional, the `confirm` value `host_dialog`) are **[added]** in A1 and need an amendment of 0002 and
engine spec 0001; plan T1 carries them.

## 11. Open questions, gaps and additions

| Id | Question or gap | Owner | Recommendation |
|---|---|---|---|
| Q1 | Every destructive-kind write (four of the five write tools) opens a modal dialog in the engineer's Revit: the run is attended and a dialog can block the Revit thread | Owner | Accept for v1 (it is a second safety gate); say "attended" in the workflow spec; ask Sasaah, in the project lane, for typed parameter and type-assignment tools of kind `write` for this workflow |
| Q2 | Without save and close tools, `work_on_copy` and file-copy promotion cannot run on Revit (R-G1, R-G2); the engine could instead skip saves for a host that cannot save | Owner | Project lane (ADR-0026) when the owner asks: typed `save_document` and `close_document` for the active document; meanwhile `approve_each_write` and an engineer save. Not an engine change |
| Q3 | Two roles (`read` with `--read-only`, `write`) versus one | Owner | Two: the read role cannot write whatever the allowlist says, and reads keep a short timeout |
| Q4 | Shared-type rule (AC15) | Owner | Accept; default flow creates a new type |
| Q5 | Write the ETABS link into Revit (`Sasaah_EtabsElementId` through `set_parameter_value_by_guid`) | Owner | Not in v1: it writes into the engineer's model for a convenience; the map is kept in the harness. Revisit with the column workflow |
| Q6 | Origin offset between ETABS and Revit: basis fields (v1) or derived from named grid lines | Owner | Basis fields now, no rotation; a grid-derived offset as a later calc. The basis template (spec 0004) needs `mapping.offset_x/_y/_z` and a source for each |
| Q7 | `compare.length` as the single tolerance of the mapping | Owner | Reuse it; a separate `mapping.*` tolerance only if the owner wants two |
| Q8 | `batch_execute` and `run_synapse_command` on the deny list (S-12 left them for the owner) | Owner | Deny: they forward other tools or commands |
| Q9 | Revit version: specs 008 and 009 say 2026, 07 says "2025 and newer" | Owner | Pin 2026 in the allowlist header; widen only after a local test on another version (17) |
| R-G1 | No save tool (S12-G11): `HostPort.save` is `NotImplementedGap`; edits stay unsaved | Owner | Q2 |
| R-G2 | No close or revert tool: the working copy stays open, `restore` unavailable, promotion by file copy impossible | Owner | Q2 |
| R-G3 | No analytical-model tools and no `check_model` (S12-G11) | Owner | Not needed by the column workflow; `check_model` is the adapter's read-back and integrity set (§4.8) |
| R-G4 | No `move_elements` | Owner | Out of scope |
| R-G5 | Materials, rebar, loads cannot be edited with allowlisted tools | Owner | Out of scope for v1 |
| R-G6 | `set_*_values` take raw internal units for every double that is not a length; `set_parameter_value_by_guid` has a `unit` argument | Owner | Adapter writes lengths only; Sasaah: an explicit unit on the other tools |
| R-G7 | `ModifyHandlers` ignore the `Commit()` status (`:138,194`); `FamilyHandlerSupport.Commit` checks it | Owner | Mandatory read-back; Sasaah: check the status |
| R-G8 | Parameters by display name (language-dependent, first match); only the GUID tool is language-independent | Owner | Name taken from the prior read; Sasaah: built-in id or GUID on every tool (07 §2) |
| R-G9 | Workshared models: opening a copy of a workshared file creates a local of the **original central** (`A/Meta/OpenModelHandler.cs:157-202`), so the copy approach is unsafe | Owner | v1 refuses (AC23); engine gap E-G1 (replayed writes) is what a workshared Revit workflow needs, OQ-Q23 |
| R-G10 | The add-in journal (`get_change_records`, records failed and timed-out writes) is shadowed by the local tool of the same name; the local store records only calls that returned | Owner | Sasaah: rename the local tool or expose the bridge journal; then add it to reconciliation as evidence |
| R-G11 | The server resends a write once after an `IOException`, with no idempotency key; a client `TimeoutException` loses its code (S12-G11) | Owner | Reconciliation by reading (§4.10); Sasaah: no resend after the request is written, or an `op_id` |
| R-G12 | List tools return no `uniqueId`; `list_elements` caps at 1000 without an offset and reports the base level only | Owner | Details reads and per-level reads (§4.5); Sasaah: add `uniqueId` to the summary |
| R-G13 | No Revit or add-in build id (S12-G1); `catalog_version` covers the whole catalog | Owner | Add-in hashes and pinned commit (§4.3); Sasaah: version in `ping` |
| R-G14 | Model identity cannot be stamped (S12-G6) | Owner | ADR-0032 store (§4.9) |
| R-G15 | Column rotation, base and top: no field in the details reply | Owner | Candidate parameter and bounding box, confirmed locally (L6); rows without them are left out of the neutral kind |
| C1 | **Correction to S-12 §10 and the inventory notes** ("the token is not a human confirmation"): the add-in shows a Yes/No dialog for every `destructive` call (§1) | Owner | Amend S-12 §10 and the notes in `inventory/sasaah-revit-mcp.json` in a spikes change; this spec follows the source |
| C2 | Conflict: 07 §5 and §6 describe a bounded queue, a journal of `op_id`s, dialog handling by the add-in, dry runs; Sasaah has none of them | Owner | ADR-0024 already makes 07 a target; this spec follows Sasaah |
| A1 | **[added]** descriptor class `attended`, `confirm = "host_dialog"`, `ToolInfo.attended`, deny-list names `shutdown_bridge`, `authenticate`, `prepare_destructive`, `revit_switch_target`, `HostInstance.pid` optional, `harness.toml` `addin_sha256` and `addin_paths`, harness kinds of §4.5, calc `harness.frame_element_map`, codes `ELEMENT_MISSING`, `TYPE_UNDEFINED`, `REVIT_WARNINGS_INCREASED`, `MODEL_UNSAVED`, `PARAMETER_UNIT_UNMAPPED`, `ROTATION_UNAVAILABLE`, `SECTION_ROLES_UNMAPPED` | Owner | Accept with this spec |

## 12. Needs local test

Spike S-05 (readiness of `sasaah-revit-mcp` in Revit: which tools pass, dialogs, transactions and rollback, change
tracking) is entirely a local test. No CI job runs Revit. The plan writes the steps into `docs/local-testing.md` and a record
script under `acceptance/scripts/`; the owner runs them on a copy of a structural model, in an attended session:

L1 the live `tools/list` of both roles against the allowlist fingerprints, `catalog_version`, the toolsets on, whether the loaded add-in
equals the files hashed, the Revit version; L2 the reply fields of every allowlisted read on a model with columns, framing,
levels and grids (field names, id types, the `_warning` member); L3 the destructive dialog: when it appears, the text and
the 500-character summary, the effect of Yes, No and no answer, what the calls queued behind it do, which reads answer while
it is open, and the real deadline of a call; L4 transactions and rollback: a write that Revit rejects, the status the
handlers ignore, the undo entries, whether a batch is all-or-nothing, warning dialogs on commit; L5 the server's resend:
break the pipe during a write and compare the state with the reconciliation rules of §4.10, and the timeout texts of §4.7;
L6 column geometry: the location of vertical and sloped columns, base and top from the bounding box, the rotation
parameter, level of a column spanning stories; L7 specification identifiers and raw values for the mapped roles, and
which doubles the write tools convert; L8 `change_element_type` on structural columns: do `ElementId` and `UniqueId`
survive, what happens to joined framing; L9 active-document behavior: a second open document, switching between
calls, `open_model` on a copy, the unsaved-changes refusal, a workshared file; L10 hashing a `.rvt` that Revit has
open, identical ids in a file and its copy, the engineer's save; L11 change tracking: an engineer edit between two reads
and what the fingerprint sees; L12 the owner's column families: parameter names, shared-parameter GUIDs
(`Sasaah_EtabsElementId`), material parameters; L13 two Revit instances and the pipe names; L14 the mapping calc on a real ETABS and
Revit pair: offset, tolerance, ambiguity; L15 record mode on a copy, and the owner's review of recordings before commit.
