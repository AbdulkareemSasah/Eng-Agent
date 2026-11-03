# ADR-0009: CSI shared core, COM by default, optional in-process plugin

Status: Superseded by ADR-0024 · Date: 2026-10-24

## Context

ETABS, SAFE and SAP2000 share most of the CSI OAPI (and a cross-product `CSiAPIv1` library). The API is the same from
outside (COM) and inside (plugin): a plugin does not unlock extra functions, but it runs in process, so large batches
are much faster and more stable. Plugins must be .NET; ETABS v22 plugins target .NET 8.

## Decision

- `csi-oapi-core` (Python) holds the shared port, the COM adapter (comtypes), the plugin adapter (named pipe client),
  the fake host, the unit guard and model identity, plus the C# plugin source.
- `csi-etabs-mcp`, `csi-safe-mcp` and `csi-sap2000-mcp` are separate packages on top of the core.
- COM is the default and always available. The plugin is optional; when its pipe is live and versions match, the
  adapter uses it for the operations it supports. The plugin executes only a fixed allowlist of operations.
- Wire format between Python and the plugin: length-prefixed JSON frames.

## Consequences

- One implementation of CSI quirks (return codes, units, threading) for three products.
- Two adapters must produce identical results; the same contract tests run against both.
- Whether one plugin binary serves all three products, and the plugin's threading rules, are settled in spike S-03.

## Alternatives considered

- **Three fully separate servers**: the same code written three times. Rejected.
- **One server for all three products**: users install what they do not use; tool names would mix products. Rejected.
- **Plugin only**: requires plugin installation for any use. Rejected.
