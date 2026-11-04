# Changelog

## Unreleased

- Package skeleton: `pyproject.toml`, gate configuration, `__version__` (B-255).
- Errors, check metadata and the check_id rule: `structural_codes.errors`, `structural_codes.meta` (B-256).
- Check inputs, `bounded` and `unbounded` helpers, `ratio_limit` and preconditions: `structural_codes.inputs`, `structural_codes.applicability` (B-257).
- Trace recorder: `structural_codes.trace.TraceRecorder` (B-258).
- Verdict builder `TraceRecorder.verdict` and governing selection `structural_codes._verdict` (B-259).
- Check decorator, packs and registry: `structural_codes.check`, `structural_codes.pack`, `synthbase` test fixture pack (B-260).
- Content hash over the static import closure (pack, `structural_codes`, `eng_contract`), dynamic-import rejection and `lint_scope_violations`: `structural_codes.content_hash`, `structural_codes._closure`, `hashpack` test fixture pack (B-261). The dynamic-import rule applies to the check's pack modules only; `structural_codes` and `eng_contract` sources are hashed but exempt, so every real pack (which builds `PACK` with `structural_codes.pack`) can be hashed.
