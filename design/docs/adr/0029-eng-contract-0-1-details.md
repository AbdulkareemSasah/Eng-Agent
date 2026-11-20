# ADR-0029: eng-contract 0.1 details

Status: Proposed · Date: 2026-11-03 · Deciders: owner

## Context

The spec of the first `eng-contract` package
([0001-eng-contract-0.1](../../../packages/eng-contract/docs/specs/0001-eng-contract-0.1.md)) implements
[04](../architecture/04-tool-contract.md) and marks details that 04 left open with **[added]**. Its open question Q1
recommends recording them in 04 through a hub ADR, so that 04 stays the single source and the package does not diverge
from it. Each detail is additive: none changes an existing field, code or rule of `eng-contract/1`.

## Decision

Each item below is written into [04](../architecture/04-tool-contract.md) in the same change.

1. **Sizes.** "KB" is 1024 bytes and "MB" is 1 048 576 bytes: summary limit 4096 bytes, inline `data` limit 16 384
   bytes, payload split 8 388 608 bytes (04 §1, §3.1).
2. **`payload_file`.** A result record whose payload is split carries `payload_file`
   (`<result_id>.payload.json.gz`) instead of `payload`; exactly one of the two is set; `payload_sha256` covers the
   canonical payload in both cases (04 §2).
3. **File sources in provenance.** Provenance has `files`: base name, SHA-256 and size of each input file of a
   file-based result, never a directory path (04 §1; 04 §3.4 already requires the content hash).
4. **`op_id` on errors.** Errors of `TIMEOUT_UNKNOWN_OUTCOME` and `CONFLICT` carry the `op_id`, so a caller can
   reconcile (04 §8.1).
5. **`infos` count.** The `check_model` summary adds `infos` beside `errors`, `warnings` and `clean` (04 §5.2).
6. **`Subject.case`.** A verdict subject may name the governing load case or combination (04 §5.1).
7. **`INTERNAL` for store failures.** A failed write after retries, an id collision, an unreadable record, a hash
   mismatch or a revision regression is reported as `INTERNAL` with an `incident_id`, never as `INVALID_ARGUMENT`
   (04 §3.1, §8.1).
8. **`INVALID_ARGUMENT` for a rejected literal.** Under `ENG_REQUIRE_REFS`, a literal for an `engineering_quantity`
   parameter is rejected with `INVALID_ARGUMENT` (04 §3.5, §8.1).
9. **ASCII unit symbols.** Unit symbols on the wire are ASCII; the moment unit is `kN.m`, not `kN·m` (04 §4).
10. **Canonical JSON reading.** `canonical.loads` is the only parser of canonical bytes; it rejects `NaN`, infinities,
    duplicate keys and overflow, and reads an integer within ±(2^53 − 1) as an integer, a larger literal only if it
    converts exactly to a finite float64. The writer rejects an integer of 2^53 or more (04 §2).
11. **Local trace references.** Inside a stored `verdicts.set/1` payload, `trace_ref` is a local `#/traces/<n>`
    pointer, because a payload cannot contain its own `result_id`; consumers rebase it onto the record they read; a
    full `res_...` reference is rejected there (04 §5.1).

Items 10 and 11 are the "integer rule" and the "local trace references" named in the spec's Q1.

## Consequences

- 04 and the package agree, and 04 remains the single source; the spec keeps its **[added]** marks until it is
  revised after this ADR is accepted.
- Other producers (the harness adapters that wrap Sasaah replies) must follow items 3, 4 and 7 when they build
  envelopes.
- Until the owner accepts this ADR, the 04 text for these items is proposed, like the rest of 04.

## Alternatives considered
- **Leave the details only in the package spec**: two sources of truth, and other packages would not see them.
- **Remove the details from the package**: the package would then fail on cases 04 does not decide (split payloads,
  self-referencing traces, store failures).

## Pre-mortem
The most likely reason this proves wrong is a detail that the first live runs contradict, for example a store failure
that deserves its own code. The early warning is a second code path that works around the rule; the fix is a new ADR
and a minor contract version.
