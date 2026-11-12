# 19. Roadmap, Spikes and Risks

Status: Proposed (revised by ADR-0024 to ADR-0027)

## 1. Phases

| Phase | Content | Exit criteria |
|---|---|---|
| 0. Foundations | Approve this design; GitHub plan and identities set up ([process/11](../../process/11-repository-standard.md) §6); create `eng-platform` with this hub as `design/`, CI and branch protection; `eng-dev-gate` 0.1; `eng-contract` 0.1; phase 0 spikes; a Sasaah build in which design runs and design-result reads work; owner prepares benchmark B-1 | Phase 0 spikes reported and ADRs updated; benchmark ready; gate and contract released inside the workspace |
| 1. Proof | `eng-harness` (engine, adapters for `sasaah-csi-mcp` and the Sasaah tools the slice uses, calcs, templates, rules and engineer tiers, command line, approval page and run report), workflow: the model edit cycle on ETABS | Acceptance A1 to A7 in [18](18-first-slice-dxf-to-etabs.md) |
| 2. Foundations design | `structural-codes` (framework, ACI 318-14 and SBC 304-2018 footing checks), SAFE through `sasaah-csi-mcp`, decision-model tier (Jev) in shadow mode, language-model tier with PydanticAI, block `design_isolated_footing` and its workflow; the full UI by a new ADR | Footing workflow accepted on owner projects; checks approved |
| 3. Revit and frames | Revit through `sasaah-revit-mcp`, SAP2000 through `sasaah-csi-mcp`, column checks, workflow: design columns in ETABS and update Revit by reference | Accepted on owner projects |
| 4. Connections and desktop products | IDEA StatiCa through `sasaah-idea-mcp`; `synapse`, `revit-sheet-exporter`, `sasaah-studio-autocad` (may start after phase 1, at the owner's choice) | Each product's own acceptance |
| Open source | Per package: split into its own repository after a release that meets the open-source checklist | [process/07](../../process/07-release-and-open-source.md) |

In every phase, a capability that is missing during a live project goes through the project lane
([ADR-0026](../adr/0026-project-lane-for-tools.md)).

For v1, all phases are built code-complete before live testing; the spikes that need host programs, acceptance A1 to
A7 and the A4 time gate run at the owner's local test stage and must pass before any release
([ADR-0028](../adr/0028-build-v1-in-this-repository.md)). The first live run comes first; the task-log code is a
parallel lane, never on that run's critical path ([ADR-0034](../adr/0034-task-log-by-default.md) D14).

Each phase gets a time box from the owner when it starts (two weeks proposed for phase 0). A phase that has not met
its exit criteria within its time box cuts scope; its exit criteria are never lowered to close it.

## 2. Spikes

A spike answers a specific question with throwaway code in the target package's `spikes/` folder, time-boxed to at most
two days, and ends with a written report ([process/templates/spike-report.md](../../process/templates/spike-report.md))
and ADR updates. Spike code never ships. Spikes run at the start of the phase that needs them; for v1, the parts that need host
programs run at the local test stage (ADR-0028).

| Id | Phase | Question | Feeds |
|---|---|---|---|
| S-12 | 0 | `sasaah-csi-mcp` inventory for the edit cycle: which tools cover each step and edit kind, their units, errors, timeouts and build reporting; which tools run scripts or write tables (kept off the allowlist); gaps. Starts from the tool-manifest exporter of the earlier Sasaah Agent project (`tools/export-manifest`), regenerated for the current catalog of 83 CSI tools | ADR-0024, [18](18-first-slice-dxf-to-etabs.md) |
| S-02 | 0 | Analysis and design through `sasaah-csi-mcp`: run times, timeout behavior and unknown outcomes, save before run, modal dialogs | [11](11-harness-engine.md) §6 |
| S-04 | 0 | Reading the model state through `sasaah-csi-mcp`: speed and reliability of a fingerprint and a difference report that catches edits made in the ETABS window; stamping the model identity | [11](11-harness-engine.md) §5, [18](18-first-slice-dxf-to-etabs.md) |
| S-10 | 0 | Replay-based resumption of async Python blocks with a recorded journal; Job Object termination of child servers | ADR-0014 |
| S-07 | 2 | Jev access: OpenRouter versus the TypeSafe API, request format, batching, latency from the owner's location, confidence meaning, data retention terms | ADR-0012, [12](12-decision-layer.md) |
| S-09 | 2 | UI framework for the full interface: Arabic right-to-left layout and a live timeline with 1,000 events | ADR-0027, [14](14-harness-ui.md) |
| S-05 | 3 | Readiness of `sasaah-revit-mcp` in Revit: which tools pass a live test, dialog handling, transactions and rollback, change tracking | ADR-0024 |
| S-08 | 4 | Readiness of `sasaah-idea-mcp`: coverage and licensing behavior | ADR-0024 |
| S-06 | 4 | License terms of NuGet Revit reference packages for CI builds of the Revit add-ins | [15](15-desktop-addins.md) |

S-01 (Python COM with ETABS), S-03 (CSI plugin) and S-11 (DXF drawings) were dropped by ADR-0024 and ADR-0025.

## 3. Risks (pre-mortem)

Imagine it is a year from now and the project failed. The most likely reasons, and what prevents them:

| Id | Failure story | Prevention | Early warning |
|---|---|---|---|
| R1 | It works, but it is not faster than the engineer | Benchmark B-1 and acceptance A4 before any release (ADR-0028); rules-first decisions; batch tools; save before analysis | Phase 1 timings above 50% of baseline |
| R2 | The decision model is unavailable, changes, or is wrong for engineering states | Provider interface; engineer tier; decision model only from phase 2, in shadow mode with evaluations | S-07 results; evaluation agreement under 95% |
| R3 | A host API or a Sasaah tool cannot do something a workflow needs | Spikes first (S-12); project lane; gap reports | Gap reports that block a workflow |
| R4 | Too many packages at once, none finished | Strict phases with time boxes (§1); packages created only when their phase starts | More than six active packages before phase 1 exit; a phase past its time box |
| R5 | The owner becomes the bottleneck for approvals and reviews | Owner approves only engineering content and contracts; CI reviewers and checks do the rest; daily digest | Pull requests waiting more than a week for the owner |
| R6 | Coding agents ignore the process and improvise | Machine-checked gates, risk floor, file scope, test-first check, CI reviewers, separate identities, no escape-hatch tools; the project lane as the allowed fast path | Failing `gate-check` runs; seeded-defect audits missed; one-off scripts in session reports |
| R7 | A code check or calc is wrong | Verification requirements; independent review; approval bound to content hash; program comparison | Disagreement with host design output |
| R8 | Vendor licensing blocks open-sourcing | No vendor binaries; reference packages checked in S-06; late binding | S-06 outcome |
| R9 | The UI framework cannot support Arabic or live updates | Phase 1 uses plain HTML pages (ADR-0027); spike S-09 before the full UI, with a documented fallback | S-09 outcome |
| R10 | Host programs misbehave when driven by background processes | Same-integrity rule; S-02; watchdog and wedged state; save before analysis | Spike failures; manual hand-offs in run journals |
| R11 | A host crash leaves the journal and the model out of step | Save after every write step; host-state check on resume; reconciliation by reading the model | A6 failures |
| R12 | Sasaah server behavior (stale builds, timeouts, dialogs, partial writes, unrestored units) breaks workflows | Build and tool-list check at run start; units checked after every timeout; adapters pinned to tested builds, with contract tests; work on a copy; reconciliation before any retry; adoption of [05](05-mcp-server-standard.md) in Sasaah | Build-check failures; reconciliation in more than one run in ten |
| R13 | Project-lane tools never pass the release lane | Copies only; marked results; open lane branches in the owner digest | Lane branches older than 30 days |
