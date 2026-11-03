# ADR-0018: Permission modes

Status: Proposed · Date: 2026-10-24

## Context

The owner wants users to choose how much freedom the harness has over their models: working on a copy with final
approval, approving every write, or full freedom with a log.

## Decision

- Three modes: `work_on_copy` (default), `approve_each_write`, `autonomous_logged`, selected per run with a default in
  settings.
- `work_on_copy`: a **new** model is created in the run folder and promoted by copying the file to its target path,
  with a backup of anything replaced. An **existing** model is copied before the first write and promoted by replaying
  the journaled write steps on the original after approval, then checking it and comparing change sets. Replay works
  for every host, including workshared Revit models where replacing files is not possible.
- An "always ask" list applies in every mode: deletions, overwriting originals, and anything a workflow marks.

## Consequences

- Original models are protected unless the user chooses otherwise.
- Promotion by replay doubles the write time for the final step; acceptable for safety.

## Alternatives considered

- **Promote by replacing the model file**: fast for ETABS, impossible for workshared Revit models. Allowed later as an
  ETABS-specific option by ADR.
