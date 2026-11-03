# ADR-0024: The harness runs on the existing Sasaah MCP servers and tools

Status: Accepted (by the owner, 2026-11-03) · Date: 2026-11-03

## Context

The design planned new host servers: `csi-oapi-core` with `csi-etabs-mcp`, `csi-safe-mcp` and `csi-sap2000-mcp`
(ADR-0009), `revit-agent-bridge` (ADR-0010), `ideastatica-mcp`, and `dxf-mcp` (ADR-0020). Building them fills most of
phases 1 to 4.

The owner's Sasaah repository already has working servers and tools: `sasaah-csi-mcp` (83 tools for the CSI programs,
over COM with optional in-process plugins), `sasaah-revit-mcp` with its Revit bridge, `sasaah-idea-mcp`, and
command-line tools (`tools/dxf-prep`, `tools/etabs-model`, `tools/footing-design`, `tools/sbc-audit`).

A review of real agent sessions on Sasaah (2026-11-03, kept in the Sasaah repository under `agent-sessions/_baseline/`:
11 Claude Code sessions over 31.3 hours and 16 ZadLoop sessions with host work) found where the time went: the engineer
waiting or doing manual hand-offs 55%, model turns 25%, tool calls 20%. The host failures came from missing workflow
behavior and from deployment, not from how the servers are built: a server build older than its own fix failed all 7
design runs with `model_locked`; 10 of 74 analysis runs timed out with an unknown outcome; save dialogs and failed
attaches forced manual steps. Rewriting the servers fixes none of this.

The owner decided that the harness connects to the Sasaah servers and that no new servers are built.

## Decision

1. The harness is an MCP client of `sasaah-csi-mcp`, `sasaah-revit-mcp` and `sasaah-idea-mcp`, and runs the Sasaah
   command-line tools as tool steps with declared inputs and outputs, recorded in the journal. `csi-oapi-core`,
   `csi-etabs-mcp`, `csi-safe-mcp`, `csi-sap2000-mcp`, `revit-agent-bridge`, `ideastatica-mcp` and `dxf-mcp` are not
   built.
2. The harness holds one adapter per server. The adapter lists the tools that workflows may call (never a tool that
   runs scripts or arbitrary API calls, ADR-0008), wraps every result in the `eng-contract` envelope with canonical
   units and provenance, stores it and returns a `result_id`, and resolves each `$ref` to the stored value before a
   call. P2 therefore holds at the harness boundary although the servers do not speak the contract.
3. Until a server meets [05](../architecture/05-mcp-server-standard.md) and ADR-0007, the harness supplies the safety
   itself: it works on a copy (ADR-0018), saves before every analysis, reads back after every write, reconciles after
   a timeout by reading the model state before any retry, and checks at run start that each server build is not older
   than the minimum the workflow declares. A failed check stops the run before any write.
4. [05](../architecture/05-mcp-server-standard.md), [06](../architecture/06-csi-servers.md) to
   [08](../architecture/08-ideastatica-mcp.md), ADR-0003, ADR-0007 and ADR-0008 become the target for the Sasaah
   servers, adopted tool by tool in the Sasaah repository.
5. A Sasaah server is rewritten or replaced only by a new ADR backed by measurements showing that the server, not the
   harness, is the bottleneck.

## Consequences

- Phase 1 starts from host tools that already work, and server building leaves the roadmap
  ([19](../architecture/19-roadmap-and-spikes.md)).
- Host servers stay in C# in Sasaah (amends ADR-0002). `eng-contract` is used by the harness and by code packs, not
  inside host servers (amends ADR-0004 and ADR-0005). The names of the unbuilt packages in ADR-0022 are void.
- Each adapter pins the server builds it was tested with; its contract tests run against recorded server responses,
  so a Sasaah change that alters a tool's output fails in CI, not in a project.
- The servers have no dry runs or idempotency keys yet, so a retried write could apply twice: the harness never
  retries a write before reconciliation.
- The harness depends on Sasaah only through the tool names and schemas in its adapters; publishing the harness does
  not require publishing Sasaah.

## Alternatives considered

- **Build the planned servers**: most of phases 1 to 4 before the first useful workflow, and the evidence shows the
  servers did not cause the slowness. Rejected.
- **Copy the Sasaah servers into the platform workspace**: two copies to keep in step. Rejected.
- **A proxy server that speaks the contract in front of each Sasaah server**: one more process for what an adapter in
  the harness does. Rejected for now.

## Pre-mortem

The likely failure is Sasaah tool behavior (partial writes, mixed units, silent errors) leaking into workflows faster
than adapters and Sasaah fixes contain it. Early warning: adapters growing special cases per tool, or reconciliation
in more than one run in ten.
