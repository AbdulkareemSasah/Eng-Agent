# Architecture Decision Records

One decision per file. Format: [process/templates/adr.md](../../process/templates/adr.md).
Statuses: `Proposed` (awaiting owner approval), `Accepted`, `Superseded by ADR-XXXX`, `Rejected`.
`Proposed; amended by ADR-XXXX` marks a proposed decision that a later one changes in part.
An accepted ADR is never edited except to change its status; a new decision supersedes it.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-independent-repositories-private-first.md) | Independent packages, incubated privately in one workspace, split into public repositories | Proposed; amended by ADR-0028 |
| [0002](0002-python-uv-default-csharp-at-host-boundary.md) | Python with uv by default; C# only where a host API forces it; every MCP front end in Python | Proposed; amended by ADR-0024 |
| [0003](0003-mcp-servers-are-pure-adapters.md) | MCP servers are pure host adapters; blocks, workflows and code verdicts live elsewhere | Proposed; amended by ADR-0024 |
| [0004](0004-shared-tool-contract.md) | One shared tool contract package, `eng-contract` | Proposed; amended by ADR-0024 |
| [0005](0005-pass-by-reference.md) | Results passed by reference through a workspace result store and `$ref` inputs | Proposed; amended by ADR-0024 |
| [0006](0006-canonical-units.md) | One canonical unit system with unit-suffixed field names | Proposed |
| [0007](0007-write-safety.md) | Write safety: dry runs, idempotency keys, unknown outcomes, revisions, check after write | Proposed; amended by ADR-0024 |
| [0008](0008-tool-naming-toolsets-no-escape-hatches.md) | Tool naming, toolsets, and no escape-hatch tools | Proposed; amended by ADR-0024 and ADR-0026 |
| [0009](0009-csi-shared-core-com-default-plugin-optional.md) | CSI: shared core, COM adapter by default, optional in-process plugin | Superseded by ADR-0024 |
| [0010](0010-revit-thin-addin-python-front.md) | Revit: thin C# add-in over a named pipe, Python front end | Superseded by ADR-0024 |
| [0011](0011-harness-owns-workflow-engine.md) | The harness owns a workflow engine with one composable block abstraction in typed Python | Proposed |
| [0012](0012-decision-cascade-and-provider-layer.md) | Decision cascade (rules, decision model, LLM, engineer) and a pluggable provider layer | Proposed; amended by ADR-0025 |
| [0013](0013-pydanticai-behind-interface.md) | PydanticAI for language-model steps, behind an internal interface | Proposed |
| [0014](0014-run-journal-and-replay.md) | Append-only run journal in SQLite; resumption by replay | Proposed |
| [0015](0015-harness-ui-nicegui.md) | Harness UI in NiceGUI, local web and native window | Superseded for phase 1 by ADR-0027 |
| [0016](0016-code-packs-lifecycle-and-overlays.md) | Code packs: check model, draft-verified-approved lifecycle, SBC 304 overlay on ACI 318-14 | Proposed |
| [0017](0017-templates-and-design-basis.md) | Templates and a design basis with per-field sources | Proposed |
| [0018](0018-permission-modes.md) | Three permission modes, user-selectable, default work on a copy | Proposed |
| [0019](0019-host-version-support-policy.md) | Host version support: tested versions only, design for multi-version | Proposed |
| [0020](0020-dxf-reading-as-mcp-server.md) | DXF reading as its own MCP server | Superseded by ADR-0024 |
| [0021](0021-agent-agnostic-ci-enforced-process.md) | A development process that is tool-agnostic and enforced by machines: verifiable gates, separate identities, CI-run reviews, one shared gate | Proposed; amended by ADR-0026, ADR-0028 and ADR-0035 |
| [0022](0022-repository-names.md) | Repository and package names | Proposed; amended by ADR-0024 |
| [0023](0023-license-apache-2.md) | License: Apache-2.0 | Proposed |
| [0024](0024-harness-on-existing-sasaah-servers.md) | The harness runs on the existing Sasaah MCP servers and tools; no new host servers are built | Accepted |
| [0025](0025-first-workflow-edit-cycle.md) | The first workflow is the model edit cycle | Accepted |
| [0026](0026-project-lane-for-tools.md) | A project lane builds tools during live projects; the release lane runs before reuse | Accepted |
| [0027](0027-phase-1-interface.md) | Phase 1 interface: command line, HTML approval page and run report | Accepted |
| [0028](0028-build-v1-in-this-repository.md) | Build v1 in this repository, code-complete before live testing, in bootstrap mode; Python 3.14 | Accepted (owner, in the build prompt) |
| [0029](0029-eng-contract-0-1-details.md) | eng-contract 0.1 details recorded in 04 (1024-based sizes, `payload_file`, file sources, `op_id` on errors, `infos`, `Subject.case`, `INTERNAL` for store failures, ASCII unit symbols, `canonical.loads`, local trace references) | Proposed |
| [0030](0030-replay-by-step-path-and-reconciliation.md) | Replay by step path, in-flight reconciliation, durability policy, one engine per run, one Job Object per server with host programs outside it (amends ADR-0014) | Proposed |
| [0031](0031-model-locked-after-analysis.md) | `model_locked` after analysis is `PRECONDITION_FAILED` (`model_unlocked`), not `HOST_LOCKED`; an approved unlock step; precondition `server_owned_instance` (amends 04 §8.1, 11 §7 and §9) | Proposed |
| [0032](0032-harness-side-model-identity.md) | A harness-side model identity in the workspace when the host cannot stamp one (amends 04 §3.3, 06 §6) | Proposed |
| [0033](0033-desktop-products-in-sasaah.md) | The desktop products stay in Sasaah during v1; nothing is built under `products/` | Proposed |
| [0034](0034-task-log-by-default.md) | Every owner task has a task log in the root folder `tasklog/`, pushed directly as log-only commits; recorded owner exceptions to A11, hub rule 6 and "never the owner's credentials" | Proposed |
| [0035](0035-no-changed-line-limit.md) | No changed-line limit per task; `max_changed_lines` is an estimate, file scope still enforced | Accepted; amended by ADR-0036 |
| [0036](0036-collateral-test-edits-and-session-estimate.md) | Test files and the changelog may be collateral edits; `max_sessions` is an estimate | Accepted |
