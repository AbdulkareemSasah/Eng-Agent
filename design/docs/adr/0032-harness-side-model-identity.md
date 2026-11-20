# ADR-0032: A harness-side model identity when the host cannot stamp one

Status: Proposed · Date: 2026-11-03 · Deciders: owner (pending); proposed by the agent identity with the eng-harness
server and adapter spec

Amends [04](../architecture/04-tool-contract.md) §3.3 (Proposed) and [06](../architecture/06-csi-servers.md) §6
(superseded as a build plan by ADR-0024; its rules remain the target). Closes spike gap S12-G6 (owner queue OQ-A4).

## Context

- 04 §3.3 requires a **stamped identity**: a `mdl_` ULID written into the model itself (CSI programs: project
  information; Revit: extensible storage), surviving renames and saves, with a new identity for a working copy and a
  `derived_from` link.
- No allowlisted Sasaah tool can write it. The CSI engine has no project-information call; the table `Project
  Information` can be read through `csi_db_table_read` but written only through `csi_db_tables_apply` or
  `csi_run_script`, both escape hatches kept off every allowlist ([ADR-0008](0008-tool-naming-toolsets-no-escape-hatches.md));
  `csi_model_info` returns the file path, not an identity. Revit `set_project_info` writes only fixed typed fields;
  IDEA has nothing ([S-12 report](../../../spikes/S-12-sasaah-tool-inventory/REPORT.md) §9).
- The engine needs an identity and a revision for every model it touches: staleness (11 §6 item 3), approval bindings,
  the host-state check against `model_saved` (11 §5), and `provenance.host` of every result
  ([eng-contract spec](../../../packages/eng-contract/docs/specs/0001-eng-contract-0.1.md) §4.5.5 leaves stamping to
  the adapter).
- The session evidence shows model files that move through revision chains (`REVn` copies with different names) and
  are edited by hand between harness steps (Sasaah `agent-sessions/_baseline/DESIGN-NOTES.md` د4, ج9).

## Decision

1. **Where the host offers a typed stamping tool, the adapter stamps** (04 §3.3 unchanged for it). Where it does not
   (the Sasaah CSI, Revit and IDEA servers at the pinned commit), the identity is **harness-side**: it lives in the
   project workspace, never in the model file.
2. **Harness-side identity store** under `<workspace>/.eng/state/model-files/`:
   - an index by file content: `by-sha256/<file sha256>.json` → `{model_id, revision}`, written for every state of a
     model file the harness saved or first read;
   - an index by location: `by-path/<sha256 of the normalized absolute path>.json` → `{model_id, last file sha256}`.
     Only the hash of the path is stored, never the path (no personal paths in shared state).
   - Revisions stay in the contract's `ModelStateStore` (`.eng/state/models/<model_id>.json`).
3. **Resolution at first use of a model file** (the adapter, before its `model_bound`): hash the file; a known content
   hash gives its identity; else a known path hash gives the identity of that location, and the file is treated as
   edited outside the harness (revision incremented, warning `MODEL_CHANGED_OUTSIDE`); else a new `mdl_` identity at
   revision 0. A content hash known under two identities (the same file copied into two locations) resolves to the
   identity whose path hash matches, else to a new identity with `derived_from` the older one.
4. **Working copies and promotion** follow 04 §3.3: the working copy gets a new identity with `derived_from` the
   original's; promotion records `promoted_from`. Every save by the harness writes the new content hash to the index
   before `model_saved` is journaled.
5. **In-memory edits** (between saves) are tracked by the adapter's revision counter and its fingerprint of the model
   state (06 §6), not by the file hash; the file hash identifies saved states only.
6. Provenance and records carry only `model_id` and `model_revision` (04 §3.4); nothing about the identity store
   enters a model file.

## Consequences

- When accepted: 04 §3.3 states that the identity is stamped where the host offers a typed tool and harness-side
  otherwise, with a link to this ADR; 06 §6 says the same for the CSI programs.
- The identity does not travel with the file: the same file opened from another workspace, or copied and edited by
  hand outside the harness and then moved, gets a new identity. Staleness and approvals stay correct within one
  workspace, which is where runs live.
- A typed stamping tool in Sasaah (`csi_set_project_info`, limited to project information, S12-G6) remains the
  recommended change; when it exists, the adapter stamps and keeps the store as a cache.

## Alternatives considered

- **Stamp through `csi_db_tables_apply`**: an escape hatch (ADR-0008); the baseline records a corrupted table from
  partial-row table writes. Rejected.
- **Identity from the file path alone**: breaks on the `REVn` copies and renames the evidence shows. Rejected.
- **Identity from the content hash alone**: every save would look like a new model. Rejected; the path index carries
  identity across saves made outside the harness.
- **A sidecar file next to the model**: writes into the engineer's folders and can be lost or copied apart from the
  model. Rejected.

## Pre-mortem

If this is wrong a year from now, the likely cause is two workspaces or two engineers working on one model folder, so
the same model has two identities and a reference from one workspace looks unrelated in the other. Early warning: a
promoted model that a later run resolves to a new identity instead of its `promoted_from` chain.
