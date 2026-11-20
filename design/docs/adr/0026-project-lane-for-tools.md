# ADR-0026: A project lane for building tools during live projects

Status: Accepted (by the owner, 2026-11-03) · Date: 2026-11-03

## Context

P12 and the process required a gap report and the full lifecycle (approved spec and plan, tests first, reviews) before
any missing capability was built. In the sessions reviewed for ADR-0024, agents met missing capabilities in the middle
of live projects and wrote 61 one-off scripts instead: no test checked their numbers and none was reused. With an
engineer waiting, the full lifecycle is too slow, so the rule produced the improvisation it was meant to prevent.

## Decision

1. **Project lane.** During a live project, when the owner asks in the session for a missing capability, the agent
   builds or extends a permanent tool on a branch of the tool's own repository, with:
   - a test for every number the tool produces or writes, against a cited source or a hand check;
   - a live check on a copy of the model or on a fixture, never on the working model;
   - use in the project only on a copy (ADR-0018).
2. The owner's request in the session is the approval. The agent records the work in its session report (what was
   built, the tests, the live check, open risks) and files a gap report as the record.
3. **Release lane.** Before the tool is merged to `main` or used in another project, it passes the full process
   ([process/01](../../process/01-lifecycle.md)). Until then the run report marks every result that depends on it, so
   the engineer signs knowing which results came from an unreleased tool.
4. P12 is reworded: a missing capability becomes a permanent tool, never ad-hoc code.

## Consequences

- Missing tools are built when they are needed and kept with their tests.
- Unreviewed code runs during live projects. It is contained: copies only, a test for every number, no merge, marked
  results, and the release lane before reuse.
- The shared gate must recognize project-lane branches, allowing code before an approved plan (exception to A1) while
  still running the tests. The owner digest lists open project-lane branches.
- This decision changes process documents ([process/01](../../process/01-lifecycle.md) §9, 02, 08, the process
  README and the `AGENTS.md` template). No repository exists yet, so no `AGENTS.md` needs regenerating.

## Alternatives considered

- **Gap report and full lifecycle only**: under time pressure it produced 61 untested scripts. Rejected.
- **Scripts in the project folder**: fast, but lost and untested. Rejected.
- **Free building during projects, reviewed later**: without tests, wrong numbers reach outputs. Rejected.

## Pre-mortem

The likely failure is project-lane branches that pile up and never pass the release lane, so unverified tools become
permanent in practice. Early warning: project-lane branches older than 30 days in the owner digest.
