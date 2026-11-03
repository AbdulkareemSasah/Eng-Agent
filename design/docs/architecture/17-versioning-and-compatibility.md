# 17. Versioning and Host Compatibility

Status: Proposed · Applies to: every repository

## 1. Package versions

- Semantic versioning for every package and add-in.
- For MCP servers, the tool surface is the public API: renaming or removing a tool, removing a parameter, changing a
  unit or making an optional parameter required is a **major** change. Adding a tool, an optional parameter or a new
  warning code is **minor**.
- For code packs, changing a check's result for the same inputs is a **major** change of that pack, even when it is a
  fix, because it changes engineering output. The changelog names every affected `check_id`.
- Deprecation: a tool or parameter is marked deprecated for at least one minor release, with a warning in its results,
  before removal.

## 2. Contract versions

- `eng-contract/<major>` appears in every envelope and record ([04](04-tool-contract.md) §11).
- Each result kind is versioned separately. Consumers declare the kind versions they accept.

## 3. Host program support

The goal is to support all reasonable host versions. The rule is that **a version is supported only if it is tested**.

| Host | Initial tested version | Design for older versions |
|---|---|---|
| ETABS | the latest version installed on the owner's workstation (22.x at the time of writing) | COM adapter uses late binding and version detection; the plugin builds per host runtime (.NET 8 for v22 and newer, .NET Framework for older) |
| SAFE, SAP2000 | latest installed | Same core as ETABS |
| Revit | 2026 | Multi-target project: `net8.0-windows` for 2025 and newer, `net48` for 2024 and older |
| AutoCAD | latest installed | Same split as Revit at 2025 |
| IDEA StatiCa | latest installed | REST client pinned per IDEA version |

Rules:

1. Each repository keeps a `SUPPORT.md` matrix of tested host versions, with the date and the acceptance record of
   each.
2. Servers detect the host version at connect time and expose capability flags. A tool that the connected version
   cannot perform returns `NOT_SUPPORTED_BY_VERSION`.
3. Adding a host version means adding it to the matrix, running the live acceptance suite on it, and recording it.

## 4. Python and .NET

- Python: the version is pinned per repository with `uv python pin`; packages support the current and the previous
  minor Python release.
- .NET: add-ins and plugins target the runtime their host requires. No other .NET code is written.
