# Spike report S-12: Sasaah tool inventory for the model edit cycle

Issue: none (tracked as B-005 in BUILD-STATUS.md; owner queue OQ-Q5) · Time box: not set (OQ-Q2) · Dates: 2026-11-03 · Author: Claude (subagent, task B-005)
Environment: static reading of the Sasaah sources at commit `61da80f61a6562c8e3553168056bc107e3f93013`; nothing was run against a host program and no .NET build was made. Extraction and checks ran with Python 3.14 through `uv run --script`.

All `file:line` references below are relative to the Sasaah repository root at that commit. Everything that needs a host program is marked "needs local test". Inventory data: `inventory/*.json` (one entry per tool, with source file and line). Regenerate with `uv run --script extract.py --sasaah <Sasaah checkout>`; validate with `uv run --script check.py`.

## Question

From design/docs/architecture/19-roadmap-and-spikes.md §2, S-12: for the `sasaah-csi-mcp` server, which tools cover each step and each edit kind of the model edit cycle (18 §2 and §4), with their units, errors, timeouts and build reporting; which tools run scripts or write tables (kept off every allowlist); and where are the gaps. Extended to `sasaah-revit-mcp` and `sasaah-idea-mcp` (phases 3 and 4) and to the command-line tools `tools/dxf-prep` and `tools/etabs-model` (optional DXF start), because their adapters are built in this build too.

## Method

- `extract.py` (throwaway, standard library only) tokenizes the C# catalog sources, evaluates the small C# subset they use (regular, verbatim, raw and interpolated strings, `+`, `WithTarget`/`Plain`), and writes the declared name, description, input schema and kind of every tool. For the CSI units behavior it also reads the `ExecuteCore` switch of `CsiToolService.cs`. Classification, allowlist exclusion and notes are the author's judgement, kept in tables at the top of `extract.py`. The exporter of the earlier Sasaah Agent project was not used (OQ-Q5).
- `check.py` validates the four JSON files (parse, required fields, no duplicate names, every escape hatch marked and excluded) and runs in CI.
- Counts found: 83 `csi_*` tools (matches ADR-0024), 248 Revit bridge catalog tools plus 10 tools defined in the Revit MCP server itself (258 entries), 58 `idea_*` tools, 10 command-line entries (3 entry points and 7 helpers).
- Sources read: the catalogs, the services that dispatch them, the three server `Program.cs` and config files, `CsiErrors.cs`, `CsiUnits.cs`, `CsiSession.cs`, `ComThread.cs`, `CsiModel.cs` (the edit-cycle methods), `CsiBridgePolicy.cs`, `CsiGenericInvoke.cs`, `CsiInvokeAllowlist.cs`, the Revit bridge `ListToolsHandler.cs`, `MainThreadRequestQueue.cs`, `ToolsetFilter.cs`, the Idea engine catalog and errors, the two command-line programs and their wrapper scripts, and the session baseline `agent-sessions/_baseline/REPORT.md`. Not read in full: the bodies of the 248 Revit handlers, the Idea REST and hidden-calculator clients, the bridge plugins, specs 008 and 009 (only the catalog-version contract was checked).

## Findings

### 1. Edit-cycle steps 1 to 17 against the CSI tools

Coverage: **T** = tools cover it, **P** = partly (gap named), **H** = harness work, no server tool needed, **GAP** = no tool.

| # | Step | CSI tools (and notes) | Cov. |
|---|---|---|---|
| 1 | Check server builds and tool lists | `csi_status` (installed products, running instances, `read_only`, `script_enabled`, `CsiToolService.cs:720-721`). No server version, build id or tool-list hash is reported (section 2). Tool list is read with MCP `tools/list` | P (build id GAP) |
| 2 | Open the model; save a working copy | `csi_launch` (hidden by default, `CsiToolCatalog.cs:94`), then `csi_open_model` (needs `confirm`; **only on an instance this server launched**, `CsiToolService.cs:575-579`; always rejected on attached or bridge targets, `CsiBridgePolicy.cs:8-14`), then `csi_save_model` with a new `path` (no confirm when the file does not exist, `CsiToolService.cs:547-550`). The harness copies the file first and opens the copy | T |
| 3 | Read the model state | `csi_model_info` (path, units, locked, object counts, program version), `csi_list_frames/areas/points/frame_sections/area_sections/materials/load_patterns/load_cases/load_combos`, `csi_frame_details`, `csi_get_assigned_loads`, `csi_db_table_read` (any readable table). Gaps in section 3 | P |
| 4 | Compare with the last recorded revision | Harness calc | H |
| 5 | Validate the change set | Harness; existence checks use the step 3 reads | H |
| 6 | Approve | Harness (approval page) | H |
| 7 | Save as the next revision | `csi_save_model` (new path); the harness adds fingerprint and file hash (`model_saved`) | T |
| 8 | Apply the edits | Typed tools per edit kind (section 3). One call per object; no batch or selection-based tool | P |
| 9 | Read back and check | Same reads as step 3; read-back gaps in section 3 | P |
| 10 | Save | `csi_save_model` (overwriting needs `confirm`) | T |
| 11 | Run analysis | `csi_run_analysis` (`confirm`), then `csi_analysis_status`. **Synchronous** (section 5) | P |
| 12 | Run design | `csi_design_run` (`kind` steel or concrete, `confirm`); exempt from the locked-model check (`CsiToolService.cs:956`). Aluminum and cold-formed are `unsupported_by_version` (`CsiModel.cs:2487-2520`) | T |
| 13 | Read results | `csi_results_*` (joint reactions, frame forces, story drifts (ETABS only), base reactions, joint displacements, modal periods, area and link forces, displacement envelope, frame joint forces), `csi_design_results` (steel: per-frame ratio; concrete: **beams only**, `CsiToolCatalog.cs:429-440`). Analysis messages: no tool, but the table `Analysis Messages` (import code 0, readable) is listed in `docs/csi-mcp-server/reference/etabs22-all-tables.json` and can be read with `csi_db_table_read` (needs local test) | P |
| 14 | Summarize | Harness calc | H |
| 15 | Engineer turn | Harness | H |
| 16 | Promote the accepted revision | Harness file copy | H |
| 17 | Report and sign-off | Harness | H |

### 2. The six edit kinds of 18 §2 against the CSI tools

| Edit kind | Tools | Result |
|---|---|---|
| Assign a section to frames | `csi_assign_frame_section` (`name`, `section`; `FrameObj.SetSection`, `CsiModel.cs:1545`) | Covered, one frame per call. No selection-rule or label addressing; the harness resolves rules to names with `csi_list_frames`. The section must exist; there is no auto-create |
| Define or change a frame or area section | `csi_define_frame_section`, `csi_define_area_section`, `csi_define_material` (untyped `spec` object and a free `method` member name on a fixed owner, `CsiModel.cs:3018-3026`); `csi_define_wall_section` (typed) | **Partly.** The `spec` keys are CSi API parameter names bound late by name (`CsiLateBound.cs:72-78`) and are not in the declared schema, so the adapter cannot be built from the schema alone (needs local test). Partly generic (section 8). The engine has a typed `DefineSlabSection` (`CsiModel.cs:3117`, `ICsiModel.cs:197`) that no tool exposes |
| Change slab or wall thickness | Wall: `csi_define_wall_section` (typed `thickness`, `units`). Slab: `csi_define_area_section` with `spec` (default `PropArea.SetSlab`). Per-object: `csi_assign_area_section` | Covered with the caveat above for slabs. Changing a section's thickness changes every area that uses it |
| Set frame or area loads | `csi_set_frame_load_distributed` (uniform over the full length, `Replace` true, `CsiModel.cs:1552-1560`), `csi_set_frame_load_point`, `csi_set_area_load_uniform` (`CsiModel.cs:1592-1599`) | Covered for uniform loads. Trapezoidal or partial-length loads: GAP. **Direction trap:** the frame variant maps `x`,`y`,`z` to codes 1,2,3 (`CsiModel.cs:1562-1569`), which the source comment on the area variant (`CsiModel.cs:1571-1584`) says are the local axes in the CSi API; the area variant maps them to the global codes 4,5,6. `gravity` (10) is the same in both. Use `gravity` only until a local test settles it. `csi_set_frame_load_point` passes the direction string through unmapped (`CsiModel.cs:3093-3094`); behavior needs local test |
| Change load patterns and combinations | `csi_add_load_pattern`, `csi_add_load_combo` ("add or replace": deletes the old combo first, then re-adds, not atomic, `CsiModel.cs:1502-1525`), `csi_delete_load_combo` (`confirm`, blocked on attached targets), `csi_define_load_case` (untyped `spec`) | **Partly.** No tool changes or deletes a load pattern (`LoadPatterns.Add` fails on an existing name). The 18 §2 requirement "seismic parameters through a dedicated tool, never a table write" has **no tool**: nothing in the engine touches auto-seismic parameters (grep of `Sasaah.Csi.Engine` finds none) and the only route is the excluded `csi_db_tables_apply`. The baseline records a corrupted seismic table from partial-row table writes (`agent-sessions/_baseline/REPORT.md` line 150) |
| Change restraints | `csi_set_point_restraint` (preset `fixed` or `pinned`, or six booleans, `CsiModel.cs:1601-1639`) | Covered. Read-back: `csi_list_points` returns coordinates only, no restraints (`CsiModel.cs:255-273`); use table `Joint Assignments - Restraints` through `csi_db_table_read` (key from the ETABS 22 table list; needs local test) |

Read-back gaps for step 9 (all have the same remedy: typed table reads through `csi_db_table_read`, keys from `docs/csi-mcp-server/reference/etabs22-all-tables.json`, confirmed with `csi_db_tables_list`; needs local test): frame distributed loads (`csi_get_assigned_loads` reads frame point loads only, `CsiModel.cs` GetAssignedLoads uses `FrameObj.GetLoadPoint`; table `Frame Loads Assignments - Distributed`), load pattern type and self-weight (`csi_list_load_patterns` returns names only, `CsiModel.cs:464-470`), area-section thickness (`csi_list_area_sections` returns name and type only, `CsiModel.cs:421`; table `Area Section Property Definitions - Summary`), and restraints.

Other gaps in reading: no paging. `limit` is at most 2000 and there is no offset or cursor on any list tool (`CsiToolCatalog.cs:22`, `CsiModel.cs:16`); models with more than 2000 objects cannot be listed completely (`truncated` is reported). The tools that select results for output (`csi_results_*`) change the output selection of the model as a side effect (`CsiModel.cs` SelectOutput); whether that marks the model modified needs local test.

Timing evidence from the baseline (`agent-sessions/_baseline/REPORT.md` lines 59-63): `csi_add_point` median 3.3 s per call over 100 calls; `csi_run_analysis` median 32.4 s over 74 calls with 10 timeouts. No measurement exists for the edit tools. With one call per object and no batch tool, step 8 is the likely time sink for acceptance A4; typed batch tools are the first recommended Sasaah change (section 9).

### 3. Build and version reporting

| Server | What it reports | Evidence |
|---|---|---|
| `sasaah-csi-mcp` | **Nothing usable.** No `ServerInfo` is set (`Program.cs:34-42`), `csi_status` has no version field (`CsiToolService.cs:699-722`), the shared `Directory.Build.props` pins `Version` 0.1.0 and `AssemblyVersion` 0.1.0.0 for every build. What MCP `initialize` returns by default from the SDK (ModelContextProtocol 1.1.0) cannot be established statically (needs local test) | GAP |
| `sasaah-revit-mcp` | `catalog_version`: first 16 hex characters of SHA-256 over `name\ninputSchemaJson\n` for every catalog tool, in order (`ListToolsHandler.cs:58-62`), shown by `revit_connection_status` (`Program.cs:141`) and used to send `tools/list_changed` (`Program.cs:78-79`). It covers the whole 248-tool catalog, not the filtered list, and not the 10 server-local tools. `ping` returns uptime only (`ControlHandlers.cs:18-22`); no add-in or server build id | Fingerprint exists; build id GAP |
| `sasaah-idea-mcp` | `idea_status`: installed IDEA versions and REST service state. No server version or build | GAP |
| Command-line tools | None; the wrappers rebuild the cached exe when sources are newer (`etabs-model/build.ps1`, `dxf-prep/prepare.ps1`), so behavior follows the working tree | GAP |

What a tool-list fingerprint over names and input schemas would cover, and what it would not: it detects added, removed or renamed tools and schema changes (new, removed or retyped arguments, changed defaults and bounds). It does **not** detect a behavior change behind an unchanged schema, which is exactly the baseline failure: the server running on 24 Oct lacked the 29 Oct fix for `model_locked` on `csi_design_run` (REPORT line 102), a change of handler behavior, not of schema. It is also sensitive to start options: the CSI list changes with `--read-only`, `--enable-script` and `--enable-generic-invoke` (`CsiToolCatalog.cs:667-681`), so the fingerprint must be taken over the allowlisted names only (or the options pinned and checked through `csi_status` and the presence of the generic tools). Schemas embed property `description` strings, so a second, description-free hash is less brittle. Therefore the build check needs a second signal: the adapter should hash the server executable (and record the Sasaah commit) at run start, and Sasaah should add a version and build id (section 9). The "minimum build" of 18 §3 cannot be evaluated from the servers as they are; a file hash gives equality with a tested build, not "at least".

### 4. Units

Canonical units of 04 §4 are mm, kN, MPa. The Sasaah CSI server works in the model's present units (token such as `kN_m_C`, `CsiUnits.cs:6-16`; `kN_mm_C` exists).

- **Mechanism.** `CsiModel.WithUnits` reads the present units, sets the requested token, runs the work, and restores in a `finally` block (`CsiModel.cs:51-74`). The return code of the restore call is **not checked** and nothing re-reads the units afterwards; an exception is only written to stderr (`CsiModel.cs:69-73`). The call runs inside the COM timeout (`CsiModel.cs:22-33`); on a timeout the worker is abandoned (`ComThread.cs:125-133, 147-180`) and the `finally` runs only if the hung host call ever returns on the abandoned thread. This confirms 11 §6 item 9 and refines it: the restore is deferred or lost on a timeout rather than skipped by design.
- **Tools that set and restore units (27 tools, `changes_host_units.mechanism = scoped_set_restore`):** `csi_list_stories/grids/points/frames/areas`, `csi_results_joint_reactions/frame_forces/story_drifts/base_reactions/joint_displacements/frame_joint_forces/area_forces/link_forces/displacements_envelope`, `csi_add_frame_by_coord`, `csi_add_area_by_coord`, `csi_add_point`, `csi_set_frame_load_distributed`, `csi_set_area_load_uniform`, `csi_set_point_load`, `csi_set_frame_load_point`, `csi_set_frame_offsets`, `csi_define_wall_section`, `csi_new_model`, `csi_frame_details`, `csi_design_results` (this one has a `limit` but no units, listed by mistake? No: it is not in this list, see the JSON; the list above is the JSON's `scoped_set_restore` set), `csi_db_tables_apply`. `csi_export_joint` switches to `kN_m_C` internally and restores (`CsiModel.cs:2727`). The authoritative per-tool answer is `changes_host_units` in `inventory/sasaah-csi-mcp.json`.
- **Tools that declare `units` but ignore it:** `csi_get_assigned_loads` (the dispatch at `CsiToolService.cs:173-174` never applies it) and `csi_results_modal_periods` (periods are in seconds, so harmless). Values returned by `csi_get_assigned_loads` are in the present units with no label.
- **Tools with quantities and no `units` argument:** `csi_move_area` (dx, dy, dz), `csi_define_material`, `csi_define_frame_section`, `csi_define_area_section`, `csi_define_load_case` (spec values), `csi_set_frame_releases` (spring values). They use whatever the model's present units are. The adapter must read `csi_model_info.units` before every batch and convert, or set units through another tool's scope first; both are exposed to the unrestored-units defect above.
- **Result labels.** `List(units: true)` and `Results` return a `units` field read inside the units scope (`CsiToolService.cs:343-366, 432-439`). Stress and moment units follow the token (for `kN_mm_C` stress is kN/mm², moment kN·mm); conversion to canonical MPa and kN·m belongs to the adapter (04 §4 rule 4).
- **Bridge targets.** Calls routed to a bridge plugin are forwarded unchanged (`CsiToolService.cs:920-924`); the plugin applies units. Not read here (needs local test).
- **Revit and Idea.** No unit switching. Revit schemas carry mm and degrees in field names (`x_mm`, `rotation_deg`, "numeric values in mm"), forces in kN and kNm where the description says so; conversion from Revit feet and radians happens inside handlers (not read). Idea schemas use `_mm` and `_deg`; load effects (`idea_set_loads`) are "N, Vy, Vz, Mx, My, Mz" **without a unit** in the schema, while `idea_native_set_loads` states N and N·m: GAP for `idea_set_loads`.
- **Rule for the harness (11 §6 item 9):** after any timeout, reconnect or restart, read `csi_model_info.units` before the next step; this is the only way to detect the lost restore.

### 5. Timeouts, analysis and design runs

- **Default 120 seconds**, one value for every CSI tool (`CsiServerConfig.cs:18`, `CsiModels.cs:80`), set at server start with `--call-timeout-sec` or `SASAAH_CSI_CALL_TIMEOUT_SEC`. No tool declares its own timeout and none accepts one per call. The Idea server has the same default and option (`IdeaServerConfig.cs:13`). The Revit MCP server uses 120000 ms (`ServerConfig.cs:8`); the Revit bridge main-thread queue falls back to 60000 ms for a request without a timeout (`MainThreadRequestQueue.cs:25`). Only `dev_hot_run` has its own `timeout_ms` argument. `--script-timeout-sec` is parsed (`CsiServerConfig.cs:20, 108-113`) but never passed to the engine; scripts run under the call timeout (excluded anyway).
- **Where the timeout applies.** The whole tool body runs on one STA worker thread inside `ComThread.Invoke` (`ComThread.cs:80-134`). On expiry the call returns code `timeout`, the worker is abandoned and replaced, queued items fail with `com_worker_recycled` ("never started"), and the cached session is invalidated (`ComThread.cs:125-133`, `CsiSession.cs:66-83`). The abandoned thread keeps whatever host call it was in.
- **Can analysis be started and polled through `csi_analysis_status`?** On the COM path **no**. `csi_run_analysis` calls `Analyze.RunAnalysis` and returns `{started:true}` only after it returns (`CsiModel.cs:1716-1720`), so "started" means finished. `csi_analysis_status` runs on the same single worker, so a poll waits behind a running analysis and can itself hit the timeout and recycle the worker (inferred from the code; needs local test). It returns raw per-case status codes whose meaning the server does not decode (`CsiModel.cs:1271-1284`). The baseline lists "analysis runs in the background and reports dialogs" as a missing tool of high priority (REPORT section 7) and notes `RunAnalysis` neither saves nor detects dialogs (line 103). This **conflicts with 11 §9 and 18 step 11** ("or started and then followed through the status tool"). What works today: a server instance started with a larger `--call-timeout-sec` for analysis and design runs (the value comes from S-02 measurements, not from this spike), the engine saving first (11 §6 item 7), and status read after the call returns. `csi_design_run` is synchronous in the same way (`CsiModel.cs:2487-2520`).
- **After a timeout on an instance the server launched.** `csi_attach` adopts an instance with `launched: false` (`CsiSession.cs:194`); only `csi_launch` sets `launched: true` (`CsiSession.cs:269`). A session re-attached after a recycle is therefore treated as a user instance: `csi_open_model`, `csi_new_model` and `csi_exit` are refused (`CsiToolService.cs:575-579, 561`), deletes need `--allow-attached-writes`. The harness, which owns the process, must do the exit itself (inferred; needs local test).
- **Audit trail.** Every Write, Destructive and Code call is appended to a JSONL audit file with its argument hash and result code (`CsiToolService.cs:24-54`, `CsiAuditJournal.cs`; default `%LOCALAPPDATA%/Sasaah/csi-mcp-audit.jsonl`, `CsiServerConfig.cs:32-41`). It is useful as reconciliation evidence, but a call that completes on an abandoned thread after the timeout is not recorded as completed.

### 6. Errors and the contract codes of 04 §8.1

The CSI server returns a tool result with `isError: true` and one text block holding JSON `{code, message, data}` (`Program.cs:97-101`); successes are text JSON too. There is no `structuredContent`, no output schema, no envelope, no `op_id`, no `incident_id`, no warnings (a `truncated` flag aside). An unexpected exception becomes a plain text message with no code (`Program.cs:102-106`). The adapter wraps all of this into the `eng-contract` envelope (ADR-0024).

| Sasaah code (source) | Contract code | Notes |
|---|---|---|
| `no_target` (`CsiErrors.cs:32`) | `HOST_NOT_CONNECTED` | Retry after `csi_attach` or `csi_launch` |
| `ambiguous_target` | `INVALID_ARGUMENT` | The adapter always passes `pid` |
| `target_disconnected` (also the code for **bridge** timeouts: `CsiBridgeClient.cs:649`) | `HOST_NOT_CONNECTED`; for a write, analysis or design call treat as `TIMEOUT_UNKNOWN_OUTCOME` | The message contains "timed out" for bridge timeouts; the code alone cannot separate a timeout from a lost connection |
| `timeout` (`ComThread.cs:129`) | Read: `TIMEOUT_NO_EFFECT`. Write, analysis, design, save: **`TIMEOUT_UNKNOWN_OUTCOME`** | Whether the call had started is not reported, so writes are always unknown. After it, treat the host as wedged (`HOST_WEDGED`) until reconciled: the server does not enforce this and keeps sending calls on a new worker |
| `com_worker_recycled` (`ComThread.cs:172`) | `TIMEOUT_NO_EFFECT` | The message says the call never started |
| `unsupported_by_version` | `NOT_SUPPORTED_BY_VERSION` | Also used for `csi_capture_window` on COM |
| `api_not_available` | `NOT_SUPPORTED_BY_VERSION` | |
| `confirmation_required` | `CONFIRMATION_REQUIRED` | The adapter sets `confirm` only for approved steps |
| `model_locked` (`CsiToolService.cs:964`) | **`HOST_LOCKED`** (as 11 §9 requires: shown to the engineer, never retried) | **Semantic mismatch**, section 7 |
| `not_launched_by_server` | `PRECONDITION_FAILED` | A new precondition value (for example `server_owned_instance`) is needed in 04 §8.1 |
| `read_only` | `PRECONDITION_FAILED` | The adapter should never see it: it checks `csi_status.read_only` at run start. A new precondition value is needed |
| `script_disabled`, `generic_invoke_disabled`, `unsupported_operation` | `INTERNAL` | Excluded tools; seeing one means an allowlist bug |
| `csi_error` with `data.member` or `data.return_code` or `data.hresult` | `HOST_ERROR` (`host_code` from `return_code` or `hresult`, `host_method` from `member`) | Host API failure (`CsiErrors.cs:106-123, 152-161`) |
| `csi_error` without such data | `INVALID_ARGUMENT` or `NOT_FOUND` | Used for argument validation, missing files and "unknown tool" (`Missing required argument`, `Unknown units`, `Model file ... does not exist`); also `NOT_FOUND` messages such as "Load combination ... was not found" are only distinguishable by text |
| (no code, "unexpected error" text) | `INTERNAL` | `Program.cs:102-106` |

Argument validation is shallow: `GetValue<T>()` casts on mistyped input throw plain exceptions (the "unexpected error" path), and the declared bounds (`limit` 1 to 2000, `max_width`) are not enforced by the server beyond the casts. The adapter must validate against the schema itself (04 §7).

The Revit server returns bridge errors as one text string `"<code> <message> <hint>"` with `isError` true (`Program.cs:165-170`). The bridge codes are `compile_error, runtime_exception, timeout, cancelled, bridge_busy, bridge_unavailable, invalid_request, forbidden_destructive, internal_error` (`Sasaah.Mcp.Protocol/Messages/ErrorCode.cs`). Mapping: `bridge_unavailable` to `HOST_NOT_CONNECTED`; `bridge_busy` to `HOST_BUSY`; `invalid_request` to `INVALID_ARGUMENT`; `forbidden_destructive` to `CONFIRMATION_REQUIRED`; `runtime_exception` to `HOST_ERROR`; `internal_error` to `INTERNAL`; `timeout`: the bridge message says whether the work never started or was already executing (`MainThreadRequestQueue.cs:109, 168-171`), so `TIMEOUT_NO_EFFECT` or `TIMEOUT_UNKNOWN_OUTCOME` by that text; `cancelled` on a write to `TIMEOUT_UNKNOWN_OUTCOME`. Two defects of the MCP layer: a client-side `TimeoutException` from `BridgeClient` is not caught specifically and surfaces as the generic "unexpected error" text with no code (`BridgeClient.cs:88`, `Program.cs:176-180`), so the adapter must treat that text on a write as unknown outcome; and `BridgeClient.CallAsync` retries once after an `IOException` (`BridgeClient.cs:70-93`), resending the call with a new request id, which can apply a write twice (needs local test).

The Idea server codes are `no_project, connection_not_found, confirmation_required, read_only, script_disabled, timeout, service_unavailable, unsupported_by_version, api_not_available, iom_error, idea_error` (`IdeaErrors.cs:31-41`): `no_project` to `PRECONDITION_FAILED` (`model_open`), `connection_not_found` to `NOT_FOUND`, `service_unavailable` to `HOST_NOT_CONNECTED`, `iom_error` and `idea_error` to `HOST_ERROR`, the rest as for CSI. The Idea timeout does not cancel the work (`IdeaSession.cs:84-103`), so a timed-out write is unknown outcome.

### 7. `model_locked` and the cycle

`model_locked` is raised by every Write, Destructive or Code tool except `csi_unlock_model`, `csi_save_model`, `csi_run_analysis` and `csi_design_run` when the model is locked (`CsiToolService.cs:947-968`). ETABS locks the model after an analysis. In contract 04 §8.1, `HOST_LOCKED` means "another live server process holds this host instance"; in the Sasaah server it means **the analysed model is locked**. In the cycle, the edits of step 8 of cycle N+1 come after the analysis of cycle N, so they will hit `model_locked` every cycle. Unlocking is `csi_unlock_model` (`confirm`), which "discards the locked analysis state" (`CsiToolService.cs:284`, `CsiModel.cs:1730-1735`). 11 §9's rule ("shown to the engineer, never retried") would stop every second cycle. Recommendation: the adapter checks `csi_model_info.locked` before step 8 and, if locked, runs `csi_unlock_model` as an approved, journaled step (the analysis results are stale after edits anyway), and maps `model_locked` to `PRECONDITION_FAILED` (new precondition `model_unlocked`), keeping `HOST_LOCKED` for the real instance-lock meaning. This needs an ADR amending 04 §8.1 and 11 §9 (owner queue). The mapping requested for this spike (`model_locked` to `HOST_LOCKED`) is recorded in the table above.

### 8. Tools that run scripts, evaluate code, forward API calls or write tables (excluded from every allowlist)

| Server | Tool | Why | How it is exposed |
|---|---|---|---|
| CSI | `csi_run_script` | Compiles and runs C# against the live model | Opt-in: `DisableScript` defaults to true (`CsiServerConfig.cs:14`); needs `--enable-script` |
| CSI | **`csi_db_tables_apply`** | Writes database tables directly (`ApplyEditedTables`) | **Always listed.** Kind Write, so neither `DisableScript` nor the default start options hide it; only `--read-only` does, which hides every write. The adapter allowlist is the only barrier. 11 §9 says the server is started with `DisableScript`, which does **not** cover this tool |
| CSI | `csi_invoke`, `csi_object_add`, `csi_object_delete`, `csi_object_set`, `csi_object_get` | Generic late-bound calls by path or free method name (allowlisted path table in `CsiInvokeAllowlist.cs`, but `csi_object_*` take a free `method`) | Hidden unless `--enable-generic-invoke` (`CsiToolCatalog.cs:664-681`). 11 §9 and ADR-0008 name only two tools; these five should be listed too |
| Idea | `idea_run_script` | Compiles and runs C# against the project | **Enabled by default**: `DisableScript` defaults to false (`IdeaModels.cs:435`); start with `--disable-script` |
| Revit | `compile_and_run`, and the alias `revit_send_code_to_revit` | Compiles and runs C# inside Revit | Kind code; served only if the bridge toolsets include `code` (the bridge default is read, write, control, `ToolsetFilter.cs:15-17`; the user setting needs local test) and not with `--disable-send-code` |
| Revit | `dev_hot_run`, `dev_hot_unload` | Hot-loads an assembly and runs a command or static method | Kind code, same gating |
| Revit | `run_baked_tool` | Runs a generated tool by name with free params | Kind code, same gating |
| Revit | `revit_accept_bake_suggestion`, `revit_dismiss_bake_suggestion`, `revit_list_bake_suggestions` | Tool-baking family (writes generated tool files) | Only with `--enable-adaptive-bake` |

Recommended additional exclusions (flagged in the JSON, decision for the owner): Revit `batch_execute` (forwards up to 20 catalog tools in one request, so an allowlist would have to inspect its sub-commands) and `run_synapse_command` (runs any loaded Revit `IExternalCommand` by name through reflection, `SynapseCommandHandler.cs:52-80`). Partly generic and allowed only with conditions: the CSI `spec` tools (`csi_define_material`, `csi_define_frame_section`, `csi_define_area_section`, `csi_define_load_case`: free `method` on a fixed owner), Revit `set_parameter` (by display name, string value), Idea `idea_native_code_setup` (merge-update of arbitrary fields), `idea_native_set_loads` (raw loading JSON) and `idea_update_operation` (untyped geometry parameters). The adapters should pin `method` to a fixed list and validate keys, or use the project lane (ADR-0026). Annotation defects: the Idea tools `idea_native_calculate`, `idea_native_code_setup` and `idea_native_libraries` are annotated read-only but write files when `confirm` is given; Revit control tools (`shutdown_bridge`, `authenticate`, `prepare_destructive`) and `revit_switch_target`, `revit_record_change` are annotated read-only although they change state. Annotations cannot be trusted for classification; the adapters classify by name.

### 9. Model identity

Can a tool stamp and read an identity in project information (04 §3.3)? **CSI: reading yes (partly), stamping no.** No tool writes project information: the engine has no project-info call (grep of `Sasaah.Csi.Engine` finds none). The table `Project Information` (import code 3) is in the ETABS 22 table list and `csi_db_table_read` can read it (needs local test), but writing it needs `csi_db_tables_apply` (excluded) or `csi_run_script` (excluded). `csi_model_info` returns the file path, not an identity. **Revit:** `set_project_info` writes only the typed fields name, number, client_name, address, status, issue_date (`ToolCatalog.Meta.cs`), no extensible-storage stamp, and `get_model_metadata` returns title, path and counts. **Idea:** none. Consequence for S-04: the identity must live in a harness sidecar keyed by path and file hash until a typed stamping tool exists. Recommended Sasaah change: a typed `csi_set_project_info` limited to the Project Information table (and the CSi API project-information call, to be verified locally), which keeps the "no table writes" rule.

### 10. Revit (`sasaah-revit-mcp`, phase 3)

- Shape: the MCP server builds `tools/list` from the bridge `list_tools` reply at request time (`Program.cs:71-89`), names every tool `revit_<bridge name>`, and annotates from the bridge kind (`Program.cs:196-205`). Bridge kinds: 101 read, 69 write, 69 destructive, 4 code, 5 control. Kinds are enforced at the bridge by its toolset filter; destructive tools get a confirmation token that the MCP server fetches **automatically** (`Program.cs:157-162`), so the token is not a human confirmation. `revit_get_change_records` and `revit_record_change` are listed twice (local tool and bridge tool of the same name, `Program.cs:89`).
- Against the intended phase 3 scope of 07 §8: present, by Sasaah name, `list_levels`, `list_grids`, `get_model_metadata`, `list_walls`, `list_elements` and `ai_element_filter` (columns, framing, floors, foundations by category), `get_element_parameters`, `get_type_parameters`, `get_element_geometry`, `get_available_family_types`, `duplicate_family_type`, `set_type_parameter_values`, `create_level`, `create_grid`, `create_structural_column`, `create_structural_beam`, `create_structural_wall`, `create_foundation_isolated`, `create_foundation_wall`, `change_element_type`, `set_element_parameter_values`, `set_parameter_value_by_guid`, `delete_element`, `open_model`. **GAP:** `save_document` and `save_document_as` (no save tool; `save_selection` is a saved selection set), `move_elements`, `list_analytical_members`, `get_analytical_model`, `check_model`, and any reconcile operation. The full mapping is in `inventory/sasaah-revit-mcp.json` under `server.design_07_section_8_mapping`.
- Units: millimetres and degrees in schemas; `create_structural_column` takes `type_id` or `type_name` (name-addressed, the prose style 07 §2 rejects).
- Errors, timeouts, build: section 6, 5 and 3. Dry run: `batch_execute` and workflow tools take `dry_run`; the single-write tools have none.

### 11. IDEA StatiCa (`sasaah-idea-mcp`, phase 4)

- 58 tools in two families: a project model (`idea_create_connection`, `idea_set_members`, `idea_add_plate`, `idea_set_loads`, and so on, live through the REST service or offline) and `idea_native_*` file-direct tools for 21.x `.ideaCon` files, many of which overwrite their input `path` unless `out_path` is given (every one needs `confirm`). Against 08 §2: open, save, create from template, list connections, list operations, set load effects, apply template, run calculation and check results are present; `get_stress_strain_results` and `check_model` are GAP; `list_members` and `get_connection_summary` are covered by `idea_get_connection` and `idea_get_model_info`; plate, bolt and weld edits go through the untyped `idea_update_operation` (no `set_plate_thickness`, `set_bolt_assembly`, `set_weld_size`).
- `idea_calculate` offline returns a "marked stub summary" (description): the adapter must never turn a stub into a verdict. `idea_native_loads_from_frame_forces` and the joint-bundle tools (`idea_native_create_from_joint`, `idea_native_link`, `idea_native_sync_from_joint`) consume the `sasaah.joint/1` bundle written by `csi_export_joint`; they do ETABS-to-IDEA force mapping inside Sasaah, which 08 §4 assigns to a harness calc (engineering content, risk R1: not adopted in this build).
- Timeout 120 s, no cancellation on timeout. Errors in section 6.

### 12. Command-line tools (optional DXF start, 18 §6)

| Tool | Inputs | Outputs and side effects | Notes |
|---|---|---|---|
| `tools/dxf-prep/prepare.ps1` | `-Path` (required) plus about 25 options (`inventory/sasaah-cli-tools.json`) | `<OutDir>/<stem>.dxf`, `<stem>.grids.json`, preview PNG, `prep-report.md`; input never modified | Metres, origin at the lowest-left grid intersection (`-Origin keep` to disable). Runs a validator, AutoCAD `accoreconsole` (path fixed to AutoCAD 2023 in the script) and a Python renderer: needs AutoCAD and Python on the PATH (needs local test). CLI exit codes 0 ok, 1 usage, 2 unreadable input, 3 failed (`Program.cs:34-37`); the script exits 1 on any failure |
| `tools/dxf-prep/inspect.ps1` | `-Path`, `-OutDir` | `<stem>.classify.json`, `<stem>.classify.png` | Read-only preview |
| `tools/etabs-model/build.ps1` | `-Config` (required), `-NoEtabs`, `-Rebuild` | `<out>.e2k`, `<out>.EDB`, `model-report.md` | **Launches its own hidden ETABS 22, saves the EDB and runs the analysis**; ETABS call timeout 300 s inside the CLI (`ModelFromDxf.Cli/Program.cs:194`); no overall timeout; exit 0 ok, 1 failure, 2 usage. The harness must treat it as an analysis-class write with its own process bound (Job Object) |
| `tools/etabs-model/classify-columns.ps1` | `-FootingsJson`, `-E2k`, `-Out` | `column-overrides.json` | Embeds engineering thresholds for column sizing: not adopted, owner queue |
| helpers (`validate_etabs_dxf.py`, `render_preview.py`, `render_classify.py`, `compare_dxf.py`, `make_variants.py`, `check_autocad_open.ps1`) | positional | called by the scripts | Not adapter tools |

The wrappers build the CLI with `dotnet publish` on first use or when sources are newer, so the SDK is a runtime dependency of the wrapper. Two sample office profiles in `tools/dxf-prep/profiles/` carry office-specific layer names; they are not copied into this hub.

## Answer

Partly. The 83 CSI tools cover steps 1 to 3, 7, 10 to 13 and four of the six edit kinds well enough to build the first slice; the cycle can run today against the CSI server only with the following conditions:

1. **No build id:** the "server build at least the minimum" check of step 1 cannot be evaluated; only a tool-list fingerprint and a file hash of the server executable are available, and the fingerprint does not catch behavior fixes.
2. **Analysis and design are synchronous**; there is no start-and-poll. They need a dedicated server instance with a larger server-wide call timeout, and every timeout is `TIMEOUT_UNKNOWN_OUTCOME` followed by reconciliation, with the units read first.
3. **The model is locked after analysis**, so every cycle needs an approved `csi_unlock_model` before its edits.
4. **Edit kinds without a complete tool:** definition or change of frame and area sections (untyped `spec`; a typed slab setter exists in the engine but is not exposed), change or delete of load patterns, and seismic parameters (no tool at all). Frame loads have a direction trap (`x`,`y`,`z` map to local axes) until a local test settles it.
5. **Read-back gaps** (frame distributed loads, pattern definitions, area-section thickness, restraints, analysis messages) are reachable only through typed table reads whose keys need confirming locally.
6. **No batch tools**, so step 8 is one call per object; A4 is at risk.
7. **Model identity cannot be stamped** (section 9); a harness sidecar is the fallback.
8. **`csi_db_tables_apply` is not hidden by `DisableScript`**; the adapter allowlist must exclude it, and 11 §9 must list all excluded tools (`csi_invoke`, `csi_object_*` too).

Revit and Idea cover most of their intended scope (sections 10 and 11) with the gaps named; the DXF start is a pair of long-running wrappers, not tools with a contract.

## Consequences for the design

Proposals only; each document change goes through the owner (rule 2 of the hub's AGENTS.md), none is made here.

- 11 §9 and 18 step 11: remove "started and then followed through the status tool" until Sasaah offers an asynchronous run; state that the analysis server instance gets a larger call timeout.
- 11 §9 and ADR-0008: list all excluded CSI tools (`csi_run_script`, `csi_db_tables_apply`, `csi_invoke`, `csi_object_add`, `csi_object_delete`, `csi_object_set`, `csi_object_get`), and state that `DisableScript` does not hide `csi_db_tables_apply`.
- 04 §8.1 and 11 §9: new ADR for `model_locked` (section 7) and for the two new preconditions (`model_unlocked`, `server_owned_instance`).
- 18 §2: edit kinds "define or change a section" and "change load patterns and combinations" are partly covered; the seismic part has no tool. Keep the list as proposed (OQ-Q4) but mark seismic parameters as blocked on a tool.
- 18 step 2: the model is opened by launching an instance and opening the copy, never by opening in the engineer's instance.
- 04 §3.3 and 06 §6: identity is kept in a harness sidecar until a typed stamping tool exists.
- ADR-0024 consequences: the harness hashes the server executable at run start and pins the Sasaah commit per adapter.

## Open risks

- Everything here is static reading. The live `tools/list` can differ (start options, the SDK's serverInfo, conditional Revit tools). Compare the JSON with a live listing at the first local run (OQ-Q5, needs local test).
- Several statements are inferences from code and are marked "needs local test": poll behavior while an analysis runs, the session state after a worker recycle, the frame load direction codes, the late-bound `spec` keys, the table keys for read-backs, bridge-plugin unit handling, the double send on a Revit bridge `IOException`.
- Test counts, the Revit handler bodies, the Idea REST and hidden-calculator clients, the bridge plugins and specs 008 and 009 were not read in depth; a defect there is not covered.
- The classification and exclusion tables in `extract.py` are one engineer's reading; the owner confirms the borderline cases (spec tools, `batch_execute`, `run_synapse_command`).
- Sasaah carries a stale second copy of its tree under `.claude/worktrees/` inside the checkout; it was ignored. Only the main tree at the pinned commit was read.

## Owner-queue items (recommendation for each)

| Id | Item | Recommendation |
|---|---|---|
| S12-G1 | No server version or build id in any Sasaah server (`csi_status`, MCP `serverInfo`); `Version` is 0.1.0 for every build | Sasaah change: set `ServerInfo` and add `server: {version, commit, build_utc}` to `csi_status`, `idea_status` and the Revit `ping`. Meanwhile the harness hashes the executable |
| S12-G2 | Analysis and design are synchronous; no start-and-poll; no save or dialog handling in `RunAnalysis` | Sasaah change (baseline REPORT section 7, high): a `wait:false` mode plus polling through `csi_analysis_status` with decoded codes, save first, dialog report. Until then: dedicated analysis server instance with a large `--call-timeout-sec`, sized by S-02 |
| S12-G3 | Model locked after analysis blocks the next cycle's edits; `HOST_LOCKED` means something else in 04 | New ADR (section 7): `model_unlocked` precondition, adapter unlock step with approval |
| S12-G4 | No batch or selection-based edit tools; one call per object | Project lane (ADR-0026) first, then a Sasaah change: typed batch assign-section, assign-loads, set-restraints |
| S12-G5 | No seismic parameter tool; no change or delete of load patterns; no typed slab section tool (exists in the engine, not exposed) | Gap report plus Sasaah change; seismic parameters stay out of the v1 edit list until a tool exists (OQ-Q4) |
| S12-G6 | Model identity cannot be stamped | Sasaah change: typed `csi_set_project_info` (project information only). Fallback: harness sidecar |
| S12-G7 | `csi_db_tables_apply` is visible by default and not covered by `DisableScript` | Sasaah change: a `--disable-db-write` option and listing it with the script tool; adapter allowlist as the second barrier |
| S12-G8 | Read-back gaps: frame distributed loads, pattern definitions, area-section thickness, restraints, analysis messages | Adapter reads typed tables through `csi_db_table_read`; confirm the keys at the first local run; or Sasaah read tools |
| S12-G9 | Frame load direction codes (`x`,`y`,`z` possibly local axes) and the unrestored units on timeout | Local test first; then Sasaah fix: map frame directions like the area variant, check and verify the units restore |
| S12-G10 | `csi_define_*` `spec` tools are untyped with a free `method` | Owner decision: allow with an adapter-pinned method list (recommended) or treat as escape hatches and use project-lane typed tools |
| S12-G11 | Revit: no save tool, no analytical model tools, no move, no `check_model`; `TimeoutException` loses its code; one internal retry may duplicate a write; destructive tokens fetched automatically | Phase 3: project lane for save and analytical reads; Sasaah fix for the timeout code and the retry |
| S12-G12 | Idea: `idea_calculate` stub mode; no stress-strain results or `check_model`; unit missing in `idea_set_loads`; script enabled by default | Phase 4: adapter rejects stubs; start with `--disable-script`; Sasaah schema fix for the load unit |
| S12-G13 | `tools/etabs-model/classify-columns.ps1` embeds engineering thresholds | Engineering content for the owner (risk R1); not adopted |
| S12-G14 | Proposed amendments listed under "Consequences for the design" | Owner approves; the lead opens the design-change pull request |
