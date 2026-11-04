# Changelog

## Unreleased

- Package skeleton: `pyproject.toml` with the gate configuration, workspace member, `__version__`, `py.typed`, README, rendered `AGENTS.md` and risk map (B-100).
- Servers configuration: `eng_harness.servers` loads and validates the `[servers.*]`, `[cli_tools.*]` and `[host_programs.*]` sections of `harness.toml` (required timeouts, forbidden options); `mcp>=2.3,<3` runtime dependency with ADR-0001 (Proposed) (B-120).
- Synthetic Sasaah CSI fake server (test-only, `tests/fakes/sasaah_csi/`), its schema copy of the S-12 inventory, the contract test that keeps them equal and the packaging test that proves tests are not shipped (B-123).
