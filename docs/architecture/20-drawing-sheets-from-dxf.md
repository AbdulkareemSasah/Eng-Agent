# 20. Drawing Sheets from DXF Templates

Status: Proposed ([ADR-0037](../adr/0037-drawing-sheets-from-dxf-templates.md)) · Phase 5 · Built after the model
workflows, the calculation report and the host servers are complete

## 1. Goal

Produce structural sheets (plan, schedule, details, sheet name) as DXF files that carry the office's drawing identity,
with every value taken from the run's results. The agent fills and adjusts office templates; it never invents a
drawing style.

## 2. Scope

| In scope (first stage) | Out of scope |
|---|---|
| Columns, isolated footings, tie beams and beams: plan, schedule beside it, the details the sheet needs, sheet name | Slab sheets (a later stage with its own design; slabs vary too much for one template) |
| One DXF file per sheet, without a title block | Title blocks and merging sheets into one file (done by the engineer; a merge tool is a later decision) |
| Reading the engineer's source plan to create the ETABS or SAFE model | Live AutoCAD work (the AutoCAD add-in, [15](15-desktop-addins.md)) |

## 3. Flow

1. The engineer draws the source plan as DXF by the layer convention (§4): grids, columns, tie beams, beams and slab
   outlines. A floor that differs has its own plan; repeated floors share one plan and name the stories it covers.
2. The run creates the ETABS model from the source plan with Sasaah's `tools/dxf-prep` and `tools/etabs-model`
   ([ADR-0024](../adr/0024-harness-on-existing-sasaah-servers.md), [18](18-first-slice-dxf-to-etabs.md) §5). Slab
   outlines enter the model so the analysis is complete. The created model is shown for approval.
3. The model edit cycle runs: analysis, design, section changes, each written only after approval
   ([18](18-first-slice-dxf-to-etabs.md)). Footings take their reactions through the SAFE route.
4. Grouping (§5) and reinforcement selection (§6) produce the member types and their reinforcement.
5. The sheet writer (§7) copies the source plan and the office template, updates sizes, adds labels, fills the
   schedule and details, and writes one DXF per sheet.
6. The sheets are an output of the run: listed in the run report with the revision they were made from (§8).

## 4. The layer convention

The convention is the contract between the engineer's drawings and the platform. It is a versioned document owned by
the engineer and stored with the templates; a drawing that breaks it is refused with a list of what was not understood,
never repaired silently.

- One layer per element kind (grid, column, tie beam, beam, slab outline, opening), with fixed names.
- Drawing units are stated in the template and confirmed in the design basis. The default is metres.
- A member's label and section are one text beside it, in the form the template states for its kind, for example
  `B1 (20×60)` or its Arabic form `ك1 (20×60)`. Columns, tie beams and footings each have their own form.
- Values a plan cannot show (story heights, materials, loads, founding depth) come from the design basis
  ([13](13-templates-and-design-basis.md)), not from the drawing.
- A snapping tolerance for ends that should meet is a design-basis value. Every snapped point is reported.

## 5. Grouping members into types

After design, a calc groups members into types (C1, C2, B1, F1) and proposes the labels; the engineer approves them.
Three rules apply together:

1. Members with the same section and the same reinforcement are one type.
2. Members that are close are unified upward to the heavier one.
3. The number of types per kind does not exceed the limit the engineer sets in the design basis.

The calc states, for each member moved to a heavier type, what it needed and what it received.

## 6. Reinforcement selection

The host program reports a required steel area, not a bar arrangement. The arrangement is chosen in this order:

1. The code limits (minimum and maximum ratios, minimum bar count, tie and stirrup spacing) from `structural-codes`
   ([10](10-structural-codes.md)).
2. The engineer's rules in the design basis (allowed diameters, preferred spacings, detailing habits).
3. For what remains open, a decision point: the platform proposes and the engineer answers
   ([12](12-decision-layer.md)).

No bar arrangement is invented. A case no rule covers is an explicit gap that asks the engineer.

## 7. The sheet writer

- Input: the source plan, the office template for the sheet kind, and results by reference.
- It keeps the geometry the engineer drew. It changes only drawn section sizes and labels, and adds the schedule,
  details and sheet name from the template.
- Schedules are uniform tables defined once in the template; the writer fills rows and does not change their layout.
- Layers, text styles, dimension styles, linetypes and blocks come from the template only.
- A dimension is rewritten from the geometry it measures, never left with stale text.
- The output passes an integrity check before it is offered: no entity outside the convention's layers, no missing
  style, no label without a schedule row and no schedule row without a label.

## 8. Traceability

Each sheet records the run, the model revision and the result ids it was made from. When the model has a later
accepted revision, the report marks the sheet as out of date. A sheet is signed off through the same approval page as
other outputs ([14](14-harness-ui.md)).

## 9. Dependencies and order

- Sasaah's `tools/dxf-prep` and `tools/etabs-model` must cover the layer convention; gaps go to Sasaah.
- The model edit cycle, the column and footing workflows and the calculation report come first.
- Build order when the phase starts: the layer convention and one template; the sheet writer on hand-written values
  for one sheet kind (it needs no host program and proves the idea early); grouping and reinforcement selection; then
  the link to the model results.

## 10. Open questions

| Id | Question |
|---|---|
| Q1 | The exact layer names and label forms per element kind (the engineer writes the convention) |
| Q2 | How "close" is measured for upward unification in §5 rule 2 |
| Q3 | Which details each sheet kind needs and how a detail is chosen from the template |
| Q4 | Whether the sheet writer is a harness component or a Sasaah tool beside `tools/dxf-prep` |
| Q5 | The later merge tool: one file with layouts, or sheets as external references |
