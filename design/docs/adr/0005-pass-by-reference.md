# ADR-0005: Pass results by reference

Status: Proposed; amended by ADR-0024 (the harness resolves references) · Date: 2026-10-24

## Context

When results come back as text, an agent re-types numbers into the next call, and copying errors (450 becoming 540)
reach the model. The earlier project only detected such errors after the fact by matching numbers in the transcript.
Results must also travel between servers (ETABS forces into SAFE or IDEA; code-pack section sizes into Revit).

## Decision

- Every tool result is stored as an immutable record in a workspace result store and gets a `result_id` (ULID).
- Ref-capable inputs accept `{"$ref": "<result_id>#<JSON Pointer>"}`. Servers resolve references themselves, then
  validate the resolved value like a literal.
- All servers of a project share the project workspace (`ENG_WORKSPACE`), so references work across servers. The
  workspace must be on a local, non-synchronized disk.
- Records carry lineage (`parents`), content hashes, a stamped model identity and revision. Write tools reject
  references from an older revision of the same model (unless a parameter is declared `stale_ok`); the harness applies
  the same rule to every reference it passes to calcs, decisions and approvals.
- In the harness (and in any server started with `ENG_REQUIRE_REFS=1`), parameters marked as engineering quantities
  accept only references.

## Consequences

- Copying errors are prevented, not just detected.
- A file-based store needs a cleanup command and some disk space; acceptable for engineering workspaces.
- Every server must implement reference resolution through `eng-contract`.

## Alternatives considered

- **Transcript number matching** (the earlier approach): detection after the fact, with tolerance problems. Rejected
  as the primary mechanism.
- **A store server process**: adds a moving part; files with atomic writes are enough for a single workstation.
  Rejected for now.
- **Content-addressed ids**: identical results would share ids across different provenance. Rejected; content hashes
  are kept as a field instead.
