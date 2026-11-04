---
id: workflow-isolated-footing-design
issue: "B-075"
status: draft        # draft | approved
size: large
risk: r1
---

# Workflow spec / مواصفة سير العمل: isolated footing design (`isolated_footing_design`)

> Written for the owner's review. The block and workflow specification is
> [spec 0010](../specs/0010-design-isolated-footing.md) ("spec §n") and the plan is
> [plan 0010](../plans/0010-design-isolated-footing.md). This page states what the workflow does in the engineer's
> terms; the spec states how it is built and tested.

Issue: B-075 (bootstrap mode, [ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §4) ·
Owner: the owner · Status: Draft

Sources: [10](../../../../design/docs/architecture/10-structural-codes.md) §7 and §9 (the footing check list),
[11](../../../../design/docs/architecture/11-harness-engine.md) §2 and §3 (the block, `ctx.attempts`),
[12](../../../../design/docs/architecture/12-decision-layer.md) §2 (the footing decision),
[13](../../../../design/docs/architecture/13-templates-and-design-basis.md) (the design basis), the ACI 318-14 footing
checks ([plan 0002](../../../structural-codes/docs/plans/0002-aci318-14-footing-checks.md) and its clause specs), the
SBC 304-2018 overlay ([spec 0003](../../../structural-codes/docs/specs/0003-sbc304-2018-footing-overlay.md)), SAFE
through the CSI adapter ([spec 0008](../specs/0008-safe-adapter.md)), and a read-only reading of the Sasaah repository:
`docs/footing-design/README.md` and `tools/footing-design/build.ps1` (the owner's footing tool), and the session reports
`agent-sessions/2026-11-03_0145_etabs-safe_loads-and-footings`, `..._0146_etabs_safe_project` and `_baseline` (cited
"Sasaah footing tool" and "sessions").

## 1. Goal / الهدف

Design every isolated footing under the columns of an analysed ETABS model: size the plan from the service reactions
and the allowable soil pressure, check every footing with the code pack (ACI 318-14, or SBC 304-2018 as an overlay),
fix failures in bounded rounds (rules first, the engineer when no rule applies), and produce a footing schedule with
verdicts, traces and calculation notes for the engineer to review and sign. Every engineering value comes from the
design basis, a reaction read from the model, a calculation with a cited method, or an engineer input. The ETABS model
is never written. Optionally, the column loads are placed on an engineer-prepared SAFE model and analysed as a
cross-check. For building projects with columns on isolated footings, modelled in ETABS.

## 2. Today's manual process and time / الطريقة اليدوية الحالية ووقتها

Today the owner runs the Sasaah footing tool (a command-line tool over the CSI engine) on an analysed ETABS model with a
JSON file of project values: allowable soil pressure, concrete and steel grades, cover, bar diameter, minimum depth,
size step, minimum size, number of footing types. The tool combines service loads (dead, super-dead and live patterns)
and factored loads with load factors written into the tool, sizes each footing with equal projections beyond the column
faces, deepens it until punching and one-way shear pass, chooses a bottom mesh, groups the footings into types (or
checks the office's fixed types), writes a schedule, and builds and analyses a SAFE model through table writes. In the
sessions, the related ETABS-to-SAFE work took about 188 minutes (estimated): 759 column loads moved by table writes, 31
footing areas deleted and drawn again (18 of them first in the wrong orientation), an ETABS instance hung, and a soil
pressure that looked wrong because the loads were on other combinations. Building the tool itself took about 4 to 5
hours over three runs (estimated, sessions). The tool's checks follow ACI 318-19, not the platform's ACI 318-14 scope
(spec Q9).

**Benchmark.** No manual time for designing the footings of one building has been measured (sessions: "unknown").
The owner prepares a footing benchmark like B-1 (two or three past projects, the time of the footing design by hand and
with the tool) before the first release (spec Q16). The workflow records its times per step, per round and per engineer
screen in the journal.

## 3. Inputs / المدخلات

| Input | From | Notes |
|---|---|---|
| ETABS model, analysed | Engineer, command-line `--input` | Opened as a working copy in a hidden instance; never written. A model without analysis results stops the run before any sizing (§4 step 3) |
| Template and design basis | Engineer: template plus values file, confirmed on the page | Fields of spec §4.7: allowable soil pressure and its kind, soil and concrete unit weights, soil depth and surcharge, concrete and steel grades, cover, minimum and maximum plan and depth, size increments, bar diameter and spacings, seismic category, code pack, attempt limits. No value is shipped |
| Service and factored load cases | Engineer, asked each run on the page (answers file) | Names of the model's own combinations (or cases); the load factors are the model's, never the harness's |
| Permission mode | Command-line `--mode` | `work_on_copy` by default; §6 |
| SAFE model (optional) | Engineer, command-line `--safe-model`, with basis `safe.cross_check` | Prepared by the engineer with the footing areas, soil springs and load patterns (spec 0008 Q5); the workflow cannot create or resize footings in SAFE (spec 0008 SG-1, SG-4) |

## 4. Steps / الخطوات

Steps 8 to 12 form one round and repeat, bounded by the basis attempt limit, while some footing fails.

| # | Step | Program or check | What is checked after it | If it fails |
|---|---|---|---|---|
| 1 | Check server builds and tool lists | Engine | Executable hash and tool-list fingerprint equal the adapter's pins | The run does not start |
| 2 | Open a working copy of the ETABS model | ETABS through `sasaah-csi-mcp` | Copy hash equals the original's | Stop; the original is untouched |
| 3 | Check that analysis results exist | ETABS read | Analysis status is finished | Stop: "analyse the model first" |
| 4 | Refuse what v1 cannot design | Harness, from the basis | Seismic design category not D, E or F; no special seismic system (ACI plan Q8, Q16) | Stop with the reason, before any sizing |
| 5 | Read columns, sections and reactions | ETABS reads | Lists complete; every column on a support joint has a rectangular section along the global axes | Footings that cannot be designed are listed as needing the engineer; the rest continue |
| 6 | Ask the service and factored cases | Page (answers file) | Every name exists in the model's reactions | Asked again (bounded) |
| 7 | Initial plan size | Harness calc (service loads, allowable pressure, increments) | Size is a multiple of the increment, within the basis minimum and maximum | Uplift, a net allowable pressure or overburden above the allowable: that footing needs the engineer |
| 8 | Bars and effective depths | Harness calc | At least two bars each way | That footing needs the engineer |
| 9 | Code checks, all footings at once | Code pack: bearing, one-way shear, punching, flexure, minimum steel, development length | Verdicts per footing and case | A failing footing goes to step 10 |
| 10 | Choose a fix per failing footing | Rules, then the engineer on one screen per round | §5 | — |
| 11 | Engineer dimensions (only when chosen) | Page | Values entered with their unit | — |
| 12 | Resize | Harness calc | Next plan, depth or spacing within the basis bounds | At a bound: that footing needs the engineer |
| 13 | Clearance and schedule | Harness calc | Plans do not overlap and keep the basis clear distance | Conflicting footings are marked for the engineer (combined footings are not designed in v1) |
| 14 | SAFE cross-check (optional) | SAFE through `sasaah-csi-mcp`: column loads, analysis, soil pressures and reactions | Loads read back; applied loads against base reactions within the basis tolerance | Shown in the report; never changes a verdict |
| 15 | Engineer review | Page | — | Accept or reject |
| 16 | Report and sign-off | HTML run report with calculation notes; sign-off on the page | Every exception has a reason | Outputs stay `DRAFT` until signed |

## 5. Decisions / القرارات

Point `footing_fix_strategy` (12 §2). Rules hold no number: they read check statuses and whether a size is at its basis
bound. The rules are engineering content: draft until the owner approves them.

| Decision point | Options | Rule (if the answer is known) | Who decides when no rule matches |
|---|---|---|---|
| Fix strategy for a failing footing (step 10) | enlarge the plan; increase the depth; reduce the bar spacing; combine with a neighbor; ask the engineer for dimensions | Plan, depth and spacing all at their bounds → ask the engineer. Only bearing fails, plan not at its bound → enlarge the plan (12 §2). Only one-way or punching shear fails, depth not at its bound → increase the depth. Only flexure or minimum steel fails, spacing not at its bound → reduce the spacing. Only development length fails, plan not at its bound → enlarge the plan | The engineer, on one screen for all failing footings of the round; in shadow mode the decision model's suggestion is shown beside each footing and never applied (12 §3) |
| Engineer review (step 15) | accept; reject | None | The engineer, always |

"Combine with a neighbor" marks the footing for the engineer: v1 designs no combined footing. A footing with a check
that needs the engineer (a code gap, or every SBC 304-2018 check until the owner confirms its clause, overlay spec Q3)
and no failing check is not decided: it is listed for the engineer with the gap.

## 6. Approvals / الموافقات

| Step | `work_on_copy` (default) | `approve_each_write` | `autonomous_logged` |
|---|---|---|---|
| 1 to 13 (ETABS reads, calcs, checks) | No approval: nothing is written | No approval | No approval |
| 10 Fix strategy | Rules or the engineer screen | Same | Same (no mode resolves a decision) |
| 14 SAFE loads | One change-set approval listing the loads and combinations | Also one preview per write | Resolved by the mode, logged |
| 14 SAFE analysis | No approval | One approval | Direct |
| 15 Review | On the page | On the page | On the page |
| 16 Sign-off | Always asked | Always asked | Always asked |

In every mode the ETABS model is only read, and SAFE is written only in a working copy in the run folder.

## 7. Outputs / المخرجات

- The footing schedule: per footing its column, position, plan, depth, bars each way, status, how each size was
  reached (calc or engineer) and every decision with who took it; footings that need the engineer with the reason.
- The verdict sets of every round (with their traces), the calculation notes rendered from them (English with Arabic
  labels), and the decision records.
- When the SAFE stage ran: the working SAFE file, the read-back of the loads, the equilibrium comparison and the raw
  soil pressures (informational: no verdict until the table's columns are confirmed locally, spec 0008 Q8).
- The HTML run report. Outputs stay `DRAFT` until signed and keep "DRAFT SOURCES" while any check, calc or rule is draft.

"Correct" means: every footing marked `PASS` passed every check of the chosen code pack for every selected case with
the sizes in the schedule, every size came from a calc or the engineer, and every input value has a source.

## 8. Acceptance / معايير القبول

| Id | Criterion | How it is measured |
|---|---|---|
| F1 | Every footing in the schedule is `PASS` on every check for every selected case, or is listed for the engineer with its reason | CI: fake-host workflow scenarios (enlarge, deepen, spacing, limits, gaps, SBC); local: a copy of a real analysed model |
| F2 | Every engineering value has a source (basis, reaction, calc or engineer input) | CI: the value-source audit over every test journal; local: the same audit |
| F3 | The ETABS model is never written; SAFE is written only in a working copy, only through allowlisted tools | CI: the journal audit and the allowlist contract test; local: file hashes before and after |
| F4 | At most one engineer screen per round besides the review and sign-off | CI: prompt count from the test journals; local: the same count |
| F5 | A run killed at any step resumes and ends with the same schedule | CI: crash matrix against the fakes |
| F6 | The schedule matches the engineer's own design of the same footings, differences explained | **Local only**: the footing benchmark (spec Q16) |
| F7 | Engineer time at most half of the benchmark time | **Local only**: the footing benchmark with the journal timings |

## 9. Out of scope / خارج النطاق

- Rectangular footings with unequal sides (until a band-rule check exists), combined, strip and mat footings, pile caps,
  eccentric or rotated columns, circular columns, pedestals, sloped or stepped footings.
- Grouping footings into types and the office's fixed type table (spec Q7).
- Seismic design categories D to F and special seismic systems (ACI plan Q8, Q16).
- Generating load combinations; any write to ETABS; creating or resizing footings in SAFE; SAFE slab design results.
- Drawings and DXF output.
