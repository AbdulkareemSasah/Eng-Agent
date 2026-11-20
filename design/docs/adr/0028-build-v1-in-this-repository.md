# ADR-0028: Build v1 in this repository, code-complete before live testing, in bootstrap mode

Status: Accepted (owner, in the build prompt) · Date: 2026-11-03 · Deciders: owner

## Context

ADR-0024 to ADR-0027 are accepted, and the rest of the design is the working proposal. The owner wants the first
complete version (v1) built as code in a cloud environment where the host programs (ETABS, SAFE, SAP2000, Revit, IDEA
StatiCa, AutoCAD) cannot run, and tested afterwards on the owner's Windows machine. The roadmap
([19](../architecture/19-roadmap-and-spikes.md)) assumed the opposite order: live spikes at the start of each phase,
benchmark B-1 before any phase 1 code, and acceptance A4 before phase 2. The separate identities and branch protection
that the process relies on ([process/11](../../process/11-repository-standard.md) §6) are not set up yet, and no
workspace repository exists: ADR-0001 and [03](../architecture/03-repositories.md) call it `eng-platform`.

## Decision

1. **Workspace.** The Eng-Agent repository becomes the private incubation workspace that ADR-0001 and
   [03](../architecture/03-repositories.md) call `eng-platform`. The design hub moves into `design/` with `git mv`;
   its relative links keep working. The hub's `AGENTS.md` ("documents only") moves with it and governs `design/` only.
   The workspace root follows [03](../architecture/03-repositories.md) §1: `packages/`, `tools/`, `.github/`, a root
   `pyproject.toml` as a uv workspace, a root `README.md`, and a root `AGENTS.md` rendered from
   [process/templates/AGENTS.template.md](../../process/templates/AGENTS.template.md); `CLAUDE.md` contains
   `@AGENTS.md`.
2. **Packages.** Every package that will later become its own repository is built here, under `packages/`, with
   `tools/eng-dev-gate` for the gate and `products/` for the desktop products of
   [15](../architecture/15-desktop-addins.md). The owner splits them into repositories after v1. The boundary rules of
   [03](../architecture/03-repositories.md) §3 hold strictly: no package imports another package's internals.
3. **Phasing.** All phases (0 to 4) are built code-complete before live testing. Spikes that need host programs,
   acceptance A1 to A7 ([18](../architecture/18-first-slice-dxf-to-etabs.md) §5) and the A4 time gate move to the
   owner's local test stage. They must pass before any release. Everything that needs a host program is marked
   "needs local test" and listed in the workspace's `LOCAL-TESTING.md`.
4. **Bootstrap mode**, until the owner sets up separate identities and branch protection
   ([process/11](../../process/11-repository-standard.md) §6):
   - The integration branch is `build/v1`, in place of `main`, for every gate. Each task is a branch from `build/v1`
     and a pull request into it, merged by squash after CI is green and a review by a subagent that is not the author.
     `main` keeps the approved design until the owner merges `build/v1` after the local tests.
   - `eng-dev-gate` runs all its checks in CI. A check that needs the owner's approval or another identity reports
     `awaiting owner` instead of failing.
   - Specs and plans are files with `status: draft`. A review by a subagent that did not write them stands in for G1 and
     G2 until the owner approves them; then they are implemented.
   - Engineering content (risk R1: clauses, calcs, thresholds, templates, decision rules) stays draft and goes to the
     owner queue. No agent marks it verified-and-approved or adds it to `approvals.yaml`.
5. **Python version.** One version for the whole workspace: CPython 3.14 (3.14.6 when this was written), pinned in the
   root `pyproject.toml` (`requires-python = ">=3.14,<3.15"`) and in `.python-version` (`3.14`). It is the newest
   stable release that uv offers (3.15 is in beta), and the dependencies the phases need (Pydantic 2.14, the MCP SDK
   2.3, PydanticAI 2.65, mypy 2.4, ruff 0.17) resolve on it.

## Consequences

- "`eng-platform`" in the design, ADR-0001 and ADR-0022 names this repository. The hub's documents are updated in the
  same change: [README](../../README.md), [03](../architecture/03-repositories.md),
  [18](../architecture/18-first-slice-dxf-to-etabs.md) §5, [19](../architecture/19-roadmap-and-spikes.md) §1, §2 and
  R1, [process/README](../../process/README.md), [process/01](../../process/01-lifecycle.md) §4,
  [process/11](../../process/11-repository-standard.md) and the [Arabic overview](../../00-OVERVIEW-AR.md).
- Amends ADR-0001 (the workspace is this repository; desktop products sit under `products/` during v1) and ADR-0021
  (bootstrap mode until identities exist). ADR-0001 and ADR-0021 stay `Proposed`; their acceptance remains with the
  owner.
- Risk R1 (not faster than the engineer) is measured only at the local test stage, after every phase is built, so a
  failed A4 costs more rework than in the phased roadmap. Risk R4 (too many packages at once) is accepted for v1; strict
  boundaries and per-package done criteria contain it.
- Reviews in bootstrap mode come from subagents of one model family. The second CI reviewer of a different family
  ([process/06](../../process/06-review-and-merge.md) §1) and every owner approval are `awaiting owner`.
- Phase time boxes ([19](../architecture/19-roadmap-and-spikes.md) §1) are not set for this build; the owner queue
  asks for them.

## Alternatives considered

- **Separate repositories per package now**: the owner splits them after v1. Rejected for v1.
- **Phase by phase with live tests between phases**: host programs cannot run in the build environment. Rejected by the
  owner for v1.
- **Wait for identities and branch protection before building**: blocks the build. Replaced by bootstrap mode.
- **Python 3.13 or 3.15**: 3.13 is older than needed; 3.15 is a beta.

## Pre-mortem

The likely failure is a v1 that passes every test against fakes and fails in many places at once on the real hosts,
because the fakes built from tool schemas behave differently from the Sasaah servers. Early warning: record-mode
fixtures from the first local runs that differ from the synthetic fakes. A second failure is bootstrap mode becoming
permanent: early warning, `build/v1` merged to `main` before the identities of [process/11](../../process/11-repository-standard.md)
§6 exist.
