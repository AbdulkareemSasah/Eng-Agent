# Changelog

## Unreleased

- Package skeleton: `eng-gate` command shell with exit codes 0 to 3 and `--version` (B-030, plan task T1).
- Proposed ADR-0001 for the runtime dependencies (owner queue).
- Foundations A: finding and step results with text, JSON, Actions annotation and summary output, POSIX glob matching, GitHub event file reader and the temporary-repository test fixture (B-031, plan task T2a).
- Foundations B: `Git` port with subprocess adapter and workspace member discovery from `[tool.uv.workspace]` (B-057, plan task T2b).
- Configuration: root `.gate/gate.yml`, `GateConfig` and `[tool.eng-gate]` models, coverage and mutation floors (CF001, CF002, CF006 to CF008) and bootstrap mode read only from the gate root (B-032, plan task T3).
- `gate-check` part 1: front matter models, pull-request body parsing, plan and task lookup on the gate branch, file scope (renames count both paths) and diff budget (GC001 to GC009; B-042, plan task T13). `Plan-Task: none (...)`, the lane, base branch, protected paths and the job follow in T14.
