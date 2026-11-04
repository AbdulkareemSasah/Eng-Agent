---
id: workflow-model-edit-cycle
issue: "B-066"
status: draft        # draft | approved
size: large
risk: r1
---

# Workflow spec / مواصفة سير العمل: model edit cycle (`model_edit_cycle`)

> Written for the owner's review. The block specification is
> [spec 0007](../specs/0007-model-edit-cycle.md) and the plan is [plan 0007](../plans/0007-model-edit-cycle.md).
> This page states what the workflow does in the engineer's terms; the spec states how it is built and tested.

Issue: B-066 (bootstrap mode, [ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §4) ·
Owner: the owner · Status: Draft

Sources: [18](../../../../design/docs/architecture/18-first-slice-dxf-to-etabs.md) (the slice, cited "18 §n"),
[ADR-0025](../../../../design/docs/adr/0025-first-workflow-edit-cycle.md),
[ADR-0018](../../../../design/docs/adr/0018-permission-modes.md),
[ADR-0026](../../../../design/docs/adr/0026-project-lane-for-tools.md),
[ADR-0027](../../../../design/docs/adr/0027-phase-1-interface.md),
[spike S-12](../../../../spikes/S-12-sasaah-tool-inventory/REPORT.md) (the tools), and the Sasaah session baseline
(`agent-sessions/_baseline/REPORT.md` and `DESIGN-NOTES.md` in the Sasaah repository, cited "baseline").

## 1. Goal / الهدف

Take one existing ETABS model through repeated cycles of edit, save, analysis, design and review until the engineer
accepts a revision; then promote that revision to the original file and sign the outputs. Every value written has a
source, every revision is a new file, and no change the engineer made by hand is lost or written over (18 §1,
ADR-0025). For any building project whose model is in ETABS and reachable through `sasaah-csi-mcp`.

## 2. Today's manual process and time / الطريقة اليدوية الحالية ووقتها

Today the engineer asks an agent (or works by hand): change sections, loads or combinations; wait; check; often edit
by hand; run analysis and design again (often by hand, because design runs failed with `model_locked` in 7 of 7
attempts and analysis timed out in 10 of 74 runs); read the results; repeat. In the reviewed sessions, the edit cycles
of one task took 342 agent minutes and 500 engineer minutes, and 45 engineer messages were "I ran it" or "done"
(baseline §3 and §5.1). The manual time for the same changes was never measured (baseline §10).

**Benchmark.** B-1 (18 §5): three past projects, five to ten typical change requests each, with the time those
changes took by hand and in agent chats, prepared by the owner before the first release. The workflow records its own
times per step, per cycle and per engineer turn in the journal (spec 0007 §4.9), so the same requests can be timed
end to end, engineer time included (baseline ب1).

## 3. Inputs / المدخلات

| Input | From | Notes |
|---|---|---|
| ETABS model file | Engineer, command-line `--input` | Never opened in the engineer's own ETABS: a hidden or visible instance that the run launches opens a copy (S-12 §1 step 2, baseline ج2) |
| Template and design basis | Engineer: template plus values file, confirmed on the page | Fields of spec 0007 §4.8: comparison tolerances, change-set bounds, ratio and drift limits, design kinds, attempt limits. No value is shipped (spec 0004 §4.8) |
| Change set | Engineer, or a coding agent from the engineer's words, as a JSON answers file (`resume --answers`) | One per cycle; edit kinds of §4.1 below; each value from the design basis or entered as an engineer input for this cycle |
| Permission mode | Command-line `--mode` | `work_on_copy` by default; §6 |
| `sasaah-csi-mcp` build | Pinned by the adapter (spec 0002 §4.3.4) | Checked before any write (§4, step 1) |

### 3.1 Edit kinds in v1 (18 §2 against S-12 §2 and spec 0002 §4.6.2)

The owner confirms this list (owner queue OQ-Q4). A kind without a tool is refused before approval with its gap id;
it is built through the project lane (ADR-0026) or a Sasaah change, never improvised.

| Edit kind (18 §2) | In v1 | Values and their sources |
|---|---|---|
| Assign a section to frames | Yes | Frames by name or by a selection (story, current section); the section exists in the model |
| Assign a section to areas | Yes | Areas by name or by a selection (story, current section, slab or wall); the section exists in the model |
| Change a wall thickness (define or change a wall section) | Yes | Thickness from the basis or engineer input; material exists in the model. Changes every wall that uses the section (S-12 §2) |
| Change a slab thickness; define a frame section, an area section or a material | **No** (gap H-G1) | Needs typed Sasaah tools or confirmed `spec` keys |
| Uniform load on frames or areas | Yes, gravity direction only | Value from the basis or engineer input; pattern exists or is added in the same set. Other directions and point loads: gap H-G2 |
| Add a load pattern | Yes, types dead, live, seismic, wind, snow, other | Self-weight multiplier from the basis or engineer input. Types superimposed dead and roof live: gap H-G3. Change or delete a pattern: no tool (OQ-G8) |
| Add or replace a load combination; delete a combination | Yes (type range: gap H-G3) | Scale factors from the basis or engineer input. A delete is always asked |
| Change restraints | Yes | Joints by name; six restraint flags |
| Seismic load parameters | **No** (OQ-G8, CG-1) | No Sasaah tool; never a table write |

Out of scope (18 §2): adding, moving or deleting objects; stories and grids; other host programs; code checks
(phase 2); the optional start from DXF (18 §6).

## 4. Steps / الخطوات

Steps 1 and 2 run once per run; steps 3 to 15 form one cycle and repeat until the engineer accepts (18 §4).

| # | Step | Program or check | What is checked after it | If it fails |
|---|---|---|---|---|
| 1 | Check server builds and tool lists | Engine, before the run starts | Executable hash and tool-list fingerprint equal the adapter's pins | The run does not start; nothing was written |
| 2 | Open the model; save a working copy in the run folder | ETABS through `sasaah-csi-mcp` | The copy's file hash equals the original's; the baseline revision is recorded | The run stops; the original is untouched |
| 3 | Read the model state | ETABS reads | The read is complete (no list cut at the server's limit) | Stop with the reason; nothing is written |
| 4 | Compare with the last recorded revision | Harness calc (difference report) | — | Differences are engineer changes: shown and recorded, never overwritten |
| 5 | Ask for and validate the change set | Engineer answers file; harness calc | Types, units, bounds from the basis; objects and sections exist; kinds are supported; conflicts with engineer changes are marked | An invalid set is refused with its reasons and asked again (bounded by the basis) |
| 6 | Approve the change set, with the differences | Approval page | The approval is bound to this change set and this model state; single items can be rejected | Rejected: nothing is written; the engineer turn follows |
| 7 | Save as the next revision | ETABS save to a new file | File hash and fingerprint recorded | Stop; the previous revision file is intact |
| 8 | Apply the edits (unlock first when the model is locked after analysis) | ETABS writes, one call per object | Before the first write, the model equals the approved state | If the model changed since the approval, the cycle goes back to step 3 |
| 9 | Read back and check | ETABS reads; harness calc (read-back check) | Every written value matches the change set and nothing else changed | Mismatch: the engineer chooses (§5, D-2) |
| 10 | Save | ETABS save | File hash recorded | Stop with the reason |
| 11 | Run analysis | ETABS, dedicated long-call server | The run ends; no dialog waits | A timeout is an unknown outcome: reconcile before anything else (§5, D-4) |
| 12 | Run design | ETABS (steel, concrete, or both, from the basis) | The run ends | Same as step 11 |
| 13 | Read results | ETABS reads | Analysis messages, drifts, design results stored | Stop with the reason |
| 14 | Summarize | Harness calcs | Governing ratios, failing members, drift against the basis limit, changes from the previous revision | — |
| 15 | Engineer turn | Approval page, three buttons | — | Accept; ask for more edits; or "I edited by hand: continue". A new cycle starts at step 3 |
| 16 | Promote the accepted revision | File copy with backup | The original has not changed since the copy was taken | Stop; nothing is copied |
| 17 | Report and sign-off | HTML run report; sign-off on the page | Every exception has a reason | Outputs stay `DRAFT` until signed |

## 5. Decisions / القرارات

Phase 1 decides with rules and the engineer only (ADR-0025 decision 5). No rule holds a number: every threshold is a
design basis field.

| Decision point | Options | Rule (if the answer is known) | Who decides when no rule matches |
|---|---|---|---|
| D-1 Change set invalid (step 5) | ask again; stop the cycle | Always ask again while attempts remain (basis `attempts.change_set`) | Engineer, by a corrected answers file |
| D-2 Read-back result (step 9) | continue; restore the previous revision and return to step 3; stop the cycle | `PASS` → continue | Engineer (one screen) |
| D-3 Analysis messages (step 13) | continue; stop the cycle | No error-level message → continue | Engineer (one screen) |
| D-4 Unknown outcome of a write, analysis or design (steps 8, 11, 12) | applied; not applied; abandon | None: the engine's reconciliation decides when the model state shows it, else the engineer | Engineer (engine screen) |
| D-5 Model changed after the approval (step 8) | back to step 3 | Always (bounded by `attempts.approval_void`) | — |
| D-6 Engineer turn (step 15) | accept; more edits; edited by hand | None | Engineer, always |

At most one engineer screen per cycle besides the change-set approval and the engineer turn (A7); D-2 and D-3 are shown
together when both are open.

## 6. Approvals / الموافقات

| Step | `work_on_copy` (default) | `approve_each_write` | `autonomous_logged` |
|---|---|---|---|
| 6 Change set | On the page | On the page | Resolved by the mode, logged |
| 8 Each write | Covered by the change-set approval | Also one preview approval per write | Direct, logged |
| 8 Unlock after analysis; deleting a combination | Covered by the change-set approval (listed as items) | Covered by the change-set approval | Asked separately (always-ask list, ADR-0018) |
| 11, 12 Analysis and design | No approval | One approval each | Direct |
| 15 Engineer turn | On the page | On the page | On the page |
| 16 Promotion | Always asked | Always asked | Always asked |
| 17 Sign-off | Always asked | Always asked | Always asked |

In every mode the run writes only to copies in the run folder; the original changes only at step 16.

## 7. Outputs / المخرجات

- One revision file per cycle in the run folder (never written over), each with its identity, fingerprint and file
  hash; the accepted revision copied to the original's path with a backup of the original.
- Per cycle: the difference report (engineer changes), the change set check, the read-back check, the analysis and
  design summaries.
- The HTML run report: changes, results, the source of every value, decisions, and timings per step, per cycle and per
  engineer turn. Outputs stay `DRAFT` until signed, and keep "DRAFT SOURCES" while the calcs and rules are draft.

"Correct" means: the model holds exactly the approved changes plus the engineer's own changes, every written value
has a source, and every result shown was read from the saved model after the write.

## 8. Acceptance / معايير القبول

18 §5. What CI proves with the synthetic fake server and what only the owner's local test proves:

| Id | Criterion | How it is measured |
|---|---|---|
| A1 | The model holds exactly the requested changes and nothing else | CI: read-back check and difference report against the expected effects in fake-host workflow tests. Local: every B-1 request on real ETABS |
| A2 | Every analysis and design run completes, or ends as unknown outcome followed by reconciliation; no dialog wait; a stale build stops before any write | CI: fake timeouts, save before analysis, wrong build pin. Local: real runs, dialogs, the long-call server |
| A3 | Every engineering value written came from a reference | CI: the value-source audit over every test journal. Local: the same audit over the B-1 journals |
| A4 | Median request-to-accepted-revision time, engineer included, at most 50% of the B-1 time | **Local only**: B-1 with the journal timings |
| A5 | A hand edit between cycles always appears in the next differences and is never written over | CI: fake hand edits between cycles, during an approval wait, and while the run is stopped. Local: a hand edit in every B-1 project |
| A6 | A run killed at any step resumes and ends with the same model as an uninterrupted run | CI: engine kill at every step against the fake. Local: process kill and ETABS kill |
| A7 | At most one extra engineer prompt per cycle | CI: prompt count from the test journals. Local: the B-1 journals |

## 9. Out of scope / خارج النطاق

- Edit kinds marked "No" in §3.1, and any kind not in that table (new kinds go through the project lane, ADR-0025
  pre-mortem).
- Code checks, SAFE, Revit and other hosts; the start from DXF.
- Promotion by replaying writes (gap E-G1): the accepted revision is copied as a file.
- Automatic fixing of failing members: the engineer decides at the engineer turn.
