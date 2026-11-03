# 10. Structural Code Packs: `structural-codes`

Status: Proposed · Phase 2 · Language: Python

## 1. Purpose

Turn design code clauses into **executable, verified checks** that return verdicts with a full calculation trace
(P4). Code packs are pure libraries: no host access, no network, no models, no randomness. Same inputs, same outputs,
on every machine.

## 2. Repository layout (uv workspace)

| Package | Import name | Contents |
|---|---|---|
| `structural-codes-core` | `structural_codes` | Check framework, inputs and bounds, trace recorder, verdict builder, overlay mechanism, runner, verification runner, calculation-note renderer |
| `structural-codes-aci318-14` | `aci318_14` | ACI 318-14 checks, implemented with the SI (metric) form of the code's equations |
| `structural-codes-sbc304-2018` | `sbc304_2018` | SBC 304-2018 as an overlay on ACI 318-14 |
| later: `structural-codes-aci318-19` | `aci318_19` | When needed, as a separate edition package |

SBC 304-2018 is derived from ACI 318-14 with local modifications (durability, hot weather, local materials and
others). This relationship is to be confirmed clause by clause during pack work; the overlay mechanism (§5) makes
every difference explicit.

## 3. Anatomy of a check

Each check is one Python function plus metadata, written from the clause specification template
([process/templates/clause-spec.md](../../process/templates/clause-spec.md)).

| Element | Rule |
|---|---|
| `check_id` | Stable: `<pack>.<clause with underscores>.<short_name>`, for example `aci318_14.22_6_5_2.punching_stress_concrete` |
| Metadata | Code, edition, clause numbers, a title in our own words, member types in scope |
| Inputs | Pydantic model in canonical units; every field has physical bounds ([04](04-tool-contract.md) §6); inputs normally arrive as references |
| Applicability | Explicit preconditions. Not applicable gives `NOT_APPLICABLE`; outside the clause's validity (for example a material strength above a clause limit) gives `NEEDS_ENGINEER`, never a silent clamp |
| Body | Pure, deterministic, float64. No I/O, no globals, no time, no random |
| Constants | Every numeric constant is a `Cited` value carrying its source (`Cited(0.75, "ACI 318-14 Table 21.2.1(b)")`). A CI lint rejects bare float literals in check modules |
| Trace | Every intermediate value is recorded with name, value, unit, formula reference and inputs used |
| Output | One or more verdicts ([04](04-tool-contract.md) §5.1) plus the trace, stored as a result |

## 4. Lifecycle: draft, verified, approved

| State | Meaning | Usable in harness |
|---|---|---|
| `draft` | Written, tests may be incomplete | Trial runs only; outputs watermarked `DRAFT` |
| `verified` | Passes all verification requirements in §6 | Trial runs only |
| `approved` | The engineer reviewed and signed it | Production runs |

Approval is bound to a **content hash** of the check's source and metadata. Any change to the check changes the hash
and returns it to `verified` (if tests pass) until approved again. Approvals are recorded in `approvals.yaml`
(check id, hash, engineer, date, evidence links) and changes to that file require the owner's review
([process/06](../../process/06-review-and-merge.md)).

## 5. Overlays (SBC 304 on ACI 318-14)

- The SBC pack declares `base: aci318_14` and a clause map (SBC clause to ACI clause).
- Each base check is either **inherited** (same equation; verdicts carry SBC code and clause numbers), **overridden**
  (SBC-specific implementation), **added** (SBC-only clause), or **removed** (not applicable under SBC).
- Inheritance is never implicit approval: approving the SBC pack requires confirming, check by check, that the SBC
  clause matches the inherited implementation. This is recorded as `inherited-confirmed` in the approvals file.

## 6. Verification requirements

A check reaches `verified` only when all of these hold:

1. **Worked examples:** at least one worked example from the code's own examples or a recognized textbook, stored as
   inputs, expected outputs, tolerance and citation (book, edition, page, example number). Only numbers and citations
   are stored, never copied text or figures.
2. **Program comparison** where a host program computes the same quantity (ETABS or SAFE design output): recorded
   cases within tolerance, with assumption differences documented. Unexplained differences block verification.
3. **Boundary tests** at every applicability limit, and tests for every `NOT_APPLICABLE` and `NEEDS_ENGINEER` path.
4. **Property tests** for physical sense, for example capacity never decreases when concrete strength increases.
5. **Independent review:** the reviewer of the check is not its author (human or agent) and compares it against the
   clause itself.

Default tolerance: 0.5% relative, with an absolute floor per quantity defined in the example.

## 7. Using checks

- Inside the harness: `ctx.calc("aci318_14.22_6_5_2.punching_stress_concrete", ...)` with references. The runner
  evaluates subjects in batch (all footings in one call).
- Outside the harness: a plain Python API (`structural_codes.evaluate(check_id, inputs)`), so the packs are useful to
  anyone. An MCP front end for code packs is possible later, by ADR.
- Calculation notes are rendered from traces (HTML and PDF), in English and Arabic labels, with clause references.

## 8. Copyright

Clause text is not reproduced. Titles and descriptions are written in our own words; equations are expressed as code;
clause numbers are cited. Worked-example data is limited to input and output values with their citation.

## 9. First scope

Driven by the second workflow (isolated footing design): bearing pressure, one-way shear, two-way (punching) shear,
flexure and minimum reinforcement, development length, for ACI 318-14 and SBC 304-2018. Column axial-flexure checks
follow with the column workflow.
