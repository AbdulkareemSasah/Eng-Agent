# 18. First Slice: The Model Edit Cycle

Status: Proposed (rewritten by ADR-0025) · Phase 1 · This workflow is the proof of the whole architecture.

## 1. Goal

Take an existing ETABS model through repeated cycles of edit, analysis, design and review, each ending in a revision
the engineer accepts. The cycle must be faster than the same changes take today, by hand or in an agent chat, with
every value traceable and no manual edit lost ([ADR-0025](../adr/0025-first-workflow-edit-cycle.md)).

## 2. Scope

One ETABS model through `sasaah-csi-mcp` ([ADR-0024](../adr/0024-harness-on-existing-sasaah-servers.md)). A request
is a change set made of these edit kinds:

| Edit kind | Parameters and their sources |
|---|---|
| Assign a section to frames | Frames by label or by a selection rule; a section that exists in the model or the template |
| Define or change a frame or area section | Properties from the template or engineer input |
| Change slab or wall thickness | Areas; thickness from the template or engineer input |
| Set frame or area loads | Objects, load pattern, value from the design basis or engineer input |
| Change load patterns and combinations | From the template, including seismic parameters through a dedicated tool, never a table write |
| Change restraints | Joints, restraint type |

This list is the starting proposal. The owner confirms it in the workflow spec, and spike S-12 checks it against the
server's tools; a kind without a tool goes through the project lane ([ADR-0026](../adr/0026-project-lane-for-tools.md))
or a gap report.

Out of scope for this slice: adding, moving or deleting objects; stories and grids; other host programs; code checks
(phase 2).

## 3. Inputs and their sources

| Input | Source |
|---|---|
| ETABS model | Engineer selects it; the run works on a copy ([ADR-0018](../adr/0018-permission-modes.md)) |
| Template and design basis | Engineer selects and confirms them ([13](13-templates-and-design-basis.md)) |
| Change set | Engineer, or a coding agent from the engineer's words; validated (P5) and approved before any write |
| Values in the change set | Each with its source: template, design basis or engineer input (P8) |
| Minimum `sasaah-csi-mcp` build | Declared by the workflow; checked at run start |

## 4. Steps

Steps 1 and 2 run once per run; steps 3 to 15 form one cycle and repeat until the engineer accepts a revision.

| # | Step | Kind | Notes |
|---|---|---|---|
| 1 | Check server builds and tool lists | enforced | Stops before any write if a build is older than the declared minimum or its tool list differs from the tested one ([11](11-harness-engine.md) §6) |
| 2 | Open the model; save a working copy in the run folder | tools | The baseline revision |
| 3 | Read the model state | tools | Identity, revision, and the objects and properties the edit kinds touch |
| 4 | Compare with the last recorded revision | calc | Differences are engineer changes: shown and recorded, never overwritten |
| 5 | Validate the change set | enforced | Types, units and bounds; objects and sections exist or are defined in the same set |
| 6 | Approve the change set, with the differences | approve | On the local approval page ([ADR-0027](../adr/0027-phase-1-interface.md)). The approval is bound to this change set and this model state; single edits can be rejected |
| 7 | Save as the next revision | tool | `model_saved` with revision, fingerprint and file hash |
| 8 | Apply the edits | tools | Batched, by reference to the change set, after a check that the model has not changed since the approval; if it has, the cycle returns to step 3 |
| 9 | Read back and check | enforced | Every written value matches the change set (P7) |
| 10 | Save | tool | Before analysis, so no run waits on a save dialog |
| 11 | Run analysis | tool | With a timeout suited to analysis, or followed through the status tool ([11](11-harness-engine.md) §9). A timeout is `TIMEOUT_UNKNOWN_OUTCOME`: reconcile by reading the model state and units before any retry |
| 12 | Run design | tool | Needs a Sasaah build in which design runs work |
| 13 | Read results | tools | Analysis messages, drifts, design ratios and failing members, by reference |
| 14 | Summarize | calc | Governing ratios, failing members, changes from the previous revision |
| 15 | Engineer turn | approve | Accept the revision; ask for more edits; or edit by hand and continue. A new cycle starts at step 3 |
| 16 | Promote the accepted revision | approve | File copy with backup; stops if the original changed ([11](11-harness-engine.md) §7) |
| 17 | Report and sign-off | approve | HTML run report; outputs stay `DRAFT` until signed |

## 5. Acceptance criteria and benchmark

Before the first release, the owner prepares benchmark B-1 (v1 is built before live testing,
[ADR-0028](../adr/0028-build-v1-in-this-repository.md)): three past projects, each with its ETABS model,
five to ten typical change requests taken from the real work, and the time those changes took by hand and, where
recorded, in agent chats (the session baseline of ADR-0024).

| Id | Criterion |
|---|---|
| A1 | After each B-1 request, the model holds exactly the requested changes and nothing else, checked by the difference report against the change set |
| A2 | Every analysis and design run completes, or ends as `TIMEOUT_UNKNOWN_OUTCOME` followed by reconciliation; no run waits on a dialog; a stale server build is stopped before any write |
| A3 | The audit shows that every engineering value written came from a reference (change set, basis or step result), checked automatically |
| A4 | Median time from request to accepted revision, including the engineer's time, is at most 50% of the B-1 time for the same changes |
| A5 | A manual edit made between cycles always appears in the next cycle's differences and is never overwritten, tested by a hand edit in every B-1 project |
| A6 | A run interrupted at any step (process killed, or ETABS killed) resumes after the host-state check and ends with the same model as an uninterrupted run |
| A7 | Besides the change-set approval and the engineer turn, at most one engineer prompt per cycle, where one batched screen counts as one prompt |

If A4 is not met, no release is made until the cause is found and fixed, because time savings are the reason this
system exists.

## 6. Optional start from DXF

When the engineer starts from drawings, the run first creates the model with Sasaah's `tools/dxf-prep` and
`tools/etabs-model` as tool steps, shows the result for approval, and continues at step 2 with that model. This start
is not part of the phase 1 acceptance.
