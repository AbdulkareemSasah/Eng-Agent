# ADR-0033: The desktop products stay in Sasaah during v1; nothing is built under `products/`

Status: Proposed · Date: 2026-11-03 · Deciders: owner

## Context

[15](../architecture/15-desktop-addins.md) lists three desktop products (`synapse`, `revit-sheet-exporter`,
`sasaah-studio-autocad`), and [ADR-0028](0028-build-v1-in-this-repository.md) §2 reserves `products/` for them in this
workspace. The owner's rule is to build nothing that already exists in Sasaah. The overlap analysis in
[products/README.md](../../../products/README.md) (read from the Sasaah source, no host program run) found that all
three exist there as add-ins: `Sasaah.Synapse.Revit.Addin`, `Sasaah.Studio.Revit.Addin` (with the Sheet Exporter) and
`Sasaah.Studio.AutoCad.Addin`, sharing the engines `Sasaah.Revit.Engine`, `Sasaah.Etabs.Engine`,
`Sasaah.AutoCad.Engine` and the library `Sasaah.Core`. What 15 asks for beyond that is small and specific: SAFE and
SAP2000 sync, PDF export with naming and set rules, and tab and command-prefix conventions. The add-ins are C# and need
host programs, so v1 could not test them in the build environment in any case.

## Decision

1. The three products stay in the Sasaah repository during v1. Nothing is built under `products/`; the folder holds
   only `products/README.md`.
2. Each overlap and each gap in `products/README.md` §4 is an owner-queue item. No work on a gap starts before the
   owner decides.
3. The owner decides later whether to split a product out of Sasaah. A split is a new ADR that names the shared
   libraries (engines, core), because [03](../architecture/03-repositories.md) §3 forbids copying code between
   packages.
4. Until then 15 is read as the target description, not as a build instruction, and its phase 4 build of these three
   products is outside v1. The harness does not depend on them (15 §4).
5. Documents that name the products as separate repositories stay unchanged until the owner accepts this ADR. On
   acceptance, the same change updates 15 (status and §2 on tab ownership), 03 §2 and §5, 19 (phase 4), ADR-0001,
   07 (the sheet-export note), ADR-0022 (the product repositories row) and the Arabic overview (§3).

## Consequences

- No duplicate of existing Sasaah code is created; risk R4 (too many packages at once) shrinks.
- The tab conflict (Sasaah hosts the `Sasaah Studio` tab in one add-in; Synapse uses `Sasaah Synapse`) stays in
  Sasaah and is queued for the owner.
- The requirements of 15 that Sasaah lacks have no home until the owner decides; they are listed, not lost.
- Hub documents that describe separate product repositories are out of step with this proposal until acceptance.

## Alternatives considered

- **Build the three products under `products/` as 15 describes**: duplicates existing Sasaah code and breaks the
  owner's rule.
- **Copy the Sasaah add-ins into `products/`**: forbidden copying between repositories (03 §3), and it forks the code.
- **Split them out of Sasaah now**: needs a decision on the shared engines first; premature before v1.
- **Delete 15**: loses the requirements Sasaah lacks.

## Pre-mortem

The likely failure is drift: the hub describes separate repositories while Sasaah keeps growing the add-ins, and the
later split costs more than a split now. Early warning: a Sasaah change that adds a feature from 15's gap list (PDF
export, SAFE sync) with no record here.
