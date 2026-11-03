# eng-contract

Contract package (layer 1) of the Eng-Agent platform: error codes, canonical JSON, identifiers, units, envelopes and
records, versioned `eng-contract/1`. Spec: [docs/specs/0001-eng-contract-0.1.md](docs/specs/0001-eng-contract-0.1.md).
Plan: [docs/plans/0001-eng-contract-0.1.md](docs/plans/0001-eng-contract-0.1.md).

Install from the workspace root with `uv sync`. Import name: `eng_contract`; other packages may import only the
modules listed in `public_modules` of `pyproject.toml`.

Limits: this skeleton holds only the version constants; the modules arrive task by task (T2 onward). Nothing here
talks to a host program.
