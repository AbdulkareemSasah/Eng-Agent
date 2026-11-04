# eng-harness

Harness (layer 4) of the Eng-Agent platform: the run engine, the journal, the ports and the workflows built on them.
Spec: [docs/specs/0001-engine.md](docs/specs/0001-engine.md). Plan: [docs/plans/0001-engine.md](docs/plans/0001-engine.md).

Install from the workspace root with `uv sync`. Import name: `eng_harness`; other packages may import only the modules
listed in `public_modules` of `pyproject.toml`.

Limits: this skeleton holds only `__version__`; the modules arrive task by task (T2 onward). No host program runs in CI;
what needs the owner's machine is listed in [docs/local-testing.md](docs/local-testing.md).
