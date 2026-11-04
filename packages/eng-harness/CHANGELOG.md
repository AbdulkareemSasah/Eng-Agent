# Changelog

## Unreleased

- Harness codes and the EngineStop, StepError, RunRefused, RunLocked and JournalIntegrityError families (B-101).
- Package skeleton: `pyproject.toml` with the gate configuration, workspace member, `__version__`, `py.typed`, README, rendered `AGENTS.md` and risk map (B-100).
- Servers configuration: `eng_harness.servers` loads and validates the `[servers.*]`, `[cli_tools.*]` and `[host_programs.*]` sections of `harness.toml` (required timeouts, forbidden options); `mcp>=2.3,<3` runtime dependency with ADR-0001 (Proposed) (B-120).
- Process launcher and inspector ports with the POSIX implementation (process group per server, `/proc` identity with the boot id, pidfd-checked terminate): `eng_harness.servers._launcher` and `._procinfo`; the Windows launcher follows in T3 (B-121).
- Template model: `Template`, `Meta`, `Entry`, `Bounds`, `AskItem` and `TemplateInvalid` with citation, canonical-unit, finiteness and bounds rules (B-155; spec 0004 AC1 to AC6).
- Text, date and number formatting and sanitizing: `eng_harness._text` and its culture-invariance rule test (B-175).
- HTML builder: `eng_harness._html` (text escaped by construction, safe tokens, labeled untrusted `<bdi>` fields, style element with its SHA-256 policy source) and the shared style sheet `eng_harness.pages._css` (B-176).
