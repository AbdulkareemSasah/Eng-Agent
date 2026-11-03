# eng-dev-gate

The gate of the Eng-Agent platform: one command, `eng-gate`, that enforces the process rules locally and in CI
(exit codes 0 pass or awaiting owner, 1 rule failed, 2 usage or configuration error, 3 environment or tool error).

- Spec: [docs/specs/0001-eng-dev-gate-0.1.md](docs/specs/0001-eng-dev-gate-0.1.md)
- Plan: [docs/plans/0001-eng-dev-gate-0.1.md](docs/plans/0001-eng-dev-gate-0.1.md)
- Runtime dependencies: [docs/adr/0001-runtime-dependencies.md](docs/adr/0001-runtime-dependencies.md) (Proposed)
- Live steps: [docs/local-testing.md](docs/local-testing.md)

Status: skeleton (plan task T1). The commands are registered but not implemented yet.

```
uv sync
uv run eng-gate --version
uv run pytest
```
