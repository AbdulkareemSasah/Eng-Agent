# ADR-0008: Tool naming, toolsets, and no escape hatches

Status: Proposed; amended by ADR-0024 (a target for the Sasaah servers; the harness adapters enforce the allowlist) and ADR-0026 (missing tools through the project lane) · Date: 2026-10-24

## Context

The earlier servers had about 390 tools in total (248 for Revit alone), long prose descriptions, and escape hatches
(`csi_run_script`, `csi_invoke`, `idea_run_script`, `run_baked_tool`, generic setters). When a needed tool was missing,
agents used the escape hatches or rewrote server code, which produced random code and multi-hour tasks.

## Decision

- Tool names: `<prefix>_<verb>_<noun>` with a fixed verb vocabulary ([05](../architecture/05-mcp-server-standard.md) §3).
  The prefix is the host (`etabs`, `safe`, `sap`, `revit`, `idea`, `dxf`) so names never collide across servers in
  clients that do not namespace tools.
- Tools are grouped into toolsets of at most 25 tools; a server has at most 80 tools; clients enable only the
  toolsets they need.
- No tool may execute scripts, evaluate expressions, forward arbitrary API calls, or set arbitrary properties by
  name. Database-table writes are forbidden.
- A missing capability is a gap report and a new, specified tool (P12), never an improvised workaround.

## Consequences

- Agents and workflows can only do what tools allow, which is the point.
- Some host features will be unavailable until a tool is specified for them; the gap process keeps that visible.

## Alternatives considered

- **Keep an "expert" escape-hatch toolset disabled by default**: experience shows it gets enabled under pressure.
  Rejected.
- **No prefix, rely on client namespacing**: not all clients namespace. Rejected.
