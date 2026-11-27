# eng-platform

The private incubation workspace for the Eng-Agent platform ([ADR-0028](design/docs/adr/0028-build-v1-in-this-repository.md)).
Every package of the platform is built here and split into its own repository by the owner after v1.

## Layout

| Path | Contents |
|---|---|
| `design/` | The design hub: architecture, decisions, process (its own `AGENTS.md` governs it) |
| `packages/` | Library, server and harness packages (uv workspace members) |
| `tools/` | Development tools, such as `eng-dev-gate` (uv workspace members) |
| `products/` | Desktop products |
| `spikes/` | Throwaway spikes, each with a `check.py` |
| `.github/` | CI, templates, `CODEOWNERS`, dependency updates |
| `.gate/` | Gate configuration: risk map, ratchet, rendering inputs for `AGENTS.md` |

## Quick start

1. Install [uv](https://docs.astral.sh/uv/). It installs Python 3.14 as pinned in `.python-version`.
2. `uv sync`
3. `uv run pytest`

Use uv for everything; never pip, poetry or conda. Read [AGENTS.md](AGENTS.md) before changing anything.

## State files

- [BUILD-STATUS.md](BUILD-STATUS.md): tasks, lead decisions, owner queue.
- [LOCAL-TESTING.md](LOCAL-TESTING.md): everything that needs a host program and must be tested locally.

Host programs run only on the owner's Windows machine.
