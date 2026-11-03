# ADR-0027: Phase 1 interface: command line, approval page and run report

Status: Accepted (by the owner, 2026-11-03) · Date: 2026-11-03

## Context

ADR-0015 and [14](../architecture/14-harness-ui.md) put a full NiceGUI interface in phase 1. In the ZadLoop sessions
reviewed for ADR-0024, more than 20 hours went into interface work while host work stalled. The owner already works
through coding agents, and they can run a command line. In phase 1 the engineer needs to see progress, approve a
change set before it is written, and read the results.

## Decision

1. Phase 1 has no graphical application. It has:
   - a command line to start, resume, stop and inspect runs, used by a person or by a coding agent;
   - live progress in the terminal: the current step, its elapsed time and its expected time from earlier runs;
   - a local HTML approval page for each approval point: the change set and the differences from the last revision,
     with approve or reject and a reason;
   - an HTML run report: changes, result summary, the source of every value, decisions and timings.
2. Approvals are given only on the page, never through the command line, so an agent that runs a workflow has no
   approve step to run. The page is served on localhost and opened in the engineer's browser. Signing outputs (P11)
   is an approval point on the same page.
3. The full interface is decided later by a new ADR. NiceGUI remains a candidate, and spike S-09 moves to that phase.

## Consequences

- Phase 1 effort goes to the workflow and to host safety.
- The same run works from a terminal or from a coding agent; the engineer approves in the browser.
- Differences are shown as tables; there is no model view in phase 1.

## Alternatives considered

- **The full NiceGUI interface in phase 1 (ADR-0015)**: competes with the workflow for build time. Deferred.
- **Terminal only, approvals typed in the terminal**: a change set is hard to read there, and an agent could type the
  approval. Rejected.
- **Approvals inside the agent chat**: ties approvals to one agent and lets the agent answer for the engineer.
  Rejected.

## Pre-mortem

The likely failure is an approval page that grows into an unplanned interface. Early warning: requests to edit values
on the page. The page stays read-only apart from approve, reject and sign.
