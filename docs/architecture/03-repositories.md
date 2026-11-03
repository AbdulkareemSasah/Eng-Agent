# 03. Package and Repository Catalog

Status: Proposed (catalog revised by ADR-0024) · Names are *working names* until [ADR-0022](../adr/0022-repository-names.md) is accepted.

## 1. Incubation, then independent repositories

Every tool is an independent package from its first commit. While private, the agent-stack packages live together in
one private uv workspace repository, `eng-platform`; each is split into its own public repository when it goes open
source ([ADR-0001](../adr/0001-independent-repositories-private-first.md)).

```
eng-platform/                      private workspace repository (incubation)
  design/                          this design hub
  packages/
    eng-contract/                  each package: pyproject.toml, AGENTS.md, docs/, tests/, CHANGELOG.md
    eng-harness/
    ...
  tools/
    eng-dev-gate/                  the shared process gate (process/11 §4)
  .github/                         CI, CODEOWNERS, templates (repository level)
```

## 2. Catalog

| Package | Kind | Languages | Phase | Depends on | Purpose |
|---|---|---|---|---|---|
| `eng-contract` | Python library + spec | Python | 0 | Pydantic | Envelope, result store, `$ref`, units, errors, verdicts, neutral kinds |
| `eng-dev-gate` | Development tool | Python | 0 | — | Local gate, CI checks, reusable workflows, reviewer prompts, `AGENTS.md` rendering |
| `eng-harness` | Application | Python | 1 | eng-contract, MCP SDK; structural-codes and PydanticAI from phase 2 | Workflow engine, blocks, workflows, decision layer, templates, server adapters, command line and HTML pages |
| `structural-codes` | Python libraries (core, `aci318-14`, `sbc304-2018`) | Python | 2 | eng-contract | Code packs |
| `synapse` | Revit add-in (own repository) | C# | 4 | Revit API, CSI API | Revit to CSI synchronization from inside Revit (owner's product) |
| `revit-sheet-exporter` | Revit add-in (own repository) | C# | 4 | Revit API | Sheet export; appears under the shared **Sasaah Studio** ribbon tab |
| `sasaah-studio-autocad` | AutoCAD add-in (own repository) | C# | 4 | AutoCAD .NET API | Daily AutoCAD commands under the **Sasaah Studio** tab |

Host programs are reached through the Sasaah servers and tools, which are used, not built here
([ADR-0024](../adr/0024-harness-on-existing-sasaah-servers.md)):

| Host | Used through | First phase |
|---|---|---|
| ETABS | `sasaah-csi-mcp` | 1 |
| SAFE | `sasaah-csi-mcp` | 2 |
| SAP2000 | `sasaah-csi-mcp` (coverage checked when phase 3 starts) | 3 |
| Revit | `sasaah-revit-mcp` and the Sasaah Revit bridge | 3 |
| IDEA StatiCa | `sasaah-idea-mcp` | 4 |
| DXF drawings | Sasaah `tools/dxf-prep` and `tools/etabs-model`, as tool steps | 1 (optional) |

Phases are defined in [19-roadmap-and-spikes](19-roadmap-and-spikes.md). Phase 1 is the first end-to-end slice: the
model edit cycle on ETABS ([18](18-first-slice-dxf-to-etabs.md)). Desktop products may start after the phase 1 proof
at the owner's choice. A package is created only when its phase starts (risk R4).

## 3. Boundary rules (enforced in CI)

1. **Each package builds, tests and releases on its own.** CI runs every package's tests and build separately.
2. **Import rules follow the layers** ([02](02-system-overview.md) §1): `structural-codes` never imports
   `eng-harness`; `eng-contract` imports no other package; nothing imports a package's internal modules; no package
   imports Sasaah code, which is reached only over MCP or as a tool step. An import-rule exception is a CI failure,
   not a configuration change.
3. **Only `eng-contract` is shared by everyone.** Anything else two packages need goes to `eng-contract` (if it is
   contract, including neutral kinds) or to a new library, by ADR. Copying code between packages is forbidden.
4. **C# exists only where a host API forces it**: the AutoCAD add-in and the Revit product add-ins. Every other package
   is Python ([ADR-0002](../adr/0002-python-uv-default-csharp-at-host-boundary.md)). The host servers stay in C# in
   the Sasaah repository ([ADR-0024](../adr/0024-harness-on-existing-sasaah-servers.md)).
5. **No vendor binaries anywhere.** CSI, Autodesk and IDEA assemblies are referenced from the local installation or
   from vendor-published packages, never committed.

## 4. Releases during incubation

Packages are versioned separately and tagged `<package>-vX.Y.Z`. Inside the workspace, packages depend on each other
as workspace members. When a package is split out to go public, its consumers switch to the PyPI release with a version
range ([process/07](../../process/07-release-and-open-source.md)).

## 5. The "Sasaah Studio" ribbon tab

`Sasaah Studio` is a shared ribbon tab name, not a single add-in. Every add-in that wants to appear there creates the
tab if it does not exist and adds its own panel ([15-desktop-addins](15-desktop-addins.md) §2).

## 6. Visibility

`eng-platform` and the desktop product repositories are private, in git from the first commit. A package becomes a
public repository only after its first release passes the open-source checklist
([process/07](../../process/07-release-and-open-source.md) §4).
