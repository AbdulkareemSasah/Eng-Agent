# Changelog

## Unreleased

- Package skeleton: `pyproject.toml`, gate configuration, version constants `CONTRACT_VERSION`, `UNITS_VERSION`,
  `__version__` (B-010).
- Error codes, retry rules, warnings and `ContractError` (`errors`, internal `_types`), spec 4.2.3 and 4.2.4 (B-011).
- Canonical JSON (RFC 8785): `canonical_json`, `loads`, `payload_sha256`, `CanonicalJsonError`, spec 4.3.1 (B-012).
- ULID identifiers, `Timestamp`, clocks and id sources (`ids`, internal `_ulid`), spec 4.3.2 (B-013).
- Units of canonical/1: exact cited factors, `convert`, `convert_exact`, quantity kinds, field suffixes and the CSI unit systems (`Ton_*` raise `UnitGapError`, gap G-1), spec 4.7 (B-014). Factor citations unconfirmed (gap G-4, `docs/verification/units.md`).
- Build: the package declares its own test dependencies (pytest, pytest-cov, Hypothesis) in `[dependency-groups] dev`, so it keeps them when it leaves the workspace and the gate's imports rule IM006 finds them declared (B-093).
