# ADR-0025: The first workflow is the model edit cycle

Status: Accepted (by the owner, 2026-11-03) · Date: 2026-11-03

## Context

[18](../architecture/18-first-slice-dxf-to-etabs.md) made DXF to ETABS the first workflow and the proof of the
architecture. The session review behind ADR-0024 shows that creating the model is not where the owner's time goes:
the first model from DXF took about 9 minutes, while the edit cycles that followed took 342 agent minutes and
500 engineer minutes. The cycle is: ask for a change, wait, check, often edit by hand, run analysis and design again,
read the results.

The cycle is also where the sessions broke: design runs that never ran, analysis timeouts, 45 requests to the engineer
to run something by hand (with 5.0 hours of engineer gaps before them), and manual edits that an agent later lost.

## Decision

1. The first workflow, and the proof of the architecture, is the model edit cycle on ETABS through `sasaah-csi-mcp`:
   request, working copy (next revision), apply the edits, save, analysis, design, read and summarize the results,
   then an engineer turn (accept the revision, ask for more edits, or edit by hand), and again.
2. A request is a structured change set made of edit kinds from a short listed set, each with its parameters
   ([18](../architecture/18-first-slice-dxf-to-etabs.md) §2). A person fills it in, or a coding agent writes it from
   the engineer's words; the harness validates it (P5) and the engineer approves it before any write.
3. A manual edit is a normal turn. On every turn the workflow reads the model, compares it with the last revision it
   recorded, shows the differences, records them as engineer changes and continues from the new state. It never
   writes over a change it has not shown.
4. Creating the model from DXF is an optional first step that runs Sasaah's `tools/dxf-prep` and `tools/etabs-model`
   as tool steps (ADR-0024).
5. Phase 1 decides with rules and the engineer only. The decision-model tier (Jev) starts in phase 2 with the
   language-model tier (amends the phasing of ADR-0012).
6. The benchmark is the time from request to accepted revision, engineer time included, against the same changes done
   by hand and in an agent chat today (benchmark B-1, [18](../architecture/18-first-slice-dxf-to-etabs.md) §5).

## Consequences

- The proof exercises what costs the owner time: revisions, write safety, long analysis runs and engineer turns.
- Phase 1 needs a Sasaah build in which design runs and design-result reads work; the version check of ADR-0024
  enforces it.
- The harness needs a model reader and a difference report, built on read tools, from phase 1.
- Layer classification and DXF reading leave phase 1; spike S-07 (Jev) moves to phase 2 and spike S-11 (DXF) is
  dropped.

## Alternatives considered

- **Keep DXF to ETABS first**: a one-time step per project, not where the time goes. Rejected.
- **Start with SAFE or Revit**: in the roadmap they take their input from the ETABS model, so the ETABS cycle comes
  first. Rejected for the first slice.
- **Start with calculation reports**: no host writes, so it would not prove write safety. Rejected.

## Pre-mortem

The likely failure is a slice that keeps growing: new edit kinds are added before the first revision is accepted.
Early warning: requests outside the listed edit kinds in the first ten runs. New kinds go through the project lane
(ADR-0026), not into the slice.
