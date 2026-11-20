# ADR-0037: Drawing sheets are produced from DXF templates

Status: Proposed · Date: 2026-11-20 · Deciders: owner

## Context

The platform is strong on models and weak on drawings. An agent works well on one DXF file that holds one sheet or
detail without a title block, but it does not keep a uniform drawing identity across details. The owner proposed to
prepare, for each sheet kind, a DXF template with ready details and schedules that the agent adjusts per project, and
to assemble the sheets himself.

## Decision

1. Sheets are produced by filling and adjusting office DXF templates, one DXF file per sheet, without a title block.
   The design is in [20](../architecture/20-drawing-sheets-from-dxf.md).
2. The engineer draws the source plan by a fixed layer convention; the model is created from it with the existing
   Sasaah tools ([ADR-0024](0024-harness-on-existing-sasaah-servers.md)); the same plan, with sizes and labels
   updated, becomes the sheet plan.
3. Reinforcement is chosen by the code first, then the engineer's rules, then a question to the engineer.
4. Members are grouped into types by the platform and approved by the engineer.
5. The first stage covers columns, footings, tie beams and beams. Slab sheets are a later stage.
6. This is a specification only. It is built after the model workflows, the calculation report and the host servers
   are complete.

## Consequences

- The platform's output becomes deliverable sheets, not only a checked model.
- The layer convention and the templates become owner-maintained inputs that must stay stable.
- Sasaah's DXF tools must cover the convention.
- Merging sheets stays manual until a later decision.

## Alternatives considered

- **The agent draws freely in DXF**: no uniform identity across details; the problem this decision answers.
- **Live AutoCAD automation through the add-in**: needs the host program and the add-in; later, not excluded.
- **A parametric drawing generator without templates**: the office identity would be re-implemented in code.

## Pre-mortem

The likely failure is geometry that changes too much for a template to hold (member counts, spans, openings), so the
writer distorts drawings. Early warning: sheet kinds that need a new rule for every project. The slab stage is kept
separate for this reason.
