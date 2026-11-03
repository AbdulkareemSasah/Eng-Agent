# ADR-0003: MCP servers are pure host adapters

Status: Proposed; amended by ADR-0024 (a target for the Sasaah servers) · Date: 2026-10-24

## Context

The owner wants MCP projects to be "MCP and nothing more". Composite engineering tasks (blocks) are still maturing and
should stay inside the harness. Mixing workflow logic, decisions or code checks into servers would couple them to one
way of working and make them less useful to others.

## Decision

- A server adapts one host program or file format. It reads, writes, analyzes and checks model integrity through
  small typed tools.
- Servers do not run workflows or blocks, do not call models, do not call other servers, and do not evaluate design
  code clauses.
- Host-native design output (ETABS design, IDEA checks) may be returned as raw host results, labeled `source: host`.
- Blocks live only inside the harness until the owner decides otherwise by a new ADR.

## Consequences

- Servers are reusable by any MCP client, not only the harness.
- Verdicts for code compliance come from `structural-codes` (or from hosts, labeled).
- Some convenience (one call doing many steps) is deliberately absent from servers; batching covers performance.

## Alternatives considered

- **Expose blocks as MCP tools in each server**: convenient, but freezes immature designs into public APIs. Deferred.
