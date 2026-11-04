# eng-contract

Contract package (layer 1) of the Eng-Agent platform: error codes, canonical JSON, identifiers, units, envelopes and
records, versioned `eng-contract/1`. Spec: [docs/specs/0001-eng-contract-0.1.md](docs/specs/0001-eng-contract-0.1.md).
Plan: [docs/plans/0001-eng-contract-0.1.md](docs/plans/0001-eng-contract-0.1.md).

Install from the workspace root with `uv sync`. Import name: `eng_contract`; other packages may import only the
modules listed in `public_modules` of `pyproject.toml`.

JSON Schema snapshots of every public model and kind are in `docs/schema/`; regenerate them with
`uv run python -m eng_contract._schema_export docs/schema` (a test fails when they are stale). Nothing here talks to a
host program.
