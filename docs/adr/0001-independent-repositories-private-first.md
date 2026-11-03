# ADR-0001: Independent packages, incubated privately in one workspace, split into public repositories

Status: Proposed (owner decision) · Date: 2026-10-24

## Context

The earlier Sasaah repository coupled Revit, ETABS, IDEA, UI and agent code in one solution: boundaries eroded (UI
depending on the Revit engine, linked source files), builds required every host installed, and nothing could be
released or open-sourced separately. The owner wants every tool to stand alone as an open-source project, but private
until a first version works well.

Separate private repositories from day one have practical problems: PyPI has no private packages, so private packages
must depend on each other through git with access tokens in CI; while the contract is young, almost every change
crosses repositories; and a solo owner pays the coordination cost of many repositories before any value exists.

## Decision

- **Every tool is an independent package** from the first commit: its own `pyproject.toml`, version, changelog,
  `AGENTS.md`, specs, plans, tests and documentation, buildable and testable on its own.
- **Incubation**: while private, the agent-stack packages live in one private uv workspace repository (working name
  `eng-platform`), under `packages/<name>/`. Boundaries are enforced by machine: import rules between packages
  (layer rules from [02](../architecture/02-system-overview.md) §1), and declared dependencies only.
- **Split when public**: when a package is ready to go public, it is split into its own repository with its history,
  and consumers switch from the workspace member to the PyPI release in one change.
- Desktop products (`synapse`, `revit-sheet-exporter`, `sasaah-studio-autocad`) start in their own repositories when
  their phase starts, because they do not share the agent stack.
- A package is created only when its phase starts.

## Consequences

- Contract changes and their consumers change atomically while the design settles.
- No tokens or private package index are needed.
- Independence must be proven by CI (import rules, per-package tests and builds), not by repository walls.
- "Repository" in the process documents means "package directory" during incubation, except for repository-level
  files (CI, branch protection, `CODEOWNERS`), which exist once at the root.

## Alternatives considered

- **Separate private repositories from the start**: true independence, but token-based git dependencies and heavy
  cross-repository coordination for a solo owner. Rejected for the private phase.
- **One monorepo forever**: harder for outside contributors and per-tool open-sourcing. Rejected.

## Pre-mortem

If incubation lets packages couple silently, the split will be painful. Early warning: import-rule exceptions or
packages whose tests need another package's internals. Both are CI failures by design.
