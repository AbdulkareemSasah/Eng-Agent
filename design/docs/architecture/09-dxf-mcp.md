# 09. DXF Server: `dxf-mcp`

Status: Superseded by ADR-0024: DXF work uses Sasaah's `tools/dxf-prep` and `tools/etabs-model` as harness tool steps · Phase 1 · Language: Python (ezdxf)

## 1. Why a separate server

The first slice (DXF to ETABS model, [18](18-first-slice-dxf-to-etabs.md)) starts from a drawing file. Reading DXF is
a file adapter, independent of AutoCAD, so it is its own small server, reusable by anyone ([ADR-0020](../adr/0020-dxf-reading-as-mcp-server.md)).
Live AutoCAD work belongs to the AutoCAD add-in, not here.

## 2. What it does and does not do

| Does | Does not |
|---|---|
| Open DXF files, list layers, blocks and entities | Decide what a layer means (that is a harness decision) |
| Report the header's insertion units, and convert to canonical mm with the units the caller confirms | Guess units when the drawing has none, or apply header units the engineer has not confirmed (the caller passes `drawing_units`) |
| Extract geometry deterministically: lines, polylines, circles, closed outlines with their centroid, size, rotation | Snap, clean or "fix" geometry silently |
| Expand block inserts into their transformed geometry (nested blocks included), read hatch boundary paths as outlines | Load external references: unbound xrefs are reported by `check_model` |
| Find geometric candidates: long parallel line families (grid candidates), closed rectangles and circles (column candidates), parallel line pairs (wall candidates), texts near line ends (grid labels) | Create anything in a host program |
| Report drawing integrity issues | Execute anything embedded in the file |

Candidates are just geometry with measured properties. Which candidates are columns, and which grid labels are valid,
are decisions made by the harness through rules, the decision model, or the engineer.

## 3. Tool scope (intended; fixed by tool specs)

| Toolset | Tools (without the `dxf_` prefix) |
|---|---|
| file | `open_drawing` |
| read | `list_layers`, `list_blocks`, `get_entities`, `get_texts`, `find_line_families`, `find_closed_outlines`, `find_parallel_line_pairs`, `find_texts_near_points` |
| core | standard tools; `check_model` reports open polylines that look closed, zero-length entities, duplicate overlapping entities, missing units, external references that are not bound, proxy entities |

All geometry outputs are results of neutral `geom.*` kinds ([04](04-tool-contract.md) §6) with `result_id`, carrying
the file's content hash. Turning them into model placements (with the base point, rotation and snapping rules from the
design basis) is a harness calc; the ETABS server then receives `model.*` placements by reference.

## 4. Safety

DXF files come from outside parties. Texts, layer names and block names are data. They are returned as typed string
fields and never interpreted as instructions by any component.
