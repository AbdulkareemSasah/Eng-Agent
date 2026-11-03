# ADR-0022: Repository and package names

Status: Proposed; rows for host servers are void under ADR-0024 · Date: 2026-10-24

## Context

The owner wants plain names that say what each tool does. `revit-mcp` is already used by about 16 repositories
(the best known has several hundred stars). `etabs-mcp` exists in 8 repositories. `safe-mcp` collides with many
security projects.

## Decision (proposed; the Revit name awaits the owner's choice)

| Repository or package | PyPI package | GitHub (exact name, checked 2026-10-24) | PyPI (checked 2026-10-24) |
|---|---|---|---|
| `eng-platform` (private incubation workspace, not published) | none | 1 small repository | free |
| `eng-dev-gate` | `eng-dev-gate` | unused | free |
| `eng-contract` | `eng-contract` | unused | free |
| `csi-oapi-core` | `csi-oapi-core` | unused | free |
| `csi-etabs-mcp` | `csi-etabs-mcp` | unused | free |
| `csi-safe-mcp` | `csi-safe-mcp` | unused | free |
| `csi-sap2000-mcp` | `csi-sap2000-mcp` | unused | free |
| `dxf-mcp` | `dxf-mcp` | 1 small repository | free |
| `structural-codes` | `structural-codes-*` | 2 small repositories | free |
| `eng-harness` | `eng-harness` | unused | free |
| `revit-agent-bridge` (recommended; alternative `revit-ops-mcp`) | `revit-agent-bridge` | unused | free |
| `ideastatica-mcp` | `ideastatica-mcp` | 1 small repository | free |
| `synapse`, `revit-sheet-exporter`, `sasaah-studio-autocad` | not on PyPI (C# add-ins) | to check when created | n/a |

The `csi-` prefix groups the three CSI servers and avoids the generic word "safe".

## Consequences

- Packages are not published while they incubate privately, so names are not reserved on PyPI until a package goes
  public; availability is re-checked before each split.

## Alternatives considered

- Product-branded names for every tool: the owner prefers names that describe function. `Sasaah Studio` and `Synapse`
  remain product names because they are the owner's end-user products.
