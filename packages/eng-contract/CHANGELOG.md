# Changelog

## Unreleased

- Package skeleton: `pyproject.toml`, gate configuration, version constants `CONTRACT_VERSION`, `UNITS_VERSION`,
  `__version__` (B-010).
- Error codes, retry rules, warnings and `ContractError` (`errors`, internal `_types`), spec 4.2.3 and 4.2.4 (B-011).
- Canonical JSON (RFC 8785): `canonical_json`, `loads`, `payload_sha256`, `CanonicalJsonError`, spec 4.3.1 (B-012).
- ULID identifiers, `Timestamp`, clocks and id sources (`ids`, internal `_ulid`), spec 4.3.2 (B-013).
- Units of canonical/1: exact cited factors, `convert`, `convert_exact`, quantity kinds, field suffixes and the CSI unit systems (`Ton_*` raise `UnitGapError`, gap G-1), spec 4.7 (B-014). Factor citations unconfirmed (gap G-4, `docs/verification/units.md`).
- `Quantity`, `LabeledQuantity` (no arithmetic, physical equality, same-dimension ordering, consistent hash) and `Cited`, spec 4.8 (B-015). A float enters the exact comparison as its shortest round-trip decimal so that AC35 holds (owner queue).
- Build: the package declares its own test dependencies (pytest, Hypothesis) in `[dependency-groups] dev`, so it keeps them when it leaves the workspace and the gate's imports rule IM006 finds them declared; its tool configuration uses only keys of the gate's allowed set (eng-dev-gate spec 4.12): a `[tool.ruff]` table with `line-length`, `src` and the root's rule set in place of `extend`, no `[tool.mypy]` table (the root's applies, `warn_unreachable` included), pytest `addopts` without the coverage options and no `[tool.coverage.*]` tables, because the gate runs coverage itself with the thresholds of `[tool.eng-gate]` (B-093).
- Provenance, envelopes (`SuccessEnvelope`, `FailureEnvelope`, `Envelope`), `make_success`, `make_failure` and `ResultRecord`, spec 4.2.2, 4.2.5 and 4.4 (B-016). `RefInput` validates ref text with a local pattern until `refs` (T8) defines `RefString`.
