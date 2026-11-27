# Eng-Agent Design Hub

This folder is the single source of truth for the architecture and the development process of a family of
independent, open-source engineering tools: MCP servers for Revit, ETABS, SAFE, SAP2000 and IDEA StatiCa,
structural code packs, and an engineering harness that runs engineer-defined workflows on top of them.

No product code lives in this folder. Each tool is an independent package; while private, the packages incubate
together in one workspace repository, `eng-platform`, and each becomes its own public repository when it goes open
source ([ADR-0001](docs/adr/0001-independent-repositories-private-first.md)). `eng-platform` is the repository that
holds this hub as its `design/` folder ([ADR-0028](docs/adr/0028-build-v1-in-this-repository.md)). This hub holds:

| Folder | What it holds | Normative? |
|---|---|---|
| `docs/architecture/` | How the system is shaped: principles, components, contracts, data flow | Yes |
| `docs/adr/` | Architecture Decision Records: one decision per file, with context and alternatives | Yes |
| `process/` | The development process every contributor (human or AI agent) must follow | Yes |
| `process/templates/` | Templates for specs, plans, ADRs, PRs, issues, and per-repo agent files | Yes |
| `00-OVERVIEW-AR.md` | Arabic overview of every decision, for the product owner's review | Informative |
| `AGENTS.md` | Rules for any agent working inside this hub | Yes |

## Reading order

1. [00-OVERVIEW-AR.md](00-OVERVIEW-AR.md): the whole picture in Arabic.
2. [docs/architecture/01-vision-and-principles.md](docs/architecture/01-vision-and-principles.md)
3. [docs/architecture/02-system-overview.md](docs/architecture/02-system-overview.md)
4. [docs/architecture/03-repositories.md](docs/architecture/03-repositories.md)
5. [docs/architecture/04-tool-contract.md](docs/architecture/04-tool-contract.md): the contract every tool obeys.
6. The component documents (`05` to `19`) for the area you work on.
7. [process/README.md](process/README.md) before writing any code anywhere.

## Status

Phase: **build v1** ([ADR-0028](docs/adr/0028-build-v1-in-this-repository.md)). The owner decided on 2026-11-03 to
build v1 code-complete in this repository before live testing, on the branch `build/v1` in bootstrap mode; `main` keeps
the approved design until the owner merges after the local tests.
On 2026-11-03 the design was revised from evidence in real sessions (ADR-0024 to ADR-0027, accepted by the owner):
the harness runs on the existing Sasaah MCP servers and tools, the first workflow is the model edit cycle, a project
lane allows building tools during live projects, and the full UI is deferred.
The design was reviewed by two independent ECC architect reviews (architecture, and process enforceability); their
findings are incorporated.
Each document states its status in its header: `Draft`, `Proposed`, or `Accepted`.

## Rules for this hub

- Every architectural change lands here first, as an ADR plus edits to the affected documents, before code in any repository changes.
- Documents describe intent and contracts. They never duplicate code; code-level detail lives in each repository.
- Names marked *working name* are not final until [ADR-0022](docs/adr/0022-repository-names.md) is accepted.
