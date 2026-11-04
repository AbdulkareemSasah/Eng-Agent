# Changelog

## Unreleased

- Package skeleton: `eng-gate` command shell with exit codes 0 to 3 and `--version` (B-030, plan task T1).
- Proposed ADR-0001 for the runtime dependencies (owner queue).
- Foundations A: finding and step results with text, JSON, Actions annotation and summary output, POSIX glob matching, GitHub event file reader and the temporary-repository test fixture (B-031, plan task T2a).
- Foundations B: `Git` port with subprocess adapter and workspace member discovery from `[tool.uv.workspace]` (B-057, plan task T2b).
- Configuration: root `.gate/gate.yml`, `GateConfig` and `[tool.eng-gate]` models, coverage and mutation floors (CF001, CF002, CF006 to CF008) and bootstrap mode read only from the gate root (B-032, plan task T3).
- Check orchestrator: `eng-gate check` with the step registry and the `lock`, `format`, `lint` and `types` steps (ST001), the `ToolRunner` port and its subprocess adapter (B-034, plan task T5).
- `agents render`, `agents keys` and `agents drift` with codes AG001 to AG007; the committed AGENTS.md files of the root and this package equal their rendering, so they are unchanged (B-033, plan task T4).
- `tests` step (`coverage run --branch` with pytest, line and branch compared separately, CV001 to CV003) and the `eng_dev_gate.pytest_plugin` pytest plugin (Hypothesis profile `ci`, deselection guard) (B-036, plan task T7).
