---
id: workflow-column-design
issue: "B-083"
status: draft        # draft | approved
size: large
risk: r1
---

# Workflow spec / مواصفة سير العمل: column design in ETABS, Revit update by reference (`column_design`, `column_revit_update`)

> Written for the owner's review. The block specification is [spec 0013](../specs/0013-column-workflow.md) and the
> plan is [plan 0013](../plans/0013-column-workflow.md). This page states what the workflow does in the engineer's
> terms; the spec states how it is built and tested.

Issue: B-083 (bootstrap mode, [ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §4) ·
Owner: the owner · Status: Draft

Sources: [19](../../../../design/docs/architecture/19-roadmap-and-spikes.md) §1 phase 3 ("design columns in ETABS and
update Revit by reference"), the [edit-cycle workflow](model-edit-cycle.md) ("EC §n"), the calcs of
[spec 0003](../specs/0003-calcs.md), the decision layer of [spec 0005](../specs/0005-decisions.md), the Revit adapter
[spec 0011](../specs/0011-revit-adapter.md), the SAP2000 coverage check [spec 0012](../specs/0012-sap2000-adapter.md),
the ACI 318-14 column checks of [plan 0004](../../../structural-codes/docs/plans/0004-aci318-14-column-checks.md),
[ADR-0005](../../../../design/docs/adr/0005-pass-by-reference.md) (pass by reference),
[ADR-0018](../../../../design/docs/adr/0018-permission-modes.md) (permission modes), and the Sasaah session evidence
(`agent-sessions/_baseline/REPORT.md` and the session reports of 2026-11-03 in the Sasaah repository, read-only, cited
"baseline").

## 1. Goal / الهدف

For a reinforced-concrete or steel building whose frame model is in ETABS and whose drawings are in Revit: check the
columns the engineer selects, propose section changes for the failing ones, apply the approved changes to ETABS through
the edit cycle's write path, run analysis and design again until the engineer accepts; then give the matching Revit
columns the accepted sections, with every length passed by reference from the ETABS read and every write read back.
No value is typed twice and no value comes from the agent.

The work is two runs of the harness: `column_design` (ETABS) and then `column_revit_update` (Revit, reading the accepted
ETABS revision). Two runs, because the Revit adapter can work only in `approve_each_write` (no save tool, spec 0011
§4.12), while ETABS work defaults to `work_on_copy`.

## 2. Today's manual process and time / الطريقة اليدوية الحالية ووقتها

Today the engineer reads frame forces and the ETABS design, decides new sizes, changes sections in ETABS, re-runs, and
then changes the Revit types by hand. In the reviewed sessions, "load combinations and review of columns and beams"
took 146 agent minutes and 116 engineer minutes (baseline §3); a column sizing tool divided service loads by fixed
thresholds (an engineering rule that was never sourced, not adopted, S-12 OQ-G14); and the engineer found columns
rotated by 90 degrees after a check had passed, because the check compared a constant with itself (baseline §5.5).
The manual time for the same work was not measured.

**Benchmark.** Proposed: a B-1-style set (EC §2) of column reviews on past projects, timed by hand and through the
workflow (owner queue, spec Q11). The journal records the times per step and per engineer turn as in the edit cycle.

## 3. Inputs / المدخلات

| Input | From | Notes |
|---|---|---|
| ETABS model file | Engineer, `--input` | Opened as a copy in a launched instance (EC §3) |
| Revit model file (second run) | Engineer, `--input` | Non-workshared; opened as a copy in the engineer's attended Revit (spec 0011 AC23) |
| Template and design basis | Engineer, confirmed on the page | Fields of spec 0013 §4.7: materials, effective length factor, rounding increment, tolerances, mapping offset, limits, attempts. No value is shipped |
| Column scope | Engineer answers file, once per run | Which frames (names, stories or current sections), which load combinations, and the statement that none is part of a special seismic system |
| Reinforcement layout per concrete section | Engineer answers file | Bar counts per face, bar area and cover distance, each from the basis or entered with a source; ETABS has no allowlisted read for it (gap CW-G2) |
| Required section size per failing column | Engineer answers file, per cycle | A required size only; the rounding calc gives the size, the model must already hold a section of that size (gap CW-G3) |
| Permission mode | `--mode` | `column_design`: any mode, default `work_on_copy`. `column_revit_update`: `approve_each_write` only |

## 4. Steps / الخطوات

### 4.1 `column_design` (ETABS)

Steps 1 and 2 run once per run; steps 3 to 14 form one cycle and repeat until the engineer accepts at step 10.

| # | Step | Program or check | What is checked after it | If it fails |
|---|---|---|---|---|
| 1 | Check server builds; open the model; save a working copy | Engine; ETABS through `sasaah-csi-mcp` (EC steps 1, 2) | Builds pinned; copy hash equals the original's | The run does not start; nothing is written |
| 2 | Ask for the column scope and the reinforcement layouts | Engineer answers file | Names exist; combinations exist; a layout for every concrete section in scope | Asked again (bounded by the basis) |
| 3 | Read the model state; compare with the last revision | ETABS reads; difference report (EC steps 3, 4) | Read complete | Differences are engineer changes: shown, never overwritten |
| 4 | Select the columns | Harness calc | Every selected frame is vertical within the basis length tolerance; others listed as excluded | Nothing selected: the scope is asked again |
| 5 | Run analysis and design | ETABS (EC steps 11, 12; the engine saves first) | The runs end; no dialog waits | Unknown outcome: the engineer reconciles (EC D-4) |
| 6 | Read frame forces of the selected columns and combinations, analysis messages and the host design results | ETABS reads | Every selected column has forces for every selected combination | Missing rows are listed; those columns get `NEEDS_ENGINEER` |
| 7 | Host verdicts | Harness calc | Steel: host ratio against the basis limit. Concrete: `NEEDS_ENGINEER` (the host reply holds beams only, gap CW-G1) | — |
| 8 | Code checks (ACI 318-14, draft) | `structural-codes` through the harness | Maximum axial strength, axial force with uniaxial flexure, longitudinal reinforcement limits, per column, combination and end | Biaxial moments, slender columns, tension, circular and steel sections: `NEEDS_ENGINEER` with the gap id |
| 9 | Summaries | Harness calc (design summary, once for host and once for code verdicts) | Governing ratio, failing members, changes from the previous cycle | — |
| 10 | Engineer turn | Approval page | — | Accept (go to 15); revise (go to 11); "I edited by hand: continue" (next cycle at 3) |
| 11 | Ask for required sizes of the columns to change | Engineer answers file | Each names a selected column | Asked again (bounded) |
| 12 | Round and match | Rounding calc; section match calc | Size is the smallest basis multiple not below the required size; a model section of that shape, size and material exists | None exists: the item is refused with gap CW-G3; the engineer defines it in ETABS and continues with "I edited by hand" |
| 13 | Decide per column | Decision rules, then the engineer | `keep`, `change_section` or `refer_to_engineer` (§5) | — |
| 14 | Apply the change set | Edit cycle write path (EC steps 6 to 10): approval, revision save, writes, read-back, save | The model holds exactly the approved sections | EC D-2; then the next cycle starts at 3 |
| 15 | Promote, write the design record, sign off | EC steps 16, 17 | The original unchanged since the copy | Outputs stay `DRAFT` until signed |

### 4.2 `column_revit_update` (Revit)

| # | Step | Program or check | What is checked after it | If it fails |
|---|---|---|---|---|
| R1 | Check builds and the mode | Engine | Both servers pinned; mode `approve_each_write` | The run does not start |
| R2 | Open the promoted ETABS model as a copy and read it | ETABS reads | Its fingerprint equals the accepted revision in the design record | Stop: ETABS changed after the design run; run `column_design` again |
| R3 | Open a copy of the Revit model and read columns, types and parameters | Revit through `sasaah-revit-mcp` | Non-workshared; parameter roles mapped | Stop with the reason |
| R4 | Map ETABS columns to Revit columns | Harness calc `harness.frame_element_map` (spec 0011 §4.11) | Pairs, ambiguous, unmatched, conflicts | Ambiguous, unmatched or conflicting columns are never written; the engineer decides whether to continue with the matched pairs |
| R5 | Plan the Revit changes | Harness calc | For each pair whose Revit dimensions differ from ETABS: reuse an existing type of equal size, or a new type duplicated from the current one, then assign | Unmapped roles, steel or other shapes, name clashes: listed, not written |
| R6 | Approve the map and the changes | Approval page | Bound to both model states; single items can be rejected | Rejected: nothing is written |
| R7 | Write | Revit: duplicate type, set type sizes, change element types; each write previewed and confirmed in Revit's own dialog | Each write read back by the adapter | Declined in Revit: not applied, not retried; timeout: reconciled by reading |
| R8 | Read back the whole plan | Harness calc | Every planned element has its type and size; no other column changed type | The engineer chooses accept or abandon (Revit's undo is the engineer's) |
| R9 | Report and sign-off | Run report | The Revit document is **unsaved**: the engineer saves it (gap CW-G6) | Outputs stay `DRAFT` until signed |

## 5. Decisions / القرارات

Rules and the engineer only in v1 (no model tier, spec Q8). No rule holds a number; every threshold is a basis field
used by a calc.

| Decision point | Options | Rule (if the answer is known) | Who decides when no rule matches |
|---|---|---|---|
| Per column after step 12 | keep; change section; refer to the engineer | All verdicts `PASS` and no proposal → keep. A `FAIL` and a matched proposal → change section (still approved at step 14) | Engineer (one batched screen per cycle) |
| Read-back, analysis messages (steps 14, 6) | as EC D-2, D-3 | as EC | Engineer |
| Engineer turn (step 10) | accept; revise; edited by hand | None | Engineer, always |
| Map result (R4) | continue with matched pairs; stop | No ambiguous, unmatched or conflicting selected column → continue | Engineer |
| Revit read-back (R8) | accept; abandon | `PASS` → accept | Engineer |

## 6. Approvals / الموافقات

| Step | `work_on_copy` | `approve_each_write` | `autonomous_logged` |
|---|---|---|---|
| 14 ETABS change set and writes | as EC §6 | as EC §6 | as EC §6 |
| 10 Engineer turn, 15 promotion and sign-off | page, always | page, always | page, always |
| R6 Revit map and changes | refused (mode) | page | refused (mode) |
| R7 Each Revit write | — | preview on the page, then Yes in Revit's own dialog (attended) | — |
| R9 Sign-off | — | always asked | — |

## 7. Outputs / المخرجات

- ETABS: the accepted revision, promoted to the original with a backup (EC §7); the design record (accepted
  fingerprint, changed columns, summaries, verdicts).
- Revit: the copy opened in Revit with the new types assigned, unsaved until the engineer saves it.
- Two run reports: the columns, their verdicts with clause ids or host source, every proposed and applied size with its
  source chain (required size, rounding, model section), the map, the Revit changes and their read-back. Outputs stay
  `DRAFT` until signed and keep "DRAFT SOURCES" while the calcs, rules and code checks are draft.

"Correct" means: ETABS holds exactly the approved sections plus the engineer's own changes; every verdict comes from
the host or a cited code check; every Revit length equals the ETABS section it references, read back from Revit; no
column outside the approved set changed.

## 8. Acceptance / معايير القبول

| Id | Criterion | How it is measured |
|---|---|---|
| CA1 | ETABS holds exactly the approved section changes and nothing else | CI: fake-host workflow, read-back and difference report. Local: an owner project |
| CA2 | Every verdict shown has a source (host reply or a code check id with its clause) and no verdict is computed by the workflow | CI: verdict-source audit over the test journals. Local: the same audit |
| CA3 | Every engineering value written to ETABS or Revit came from a reference | CI: value-source audit (EC A3) over both runs. Local: the same |
| CA4 | Every changed ETABS column whose Revit column matched has, after read-back, a Revit type of the same size; no other Revit column changed type | CI: fake-host workflow with the Revit fake. Local: an owner project, attended |
| CA5 | An ambiguous, unmatched or conflicting column is never written in Revit | CI: golden map cases and a workflow test. Local: an owner pair of models |
| CA6 | A hand edit in ETABS between cycles is kept; an ETABS change after the design run stops the Revit run | CI: fake hand edit; fingerprint mismatch. Local: one hand edit per project |
| CA7 | A run killed at any step resumes with the same result | CI: crash matrix against both fakes. Local: process kill at the Revit writes |
| CA8 | Column review time against the manual time | **Local only**, once the owner prepares the benchmark (spec Q11) |

## 9. Out of scope / خارج النطاق

- SAP2000 as the frame model (spec 0012 gaps SP-3 and SP-5); IDEA StatiCa; SAFE.
- Defining new ETABS sections (H-G1), materials or reinforcement in ETABS; reducing sections that pass (no source for
  when a section is "too large").
- Biaxial bending, slenderness effects, axial tension, spiral and special-seismic columns, transverse reinforcement
  checks, steel code checks (the code pack's gaps, plan 0004 §6).
- Revit: steel column types, rebar, materials, moving or creating elements, saving or closing the document, workshared
  models, writing the ETABS link into Revit (spec 0011 Q5).
- Automatic sizing: a required size is the engineer's input in v1.
