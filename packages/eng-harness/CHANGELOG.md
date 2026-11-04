# Changelog

## Unreleased

- Package skeleton: `pyproject.toml` with the gate configuration, workspace member, `__version__`, `py.typed`, README, rendered `AGENTS.md` and risk map (B-100).
- Servers configuration: `eng_harness.servers` loads and validates the `[servers.*]`, `[cli_tools.*]` and `[host_programs.*]` sections of `harness.toml` (required timeouts, forbidden options); `mcp>=2.3,<3` runtime dependency with ADR-0001 (Proposed) (B-120).
- Text, date and number formatting and sanitizing: `eng_harness._text` and its culture-invariance rule test (B-175).
