# 14. Harness UI

Status: Proposed; deferred after phase 1 by ADR-0027 · Lives in: `eng-harness` · Technology: NiceGUI ([ADR-0015](../adr/0015-harness-ui-nicegui.md))

## 1. Goals

The engineer sees every workflow step by step: what ran, what it produced, what was decided and by whom, and what
needs approval or input. The UI is how the engineer stays in charge (P11).

## 2. Technology

- Python only (NiceGUI), served by the harness process on `127.0.0.1` with a per-session token. It opens in the
  browser, or in a native desktop window through NiceGUI's native mode. One code base gives both.
- Live updates come from the run journal through the UI framework's websocket channel.
- Arabic and English, with right-to-left layout when Arabic is selected. RTL support and live-update performance are
  verified in spike S-09 before the UI work starts. If the spike fails, the fallback is a TypeScript front end over the
  same local API, decided by ADR.

## 3. Screens

| Screen | Content |
|---|---|
| Home | Recent runs with status, start a workflow, pending approvals and inputs |
| Workflow catalog | Each workflow's description, inputs, and a step diagram generated from its block metadata |
| Run setup | Template choice, design basis confirmation and inputs ([13](13-templates-and-design-basis.md) §4), permission mode, model and file selection |
| Run view | Timeline of steps with status, duration and tier of each decision; step detail with inputs (as links to results), result summaries, verdict tables, warnings |
| Approval | Dry-run change set: counts by type, list of changes, affected stories or levels, before and after values by reference |
| Input request | Form generated from the field schema with units and bounds; values become engineer-sourced results |
| Escalation | Why the run stopped, the evidence, and the options to continue |
| Results browser | Any result's payload and its lineage graph back to host data and engineer inputs |
| Templates | View, copy, edit and validate templates |
| Settings | Providers and keys, decision policies per point, default permission mode, servers, language |
| Audit | Journal and server audit records, filterable |

## 4. Controls

Pause at the next safe point, resume, cancel, retry a failed step, take over a decision, sign off.

## 5. Phase 1 scope

Deferred by [ADR-0027](../adr/0027-phase-1-interface.md): phase 1 has no graphical application. It has the command
line, live progress in the terminal, a local HTML approval page (approvals, engineer inputs, batched decisions and
sign-off) and an HTML run report ([11](11-harness-engine.md) §11). The screens above are the target for the later UI,
which a new ADR confirms after spike S-09.

## 6. Sign-off and reports

- Outputs are `DRAFT` until the engineer signs off. Sign-off records the engineer's name and time and is allowed only
  when every verdict is `PASS` or each exception is accepted with a written reason.
- The run report (HTML and PDF) is generated from the journal and the calculation traces: inputs and their sources,
  steps, decisions with their tier, verdicts with clause references, and the sign-off.
- In phase 1, sign-off is given on the approval page and the report is HTML only
  ([ADR-0027](../adr/0027-phase-1-interface.md)).
