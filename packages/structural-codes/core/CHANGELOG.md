# Changelog

## Unreleased

- Package skeleton: `pyproject.toml`, gate configuration, `__version__` (B-255).
- Errors, check metadata and the check_id rule: `structural_codes.errors`, `structural_codes.meta` (B-256).
- Check inputs, `bounded` and `unbounded` helpers, `ratio_limit` and preconditions: `structural_codes.inputs`, `structural_codes.applicability` (B-257).
- Trace recorder: `structural_codes.trace.TraceRecorder` (B-258).
- Verdict builder `TraceRecorder.verdict` and governing selection `structural_codes._verdict` (B-259).
- Check decorator, packs and registry: `structural_codes.check`, `structural_codes.pack`, `synthbase` test fixture pack (B-260).
- Content hash over the static import closure (pack, `structural_codes`, `eng_contract`), dynamic-import rejection and `lint_scope_violations`: `structural_codes.content_hash`, `structural_codes._closure`, `hashpack` test fixture pack (B-261). The dynamic-import rule applies to the check's pack modules only; `structural_codes` and `eng_contract` sources are hashed but exempt, so every real pack (which builds `PACK` with `structural_codes.pack`) can be hashed.
- Runner: `structural_codes.evaluate`, `evaluate_batch`, `BatchItem`, `Evaluation` and `Mode` (module `_runner`): validation through `validate_input`, member scope, preconditions, declared gaps, `ERROR` isolation per item, governing verdicts and the `verdicts.set/1` payload (B-262). Until the lifecycle task every check is a `draft` and `production` mode is refused. In a batch, the `field` of an item error is `items[<k>].<field>`, the contract field-path form. A `ValueError` is contained as an `ERROR` verdict only when it is a math-domain error (the message forms of the math module); any other `ValueError` propagates as a defect of the check.
