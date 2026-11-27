# 13. Templates and the Design Basis

Status: Proposed · Phase 1 · Lives in: `eng-harness`

## 1. Two ideas

- A **template** is a reusable, versioned file of project knowledge: code and edition, materials, section catalogs,
  load patterns and combinations, limits, analysis settings, modeling conventions, drawing conventions.
- A **design basis** is the exact set of values one run uses: the template's values, the engineer's overrides, and
  the values asked at run start. Every field records where it came from.

Templates remove repetition; the design basis removes assumptions (P8).

## 2. Template content

Templates are YAML data files validated against a schema (Pydantic). They contain data only: no code, no
expressions. Every value carries a citation (code clause, standard, or the owner's documented practice).

| Section | Examples |
|---|---|
| `meta` | name, version (semver), description, author, code pack and edition (for example `sbc304_2018`) |
| `materials` | concrete grades with `fc_MPa` and `E_MPa` (a literal value with its citation); reinforcement with `fy_MPa`, `Es_MPa`; unit weights |
| `sections` | catalogs: rectangular and circular columns, beams (width and depth), slabs and walls (thickness), with names; the default section per element type when the drawing does not show one |
| `loads` | load patterns (dead, superimposed dead, live, roof live, wind, seismic) and their default area loads by occupancy |
| `combinations` | the explicit combination set (phase 1); from phase 2 optionally a reference to a code pack's combination generator |
| `limits` | drift limits, deflection limits, utilization limit (`ratio_limit`), minimum dimensions |
| `analysis` | mass source, diaphragms, cracked-section stiffness modifiers, P-delta option |
| `modeling` | cover, snapping tolerance to grids, merge tolerance for joints, rounding increment for new section sizes, naming conventions |
| `drawing` | DXF layer name patterns and their meaning hints (used by rules), expected drawing units, how the base point is chosen (for example the intersection of grids A and 1) |
| `ask_each_run` | fields that must always be entered at run start, for example allowable soil pressure or number of stories |

A template may `extend` another and override fields. Templates shipped with the harness live in its `templates/`
folder; the engineer's own templates live in the user's templates folder. A run records the exact template name,
version and content hash.

## 3. Design basis

- Built at run setup from: chosen template, then engineer overrides, then values asked (`ask_each_run` plus anything
  the workflow declares as required and the template does not provide).
- Stored as a result of kind `basis.design_basis/1`, so blocks and tools read it by reference
  (`ctx.basis.ref("limits.drift_ratio")`).
- Every field carries `source`: `template:<name>@<version>`, `engineer:<name>@<timestamp>`, or `model:<result ref>`
  (read from a host model), and `confirmed: true` once the engineer has seen it on the setup screen.
- The engine refuses to start a run while any required field is missing or unconfirmed.

## 4. Run setup flow

1. Choose the workflow.
2. Choose a template (or the last one used for this project).
3. The setup screen shows every value the workflow will use, grouped by section, with its source. Values asked each
   run are empty and required.
4. The engineer fills the missing values, changes anything for this project, and confirms each section.
5. Choose the permission mode and the models or files to work on.
6. Start. The confirmed basis is frozen for the run. Changing it later starts a new run.

In phase 1 there is no setup screen: the basis is shown and confirmed on the local page of
[ADR-0027](../adr/0027-phase-1-interface.md), and the other choices are command-line options. "Setup screen" in this
document means that page until the full UI exists.

## 5. Validation

- Schema and bounds for every field, with canonical units; a citation on every value.
- From phase 2: consistency with the chosen code pack (combinations valid for the code, materials within the code's
  ranges, else flagged `NEEDS_ENGINEER`).
- Values detected from inputs (for example the DXF header's units) are shown on the setup screen as detected and must be
  confirmed like any other value.
- Template changes go through the normal process when they are shipped templates; user templates are validated on
  save.
