# Changelog

## Unreleased

- Package skeleton: `pyproject.toml`, gate configuration, version constants `CONTRACT_VERSION`, `UNITS_VERSION`,
  `__version__` (B-010).
- Error codes, retry rules, warnings and `ContractError` (`errors`, internal `_types`), spec 4.2.3 and 4.2.4 (B-011).
- Canonical JSON (RFC 8785): `canonical_json`, `loads`, `payload_sha256`, `CanonicalJsonError`, spec 4.3.1 (B-012).
- ULID identifiers, `Timestamp`, clocks and id sources (`ids`, internal `_ulid`), spec 4.3.2 (B-013).
