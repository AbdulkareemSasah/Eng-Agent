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
- Base-commit gate: the global `--gate-root` option reads the policy and the mode from a checkout of the pull request's base commit while the head is the tree under check; provenance rule CF009 (gate root is not the base commit, running package outside it, head run with bootstrap off or when the base has the job's action) and AW09 for the first pull request of a job; `GateContext` is the reader that judging checks must use; the `agents drift` handler does not read it yet and is wired in a follow-up task (B-055, plan task T26).
- CI part 1: the root workflow is thin and calls the composite actions `setup`, `gate`, `agents-drift` and `build` with the base-first steps (head checkout, base checkout into `.gate-base`, guarded base and head variants); the `gate` job runs `check --all` (any set of members) and the spike checks, the `windows` job stays on pushes to `build/v1`; new command `packages` (`--names`, `--json`) (B-035, plan task T6).
- `licenses` step and command (allowed licenses of the dependency closure read from `importlib.metadata`, LC001 to LC003, exceptions from `.gate/gate.yml`) and the `docs-fresh` step (generated documents compared with their regeneration, GF001, GF002; AGENTS.md drift of the package) registered in `check` (B-048, plan task T19).
