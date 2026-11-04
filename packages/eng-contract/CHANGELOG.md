# Changelog

## Unreleased

- Package skeleton: `pyproject.toml`, gate configuration, version constants `CONTRACT_VERSION`, `UNITS_VERSION`,
  `__version__` (B-010).
- Error codes, retry rules, warnings and `ContractError` (`errors`, internal `_types`), spec 4.2.3 and 4.2.4 (B-011).
- Canonical JSON (RFC 8785): `canonical_json`, `loads`, `payload_sha256`, `CanonicalJsonError`, spec 4.3.1 (B-012).
- ULID identifiers, `Timestamp`, clocks and id sources (`ids`, internal `_ulid`), spec 4.3.2 (B-013).
- Units of canonical/1: exact cited factors, `convert`, `convert_exact`, quantity kinds, field suffixes and the CSI unit systems (`Ton_*` raise `UnitGapError`, gap G-1), spec 4.7 (B-014). Factor citations unconfirmed (gap G-4, `docs/verification/units.md`).
- `Quantity`, `LabeledQuantity` (no arithmetic, physical equality, same-dimension ordering, consistent hash) and `Cited`, spec 4.8 (B-015). A float enters the exact comparison as its shortest round-trip decimal so that AC35 holds (owner queue).
- Provenance, envelopes (`SuccessEnvelope`, `FailureEnvelope`, `Envelope`), `make_success`, `make_failure` and `ResultRecord`, spec 4.2.2, 4.2.5 and 4.4 (B-016). `RefInput` validates ref text with a local pattern until `refs` (T8) defines `RefString`.
- References (`refs`, internal `_pointer`): `Ref`, `RefString`, `LocalTraceRef`, `rebase_local_ref`, `parse_ref`, `JsonPointer` (RFC 6901 string form), `RefRule`, `RecordSource`, `resolve_ref` and `ResolvedRef`, spec 4.6 (B-017). Additive details for the owner queue: `RefRule` and `parse_ref` take an optional `field` so errors carry it; `resolve_ref` takes an optional `ids` for the incident id of the `INTERNAL` case; `RecordSource` also has `payload()` for split payloads.
