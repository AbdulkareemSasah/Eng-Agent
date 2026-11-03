# 04. The Tool Contract (`eng-contract`)

Status: Proposed · Contract version: `eng-contract/1` (draft) · Applies to: the harness boundary and every code pack; the target for Sasaah servers (ADR-0024)

This is the one agreement that lets independent packages work together. It is implemented once, in the Python package
`eng-contract`, and every Python package uses it instead of re-implementing it. C# components never implement it: they
sit behind a Python front end ([ADR-0002](../adr/0002-python-uv-default-csharp-at-host-boundary.md)). The Sasaah servers
do not speak it yet; the harness adapters resolve references for them and wrap their replies into it
([ADR-0024](../adr/0024-harness-on-existing-sasaah-servers.md)).

Contents: §1 envelope · §2 result records · §3 store, references, model identity · §4 units · §5 verdicts and issues ·
§6 neutral kinds · §7 input validation · §8 errors and warnings · §9 standard tools · §10 MCP mapping · §11 versioning.

## 1. The result envelope

Every tool call returns exactly one envelope.

Success:

```json
{
  "contract": "eng-contract/1",
  "ok": true,
  "result_id": "res_01JB7Z3K9V4X2N8Q5W6E7R8T9Y",
  "kind": "forces.member_end/1",
  "summary": {
    "members": 1240,
    "combos": ["ULS-1", "ULS-2"],
    "max_abs_P": {"value": 4120.5, "unit": "kN", "member": "C12", "combo": "ULS-1", "end": "i"}
  },
  "data": null,
  "complete": true,
  "warnings": [],
  "provenance": {
    "tool": "sasaah-csi-mcp/csi_results_frame_forces",
    "tool_version": "0.3.1",
    "host": {"program": "ETABS", "version": "22.1.0", "model_id": "mdl_01JB6...", "model_revision": 12},
    "inputs": {
      "combos": {"ref": "res_01JB7YX...#/combinations/ultimate"}
    },
    "started_at": "2026-10-24T10:15:02.114Z",
    "duration_ms": 412
  }
}
```

| Field | Meaning |
|---|---|
| `result_id` | Reference to the full result in the store (§3). Present on every success, even when `data` is inline |
| `kind` | Versioned type of the payload. Shared kinds are neutral (§6); a server's own kinds carry its prefix |
| `summary` | Small structured digest that decisions depend on (P3): counts, governing values as quantity objects with their element ids, statuses. Limit 4 KB. Never misleading: if it lists "top N", it says so |
| `data` | The full payload inline, only when its serialized size is at most 16 KB; otherwise `null` |
| `complete` | `false` when the host returned partial data (P9). Consumers must not treat partial data as complete |
| `warnings` | Non-fatal conditions, each with a warning code (§8.2) |
| `provenance` | Tool, versions, host model identity and revision, every input as `ref` or `literal`, input files (`files`: base name, SHA-256 and size of each file a file-based result was read from, never a directory path), timing |

Size limits: "KB" means 1024 bytes and "MB" means 1 048 576 bytes everywhere in this contract (summary limit 4096 bytes,
inline `data` limit 16 384 bytes, payload split 8 388 608 bytes).

Failure:

```json
{
  "contract": "eng-contract/1",
  "ok": false,
  "error": {
    "code": "OUT_OF_RANGE",
    "message": "b_mm must be between 150 and 3000.",
    "field": "sections[3].b_mm",
    "expected": {"min": 150, "max": 3000, "unit": "mm"},
    "received": 45,
    "hint": "Values below 150 mm are not valid column widths. Check the source result.",
    "retryable": false
  }
}
```

## 2. Result records

The store holds immutable result records. A record is written once and never modified.

```json
{
  "contract": "eng-contract/1",
  "result_id": "res_01JB7Z3K9V4X2N8Q5W6E7R8T9Y",
  "kind": "forces.member_end/1",
  "created_at": "2026-10-24T10:15:02.526Z",
  "units": "canonical/1",
  "complete": true,
  "producer": { "...": "same object as the envelope provenance" },
  "parents": ["res_01JB7YX..."],
  "payload_sha256": "3b1f...",
  "payload": { "...": "kind-specific, validated against the kind schema" }
}
```

- `result_id` is `res_` followed by a ULID: unique, sortable by time, safe in file names and JSON Pointers.
- `parents` lists every result the producer read, giving a lineage graph from any verdict back to host data and the
  engineer's inputs.
- `payload` is the inline payload. A payload above the split size (§3.1) is not inline: `payload` is absent and
  `payload_file` names the compressed file next to the record (`<result_id>.payload.json.gz`). Exactly one of the two is
  set.
- `payload_sha256` is computed over the canonical JSON form of the payload (in both cases); it is verified on read.
- Canonical JSON: object keys sorted by UTF-16 code units, no whitespace, UTF-8, no `NaN` or infinity, no duplicate
  keys, and no integer of 2^53 or more (a producer holding such a number as an integer has a bug). Bytes in the store
  and in references are read only with `canonical.loads`, which rejects `NaN`, infinities, duplicate keys and overflow
  (`1e400`), reads an integer literal within ±(2^53 − 1) as an integer and a larger one only if it converts exactly to
  a finite float64, and otherwise fails. So re-serializing what was read gives the same bytes and the same hash.
- Engineer inputs, template values and the design basis are results too (kind `basis.*`, producer `engineer`,
  `template` or `harness`), so they are referenced exactly like host data.

## 3. Store, references and model identity

### 3.1 Where results live

- The **project workspace** is the folder given by `ENG_WORKSPACE`. Without it, a server uses
  `%LOCALAPPDATA%\eng\workspaces\default` (never the process's working directory, which MCP clients set unpredictably).
- Runs of the harness are subfolders of the project workspace (`runs/<run_id>/`); results are shared across runs of
  the same project.
- Results: `<workspace>/.eng/results/<yyyy>/<mm>/<dd>/<result_id>.json` (date from the ULID). Payloads above 8 MB (8 388 608 bytes of canonical JSON) go
  to `<result_id>.payload.json.gz`.
- Writes: write to a temporary file in the same folder, flush to disk, then rename with exclusive create; renames are
  retried with backoff (antivirus scanners briefly lock new files on Windows).
- A workspace on a cloud-synchronized folder (OneDrive and similar) or a network share is refused with
  `PRECONDITION_FAILED` (`precondition: local_workspace`): synchronization corrupts SQLite journals and races renames.
- A failure to write a record after the retries, an id collision, or a record that is unreadable, fails its hash check
  or shows a revision regression is a bug or a damaged store, not bad input: it is reported as `INTERNAL`
  (never `INVALID_ARGUMENT`), with an `incident_id`.
- Records are never deleted during a run. Cleanup is an explicit command that keeps every result referenced by a
  journal that is not archived.

### 3.2 References in tool inputs

Any input parameter declared *ref-capable* accepts either a literal or a reference:

```json
{ "b_mm": 450 }
{ "b_mm": { "$ref": "res_01JB7Z...#/sections/C45x45/b_mm" } }
{ "outlines": { "$ref": "res_01JB80A..." } }
```

- The part after `#` is a JSON Pointer (RFC 6901) into the payload. Without `#`, the reference means the whole payload,
  and the server checks the `kind` against what the parameter accepts.
- The server resolves the reference **before** validation, then validates the resolved value exactly like a literal
  (§7). A reference does not bypass bounds.
- Provenance records the reference, never a re-typed copy of the value.
- Resolution errors: `REF_NOT_FOUND`, `REF_POINTER_INVALID`, `REF_KIND_MISMATCH`, `REF_UNIT_MISMATCH`, `REF_STALE`.

### 3.3 Model identity

- Every host model gets a **stamped identity**: a `mdl_` ULID written into the model itself on creation or first attach
  (ETABS and the other CSI programs: project information; Revit: extensible storage on the project information element).
  It survives renames and saves.
- A working copy made with `save_model_as` into a run folder gets a **new** identity and records `derived_from` the
  original's identity; promotion records the reverse link.
- `model_revision` increments on every write by the server and on detected outside edits (§3.4). It is persisted in
  `<workspace>/.eng/state/models/<model_id>.json`.

### 3.4 Staleness

- A result read from a host model carries `model_id` and `model_revision`.
- Write tools reject a reference produced from the **same** model at an older revision with `REF_STALE`, unless the
  parameter is declared `stale_ok` (for example a design intent valid across revisions).
- The harness applies the same rule to every reference it passes to `ctx.calc`, `ctx.decide` and `ctx.approve`, so a
  calculation never mixes revisions of one model ([11-harness-engine](11-harness-engine.md) §6).
- Outside edits are detected per host (Revit: document change events; CSI: fingerprint, [06](06-csi-servers.md) §6) and
  raise the warning `MODEL_CHANGED_OUTSIDE`.
- References to the design basis and to file-based results (DXF) are never stale by revision; file results carry the
  file's content hash instead, and a changed file is a new result.

### 3.5 Literals and policy

General MCP clients may send literals; the server records them as `literal` in provenance. A server started with
`ENG_REQUIRE_REFS=1` rejects literals for every parameter marked `engineering_quantity` with `INVALID_ARGUMENT` (the
field is named). Inside the harness this rule
always applies, enforced by the engine ([11](11-harness-engine.md) §6).

## 4. Canonical units (`canonical/1`)

All values crossing the contract use one unit system. Servers convert to and from host units internally.

| Dimension | Unit | Field suffix | Example |
|---|---|---|---|
| Length, coordinates, displacement | mm | `_mm` | `b_mm`, `x_mm`, `ux_mm` |
| Area | mm² | `_mm2` | `As_mm2` |
| Section modulus | mm³ | `_mm3` | `Sx_mm3` |
| Second moment of area | mm⁴ | `_mm4` | `Ix_mm4` |
| Force | kN | `_kN` | `P_kN`, `V2_kN` |
| Moment, torsion | kN·m | `_kNm` | `M3_kNm` |
| Stress, strength, modulus | MPa (N/mm²) | `_MPa` | `fc_MPa`, `E_MPa` |
| Line load | kN/m | `_kN_m` | `w_kN_m` |
| Area load, soil pressure | kPa (kN/m²) | `_kPa` | `q_allow_kPa` |
| Unit weight, subgrade modulus | kN/m³ | `_kN_m3` | `gamma_kN_m3`, `ks_kN_m3` |
| Mass | kg | `_kg` | `mass_kg` |
| Angle | degree | `_deg` | `rotation_deg` |
| Time | s | `_s` | `period_s` |
| Temperature | °C | `_C` | `t_C` |
| Acceleration | m/s² | `_m_s2` | `a_m_s2` |
| Dimensionless (ratios, drift ratios) | none | `_ratio` or no suffix | `ratio`, `drift_ratio` |

Rules:

1. Every unit-bearing field in a tool schema carries its suffix; the schema also states the unit as metadata.
2. Inside generic tables and summaries, a unit-bearing value is a quantity object `{"value": 450.0, "unit": "mm"}`.
3. Servers never leave a host program in different units than they found it ([06](06-csi-servers.md) §5).
4. Conversions are implemented once in `eng-contract.units` with exact factors and tests.
5. Unit symbols on the wire are ASCII: the moment unit written `kN·m` in the table is `kN.m` in a quantity object and in
   schema metadata (the field suffix `_kNm` is unchanged).

## 5. Verdicts and model issues

### 5.1 Verdict

Verdicts have two possible sources, always labeled and never mixed silently:

- `source: "code_pack"`: produced by a verified check in `structural-codes`. This is the harness's verdict.
- `source: "host"`: a host program's own design or code check (ETABS concrete design, IDEA StatiCa checks), passed
  through by its server in the same shape. Used where no code pack exists, or for cross-checking a code pack.

```json
{
  "source": "code_pack",
  "check_id": "aci318_14.22_5_5_1.one_way_shear_concrete",
  "code": "ACI 318-14",
  "clause": "22.5.5.1",
  "subject": {"kind": "frame", "id": "B204", "station_mm": 350, "case": "ULS-1"},
  "demand":   {"value": 412.0, "unit": "kN"},
  "capacity": {"value": 368.0, "unit": "kN"},
  "ratio": 1.12,
  "ratio_limit": 1.0,
  "status": "FAIL",
  "governing": true,
  "trace_ref": "res_01JB81C...#/traces/17",
  "assumptions": ["lambda = 1.0 (normalweight concrete, from design basis)"]
}
```

- `subject.case` (optional text, at most 200 characters) names the governing load case or combination of a
  force-based check.
- `ratio` is always `demand / capacity`, computed by the code pack or the host.
- `ratio_limit` is 1.0 unless the design basis sets a stricter project limit (for example 0.95).
- `status` is one of `PASS`, `FAIL`, `NOT_APPLICABLE`, `NEEDS_ENGINEER` (outside the clause's scope or its assumptions
  are not met), `ERROR` (inputs could not be evaluated; details in the trace).
- `trace_ref` points to the calculation trace. Inside a stored `verdicts.set/1` payload, which cannot contain its own
  `result_id`, it is a local reference `#/traces/<n>` (a JSON Pointer to the n-th trace of the same payload; a full
  `res_...` reference is rejected there). A consumer rebases it onto the record it read (`<result_id>#/traces/<n>`);
  every verdict that reaches an envelope summary carries the full form shown above. Calculation notes and reports are generated from traces and journals
  only; no model writes report text that contains engineering values.

### 5.2 Model issue (produced by `check_model`)

```json
{ "severity": "error", "code": "UNSUPPORTED_STRUCTURE", "subject": {"kind": "joint", "id": "J118"},
  "message": "Joint J118 has no support and no connected frame or area." }
```

Severity is `error`, `warning` or `info`. `check_model` returns a summary `{ "errors": 0, "warnings": 3, "infos": 1, "clean": true }`,
where `clean` means zero errors and `infos` counts the issues of severity `info`. Host servers report the state of the model; they never judge code compliance
([ADR-0003](../adr/0003-mcp-servers-are-pure-adapters.md)).

## 6. Neutral kinds

Results that travel between packages use **neutral kinds** defined in `eng-contract`, so no server depends on another
server's schemas ([ADR-0004](../adr/0004-shared-tool-contract.md)):

| Family | Examples | Typical producer | Typical consumers |
|---|---|---|---|
| `geom.*` | `geom.polylines/1`, `geom.outlines/1` (closed shapes with centroid, size, rotation), `geom.line_families/1`, `geom.texts/1` | Sasaah DXF tools, through their adapter (optional DXF start) | harness calcs |
| `model.*` | `model.grid_system/1`, `model.stories/1`, `model.frame_placements/1`, `model.area_placements/1`, `model.sections/1`, `model.materials/1`, `model.load_set/1` | harness calcs, server reads through their adapters | server write tools through their adapters |
| `forces.*` | `forces.member_end/1`, `forces.joint_reactions/1`, `forces.story_drifts/1` | the CSI server adapter | code packs, the IDEA StatiCa adapter, harness |
| `basis.*` | `basis.design_basis/1`, `basis.engineer_input/1` | harness | everyone |
| `verdicts.*`, `issues.*` | `verdicts.set/1`, `issues.model_check/1` | code packs, server adapters | harness |

Rules: a server's write tools accept neutral kinds and the server's own kinds only; for the Sasaah servers the adapter
translates neutral kinds into the tool's arguments. Translation between a source's geometry and a target model's
placements is a harness calc (tested, traced), never a server's job.

## 7. Input validation

Every parameter in every tool declares:

| Property | Required | Example |
|---|---|---|
| Type | Yes | number, integer, string, enum, object, array |
| Unit | For quantities | mm |
| Physical bounds | For quantities | `b_mm` from 150 to 3000 |
| Enum values | For choices | `["concrete", "steel"]` |
| Ref-capable | Yes or no | yes |
| Engineering quantity | Yes or no | yes, which makes the harness (and `ENG_REQUIRE_REFS`) require a reference |
| Stale-ok | Yes or no | default no |

Bounds reject physically meaningless values. They are not code limits: code limits belong to code packs, which return
`NEEDS_ENGINEER` instead of rejecting. Bounds are declared once in Pydantic models, which also produce the published
JSON Schema, so documentation and validation cannot disagree.

Validation order: schema shape, reference resolution, units, bounds, cross-field rules, host preconditions. The first
failure is returned; validation never "fixes" an input.

## 8. Errors and warnings

### 8.1 Error codes

| Code | Meaning | Retryable |
|---|---|---|
| `INVALID_ARGUMENT` | Input does not match the schema, or is a literal for an `engineering_quantity` parameter under `ENG_REQUIRE_REFS` (§3.5) | No |
| `OUT_OF_RANGE` | A value is outside its declared bounds | No |
| `UNIT_MISMATCH` | A quantity has an unexpected unit | No |
| `REF_NOT_FOUND` | The referenced result does not exist in this workspace | No |
| `REF_POINTER_INVALID` | The JSON Pointer does not exist in the payload | No |
| `REF_KIND_MISMATCH` | The referenced result is of a kind this parameter does not accept | No |
| `REF_UNIT_MISMATCH` | The referenced value has an incompatible unit | No |
| `REF_STALE` | The reference comes from an older revision of the same model | No |
| `NOT_FOUND` | A named object does not exist in the model | No |
| `CONFLICT` | A named object already exists, an `op_id` was reused with other inputs, or the operation conflicts with model state | No |
| `PRECONDITION_FAILED` | The model or session is not in the needed state; `precondition` names it: `model_saved`, `model_open`, `analysis_current`, `units_verified`, `local_workspace` | No |
| `CONFIRMATION_REQUIRED` | A destructive operation was called without its confirmation | No |
| `LIMIT_EXCEEDED` | Batch size or page size above the tool's limit | No |
| `HOST_NOT_CONNECTED` | The host program is not running or not reachable | Yes |
| `HOST_BUSY` | The host queue is full, or the host shows a modal dialog (`host_code: MODAL_DIALOG`) | Yes |
| `HOST_WEDGED` | An earlier call has not returned from the host; nothing new is sent until it does | Yes, after the earlier call returns |
| `HOST_LOCKED` | Another live server process holds this host instance | No |
| `HOST_ERROR` | The host API returned a failure; `host_code` and `host_method` carry its details | Depends |
| `TIMEOUT_NO_EFFECT` | A read timed out, or a write timed out before it was sent to the host; nothing changed | Yes |
| `TIMEOUT_UNKNOWN_OUTCOME` | A write timed out after it was sent; it may be applied fully, partly or not at all. Reconcile with the same `op_id` before anything else | Only through reconciliation |
| `NOT_SUPPORTED_BY_VERSION` | The connected host version does not support this operation | No |
| `INTERNAL` | A bug in the server, or a failed or damaged result store (§3.1); `incident_id` points to the log entry | No |

`op_id` (text, at most 200 characters) is carried on `TIMEOUT_UNKNOWN_OUTCOME` and `CONFLICT` errors of write
operations, so the caller can reconcile.

A released tool never advertises an option it does not implement. "Not implemented" is not an error code.

### 8.2 Warning codes

| Code | Meaning |
|---|---|
| `PARTIAL_DATA` | The host returned fewer rows than requested; `complete` is `false` |
| `MODEL_CHANGED_OUTSIDE` | The model changed outside this server since the last read; the revision was incremented |
| `DIALOG_DISMISSED` | A host dialog was answered with its documented default during the call |
| `HOST_WARNING` | The host reported a non-fatal warning; its text is in `message` |
| `DEPRECATED` | The tool or parameter is deprecated; `message` names the replacement |

## 9. Standard tools

Every server exposes these, implemented with helpers from `eng-contract` (prefix per server,
[ADR-0008](../adr/0008-tool-naming-toolsets-no-escape-hatches.md)):

| Tool | Purpose |
|---|---|
| `<prefix>_get_server_info` | Server version, contract version, toolsets, host connection, host version, adapter in use |
| `<prefix>_read_result` | Read a stored result: optional JSON Pointer, paging (`offset`, `limit`). Read-only |
| `<prefix>_get_model_status` | Host servers: model id, path, revision, dirty flag, analysis state, unit state |
| `<prefix>_check_model` | Host servers: model integrity issues (§5.2) |
| `<prefix>_reconcile_operation` | Host servers: given an `op_id`, answer `applied`, `partial` (with the missing items), or `not_applied`, with evidence ([ADR-0007](../adr/0007-write-safety.md)) |

## 10. Mapping to MCP

- Every tool declares an `inputSchema` and an `outputSchema`. The output schema is the **union** of the success
  envelope and the failure envelope, discriminated by `ok`, so a failure envelope is valid structured content.
- Tools return the MCP tool result directly (not by raising exceptions), with `structuredContent` set to the envelope,
  `isError: true` for failures, and a compact JSON copy in a text block for clients without structured output.
- Tool annotations are mandatory: `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint` (`false` for
  host tools). Each tool's timeout class is published in its metadata (`_meta`), so clients can set per-call timeouts.
- If a client cancels a write call, the server treats its outcome as unknown and keeps it in the op ledger for
  reconciliation.
- Every server's tests include a run through the official MCP client SDK, so schema mismatches are caught.
- Transport is stdio. Streamable HTTP may be added later by ADR, for remote hosts.

## 11. Versioning

- The contract major version appears in every envelope and record. Additive changes (new optional fields, codes, kinds)
  are minor versions of the package and keep the same major.
- A breaking change needs an ADR, a new major, and a transition period in which `eng-contract` reads both majors.
- Each `kind` is versioned on its own. Producers write one version; consumers declare which versions they accept.
