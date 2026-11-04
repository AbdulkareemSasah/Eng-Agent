# products/: desktop products and their overlap with Sasaah

Status: Proposed (analysis for [ADR-0033](../design/docs/adr/0033-desktop-products-in-sasaah.md)) · Work item B-091

[ADR-0028](../design/docs/adr/0028-build-v1-in-this-repository.md) §2 reserves `products/` for the three desktop
products of [15](../design/docs/architecture/15-desktop-addins.md). The owner's rule is to build nothing that already
exists in Sasaah and to list every overlap in the owner queue. This file is that analysis. **Nothing is built under
`products/` in v1** (ADR-0033). The folder holds only this file until the owner decides.

Evidence paths are relative to the read-only Sasaah repository. The analysis is from reading source files; no host
program was run, so every statement about behaviour is "needs local test".

## 1. Overlap table

| Product in 15 | What Sasaah already contains (project, features, evidence) | What 15 asks for that Sasaah lacks | Recommendation |
|---|---|---|---|
| `synapse` (Revit, Revit to CSI sync) | Project `04_Deployments/Sasaah.Synapse.Revit.Addin` over the engines `02_Engines/Sasaah.Revit.Engine` and `02_Engines/Sasaah.Etabs.Engine`. Commands: Sync to ETABS and Sync to Revit (`Commands/SyncToEtabsCommand.cs`, `SyncToRevitCommand.cs`), launch and stop ETABS, select elements, draw column, beam, wall and slab (normal and quick), assign joint force, frame point, frame distributed and shell uniform loads, define loads (`Commands/*Module.cs`). The sync target is `IStructuralSyncTarget`, implemented by `EtabsConnector` (`App.cs`, `01_Core/Sasaah.Core/Abstractions/IStructuralSyncTarget.cs`). Install discovery already enumerates ETABS, SAFE and SAP2000 (`02_Engines/Sasaah.Etabs.Engine/Connector/CsiInstallDiscovery.cs`). Specs `specs/005-synapse-ux-rebuild`, `005-synapse-workflow-reorg`, `007-synapse-sync-ux` (all Draft); `PRODUCT.md` names the Revit to ETABS bridge as the product's purpose. | (a) Sync to SAFE and SAP2000: the Synapse sync target is ETABS; SAFE and SAP2000 appear only in install discovery and in the separate MCP bridge plugins (`04_Deployments/Sasaah.Safe.Bridge.Plugin`, `Sasaah.Sap.Bridge.Plugin`), not in Synapse. (b) Ribbon tab: Synapse uses its own tab `Sasaah Synapse` (`Commands/SyncToEtabsModule.cs`, `TabName`), not the shared `Sasaah Studio` tab of 15 §2. (c) Process: 15 requires the hub process (approved spec and plan, tests first); Sasaah specs are Draft. | Keep in Sasaah. Do not build `synapse` under `products/`. Owner decides whether SAFE and SAP2000 sync becomes a Sasaah spec. |
| `revit-sheet-exporter` (Revit, PDF and DWG export with naming and set rules) | Project `04_Deployments/Sasaah.Studio.Revit.Addin`, command `Commands/SheetExporterCommand.cs`, registered on the `Sasaah Studio` tab (`Commands/SheetExporterModule.cs`). Engine `02_Engines/Sasaah.Revit.Engine`: `Pipeline/ExportPipeline.cs`, `Pipeline/ExportRequest.cs`, `Services/DwgExportService.cs`, `Services/SheetCollector.cs`, `Services/LayoutPlanner.cs`, `Services/SheetSizeProbe.cs`, `Acad/DwgNormalizer.cs`, `Acad/AccoreDwgMerger.cs`. Features read: pick sheets, choose a saved or in-session DWG export setup, output folder and file name, layout direction and spacing, merge into one DWG with a normalize step. The ribbon is built by `Ribbon/RibbonBuilder.cs`, which calls `CreateRibbonTab` in a try block. | (a) PDF export: no PDF code was found under `02_Engines/Sasaah.Revit.Engine` or `03_UI`. (b) Naming rules and set rules: `ExportRequest` carries one file name and a setup name, no rule model. (c) A separate repository and the process of 15. | Keep in Sasaah. Do not build `revit-sheet-exporter` under `products/`. PDF export and naming/set rules are a gap for the owner to decide as a Sasaah feature request. |
| `sasaah-studio-autocad` (AutoCAD, daily commands under the `Sasaah Studio` tab; command list still an owner input) | Project `04_Deployments/Sasaah.Studio.AutoCad.Addin` over `02_Engines/Sasaah.AutoCad.Engine`. Tab `Sasaah Studio` with id `SasaahStudio`, created if missing (`ExtensionApplication.cs`). Commands: `B2L` block to layouts, `CCG` column centring, `CDIM` column grid dimensioning, `GAX` grid annotation (`Commands.cs`), `SBEAM` beam line collapse (`BeamLineCollapseCommands.cs`), `SJOIN` wall line joiner (`WallLineJoinerCommands.cs`), `SCOLSEC`, `SCOL`, `SCOLASSIGN`, `SCOLADOPT`, `SCOLTAB`, `SCOLSTORY`, `SCOLSET`, `SCOLXTEST` smart columns (`SectionCommands.cs`), `SasaahAbout`. Multi-targets `net8.0-windows` and `net48` (`AGENTS.md`, build caveats). | (a) The command list is an owner input in 15, and Sasaah already holds a de facto list (above); the input may only need confirming. (b) Command prefix: 15 §2 asks for `SS` plus a short code; Sasaah commands use other names (`B2L`, `CCG`, `SCOL...`). | Keep in Sasaah. Do not build `sasaah-studio-autocad` under `products/`. Owner confirms whether the existing command set is the list 15 waits for, and whether the `SS` prefix rule applies to existing names. |

## 2. Conflicts between 15 and Sasaah (for the owner)

1. 15 §2 says no add-in owns the `Sasaah Studio` tab and each add-in guards `CreateRibbonTab`. In Sasaah,
   `Sasaah.Studio.Revit.Addin` is a host that discovers modules and builds the tab itself through the shared
   `RibbonBuilder` (with the guard), `Sasaah.Agent.Revit.Bridge` creates a tab of its own (`Ui/BridgeRibbon.cs`), and
   Synapse uses a separate `Sasaah Synapse` tab.
2. [03](../design/docs/architecture/03-repositories.md) §2 and §5 list the products as separate repositories with their
   own Revit API and CSI API dependencies. In Sasaah they share engines (`Sasaah.Revit.Engine`, `Sasaah.Core`,
   `Sasaah.UI`), so a split is a refactoring, not a copy.
3. 15 §4 and 03 §3 forbid copying code between repositories, so a split needs shared libraries by ADR.
4. Sasaah's WPF interface project (`03_UI/Sasaah.UI`) and its style file are not reused in this repository (workspace
   rules).

## 3. Sasaah material read

`PRODUCT.md` (purpose: Revit to ETABS bridge), `AGENTS.md` (build and CI), `specs/005` to `009` (Synapse UX and sync;
008 and 009 concern the MCP servers and hot reload, not the products) and `docs/stylist-rebuild/design.md` (a separate
Revit add-in, the Stylist, which states that Studio, Synapse and the AutoCAD add-in stay untouched; it is not one of
the three products and is out of scope here).

## 4. Owner queue

- O-1: Confirm that the three products stay in Sasaah and `products/` stays empty in v1 (ADR-0033).
- O-2: Whether and when to split, and how the shared engines are handled (a library by ADR).
- O-3: SAFE and SAP2000 sync in Synapse: a Sasaah feature, or dropped from 15.
- O-4: PDF export and naming/set rules in the sheet exporter: a Sasaah feature, or dropped from 15.
- O-5: Is the existing AutoCAD command set the list 15 waits for, and does the `SS` prefix apply to it.
- O-6: Tab ownership: amend 15 §2 to match the Sasaah module host, or change Sasaah.
