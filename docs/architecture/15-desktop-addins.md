# 15. Desktop Add-ins: Synapse, Sheet Exporter, Sasaah Studio for AutoCAD

Status: Proposed · Phase 4 (may start after the phase 1 proof, at the owner's choice) · Language: C#

These are products the engineer uses directly inside Revit and AutoCAD. They are independent of the agent stack and
follow the same development process. Detailed specs are written when each one starts.

## 1. Products

| Repository | Host | Purpose |
|---|---|---|
| `synapse` | Revit | Synchronize structural elements between Revit and CSI programs (ETABS, SAFE, SAP2000) from inside Revit |
| `revit-sheet-exporter` | Revit | Export sheets (PDF, DWG) with naming and set rules; appears under the Sasaah Studio tab |
| `sasaah-studio-autocad` | AutoCAD | The engineer's daily AutoCAD commands, under the Sasaah Studio tab. The command list is an owner input, still to be written |

## 2. The shared "Sasaah Studio" tab

`Sasaah Studio` is a ribbon tab name shared by independent add-ins. No add-in owns it.

Revit:
- Each add-in calls `CreateRibbonTab("Sasaah Studio")` inside a try block and ignores the "already exists" error,
  then creates its own panel with a unique name (for example `Sheet Exporter`, `Synapse`, `Agent Bridge`).
- Panel order follows load order and is not guaranteed. No add-in manipulates another add-in's panels.
- The earlier conflict over the tab came from two add-ins creating it without that guard; the guard is a review
  checklist item.

AutoCAD:
- Each add-in finds the tab by its id `SasaahStudio` in the ribbon control, creates it if missing, and adds its own
  panel. Command names use the prefix `SS` plus the add-in's short code to avoid collisions.

Shared conventions (documented in each repository): icon sizes and style, panel naming, tooltip style, version shown
in an "About" button per panel.

## 3. Installation

- Each add-in installs and uninstalls on its own: its own manifest (Revit `.addin` file, AutoCAD bundle) and its own
  folder.
- Installation is done by an installer or a script the engineer runs. Development agents never write into program
  folders or deployment folders ([16](16-security-safety-privacy.md) §7).
- The packaging format (installer type, bundle layout) is decided by ADR when the first add-in is released.

## 4. Relationship to the agent stack

- Synapse talks to CSI programs directly through their API from inside Revit; it does not use the MCP servers.
- Lessons and tested mapping rules from the Sasaah servers (`sasaah-csi-mcp`, `sasaah-revit-mcp`) may be reused as
  references, but code is not copied between repositories. Shared logic, if needed, becomes a library by ADR.
- An add-in may later expose tools through `eng-contract` (for example Synapse's mapping as tools); that is a new ADR.
