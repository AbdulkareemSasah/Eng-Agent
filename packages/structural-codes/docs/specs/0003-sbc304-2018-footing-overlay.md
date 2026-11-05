---
id: spec-0003-sbc304-2018-footing-overlay
issue: "B-072"
status: draft        # draft | approved (approved only by merging this file's own pull request)
size: standard
risk: r1
---

# Spec 0003: SBC 304-2018 overlay for the footing checks

Package: `structural-codes-sbc304-2018` (import package `sbc304_2018`), in `packages/structural-codes/sbc304-2018/`,
layer 3 · Author: agent identity (bootstrap mode,
[ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §4) · Date: 2026-11-04

This spec defines the SBC 304-2018 pack as an overlay on the ACI 318-14 pack
([10](../../../../design/docs/architecture/10-structural-codes.md) §2 and §5, cited as "10 §n";
[ADR-0016](../../../../design/docs/adr/0016-code-packs-lifecycle-and-overlays.md)), using the overlay mechanism of the
[core spec 0001](0001-core-framework.md) ("CF §n") and the contract API of the
[eng-contract 0.1 spec](../../../eng-contract/docs/specs/0001-eng-contract-0.1.md) ("EC §n"). The base checks are the
six footing checks of [plan 0002](../plans/0002-aci318-14-footing-checks.md) §1 and the three column checks of
[plan 0004](../plans/0004-aci318-14-column-checks.md) §1. The clause map, its row format and every row are specified in
the data-file spec [clause-map.md](../clauses/sbc304_2018/clause-map.md) ("CM §n"). Details this spec adds to the
architecture are marked **[added]** and listed in §11.

## 1. Problem

10 §2 states that SBC 304-2018 derives from ACI 318-14 with local modifications, and that the relationship is to be
confirmed clause by clause. A footing designed "to SBC 304-2018" with ACI 318-14 equations under SBC labels would look
verified while no one has compared the two codes: a hidden R1 failure. The SBC pack must therefore make the status of
every check explicit, and must never give `PASS` or `FAIL` for a check whose SBC clause has not been compared with the
ACI implementation from the SBC text.

The author of this spec had no SBC 304-2018 text available, and memory is not a source
([process/10](../../../../design/process/10-engineering-verification.md) §2). So **no row is `inherited` in this
version**: every check is `unconfirmed` and returns `NEEDS_ENGINEER` with a typed gap (CM §3). The pack is still useful
now: the footing workflow (B-075) can run under SBC 304-2018, show the engineer exactly which checks wait for
confirmation, and gain each check the moment the owner confirms its row, without a change to any caller.

## 2. Reuse research

| Candidate | Finding | Decision |
|---|---|---|
| Core overlay (CF §4.11) | `Overlay(base, clause_map, entries)` with `Inherited`, `Overridden`, `Added`, `Removed`; completeness (CF AC17); clause-map consistency (CF AC19) | Used. An unconfirmed check is an `Overridden` entry whose only behavior is a declared `NotImplementedGap` (§4.3) |
| Core gaps (CF §4.4, AC6) | `NotImplementedGap(gap_id, clause, reason)` from a precondition test gives `NEEDS_ENGINEER` with the gap in the trace messages | Used for every unconfirmed check |
| Core lifecycle (CF §4.8) | `inherited-confirmed` approvals for inherited checks, only by the owner | Used unchanged; this pack ships an empty `approvals.yaml` |
| ACI 318-14 pack (plans 0002, 0004) | Input models and check metadata of the nine base checks | Imported from `aci318_14` (declared dependency); nothing copied (A12) |
| A data file in YAML or TOML | Needs file I/O in a pack module (outside the hash closure, CF §4.7; against the proposed FB004 extension, CF §11 Q3) | Not used: the map is a data-only Python module (§4.1) |

## 3. Acceptance criteria

Test paths are relative to `packages/structural-codes/sbc304-2018/`. "Base inputs" are the inputs of the base check's
first hand-check case (its case file under `aci318_14`); they are used only to reach the gap and carry no SBC meaning.

### 3.1 Clause map

- AC1. Given the shipped clause map, when it is loaded, then its rows equal, field by field and in order, the rows of
  the CM §3 table whose base check is registered in the installed `aci318_14` pack (base check id, status, gap id,
  base clause chain, confirmation text), and every row is `unconfirmed`; with all nine base checks registered, no
  check uses the missing-row default `G-0`. Tests: `tests/unit/test_clause_map.py::test_rows_match_clause_map_doc`,
  `tests/unit/test_clause_map.py::test_column_rows_explicit`.
- AC2. Given map rows, when validated, then a row with a status outside `inherited`, `unconfirmed` (including
  `inherited-confirmed`, `confirmed`, `overridden`, `added`, `removed`), an `inherited` row without `sbc_clause` or
  `sbc_source` or with a `gap_id`, an `unconfirmed` row with `sbc_clause` or without `gap_id` and `confirm`, a duplicate
  `base_check_id` or `gap_id`, or a row naming a check absent from the base pack raises `CheckDefinitionError` naming
  the row. Test: `tests/unit/test_clause_map.py::test_row_rules`.
- AC3. Given a base check without a row (for example a check added to `aci318_14` after this map), when the overlay is
  built, then that check gets an `unconfirmed` entry with gap `G-0` and reason `SBC_ROW_MISSING`, and the overlay
  passes the core completeness rule (CF AC17). Test: `tests/unit/test_overlay_builder.py::test_missing_row_default`.

### 3.2 Unconfirmed checks

- AC4. Given each unconfirmed check, a `footing` subject (`column` for the column checks) and its base inputs, when
  evaluated in `trial` mode, then exactly one verdict `NEEDS_ENGINEER` with `demand`, `capacity` and `ratio` null,
  `code` `SBC 304-2018` and `clause` the provisional clause (§4.2); its trace messages contain the gap id, the reason
  `SBC_CLAUSE_UNCONFIRMED`, the base `check_id` and the text "SBC 304-2018 clause not confirmed"; the trace holds no
  step of the base body. Test: `tests/unit/test_unconfirmed.py::test_needs_engineer_with_gap`.
- AC5. Given any inputs inside the base input model's bounds, when an unconfirmed check is evaluated for an in-scope
  subject, then the status is `NEEDS_ENGINEER`, never `PASS` or `FAIL`. Test:
  `tests/property/test_unconfirmed_props.py::test_never_pass_or_fail` (Hypothesis, CI profile `derandomize=True`).
- AC6. Given a subject kind outside the base check's `members`, when evaluated, then `NOT_APPLICABLE` from the
  framework's member-scope step (CF §4.4), as for the base. Test: `tests/unit/test_unconfirmed.py::test_member_scope_copied`.
- AC7. Given each unconfirmed check, when its definition is inspected, then its input model is the base check's input
  model (same class and JSON Schema) and an input outside its bounds gives `OUT_OF_RANGE` (EC §5) as for the base.
  Test: `tests/unit/test_unconfirmed.py::test_inputs_match_base`.

### 3.3 Inherited rows, identifiers and hashes

- AC8. Given a synthetic `inherited` row (test-only, `sbc_clause` and `sbc_source` citing "synthetic test fixture, no
  engineering meaning") for a base check, when the overlay is built, then the entry is a core `Inherited` with that
  clause, the verdicts carry `SBC 304-2018` and that clause (CF AC18), and the check resolves to `draft` until an
  `inherited-confirmed` approval exists (CF AC24). Test: `tests/unit/test_overlay_builder.py::test_inherited_row`.
- AC9. Given a base check id, when `check_id_for(base_check_id)` is called, then it returns the overlay check id of its
  row (provisional while unconfirmed, §4.2); an unknown id raises `ContractError(NOT_FOUND)` with `field:
  "base_check_id"`. Test: `tests/unit/test_pack.py::test_check_id_for`.
- AC10. Given an unconfirmed check, when its row's `confirm` text, gap id or base check changes, or the row turns
  `inherited`, then the check's content hash (CF §4.7) changes. Test:
  `tests/unit/test_overlay_builder.py::test_row_changes_change_hash`.

### 3.4 Pack

- AC11. Given the package, when imported, then `__version__` is set and the shipped `approvals.yaml` is empty
  (CF AC23). Test: `tests/unit/test_package.py::test_version_and_empty_approvals`.
- AC12. Given `Registry.discover()`, when both packs are loaded, then `PACK.base` is `aci318_14`, the SBC pack holds
  one check per base check, ids sorted and unique, and every `CheckMeta.spec` is `sbc304_2018/clause-map.md` (an
  existing file). Test:
  `tests/unit/test_pack.py::test_registry_and_specs`.
- AC13. Given the shipped `approvals.yaml`, when each check's state is resolved, then `draft`, and in `production` mode
  every check is refused with `CheckNotUsable` (CF AC25). Test: `tests/unit/test_pack.py::test_all_draft`.
- AC14. Given the pack sources, when scanned, then `lint_scope_violations` is empty for every check, and no module
  holds a `Cited` value or a numeric literal (AST scan): the pack adds no engineering number. The row validation of
  AC2 needs none: it tests strings for non-emptiness only, and every length limit is the core's (`CheckMeta`,
  `GapDecl`, CF §4.2; CM §2). Test: `tests/unit/test_pack.py::test_no_engineering_numbers`.
- AC15. Given base inputs for every check, when evaluated as one batch per check, then each payload validates as
  `verdicts.set/1` (EC §4.10.2) with `draft: true` and only `NEEDS_ENGINEER` verdicts. Test:
  `tests/contract/test_pack_payloads.py::test_needs_engineer_payloads`.
- AC16. Given the same inputs, when evaluated in two subprocesses with `PYTHONHASHSEED` 0 and 1, then the canonical
  JSON of the payloads is byte-identical. Test: `tests/replay/test_pack_determinism.py::test_identical_across_hash_seeds`.
- AC17. Given the pack, when `python -m structural_codes verify --pack P` runs with `P` the pack project root
  `packages/structural-codes/sbc304-2018/` (CF §4.9.3, amendment B-419), then it exits 0, every
  `boundary` case passes, and every check, the inherited ones included (CF §4.9.3 check set), is reported not
  `verified` (no worked example, G-WE). Test:
  `tests/unit/test_verify_cli.py::test_verify_reports_unverified`.

## 4. Design

### 4.1 Clause map as a data module **[added]**

The map is `sbc304_2018/clause_map.py`: a tuple of frozen `MapRow` values with string fields only (format and rules in
CM §2). A Python data module rather than a YAML or TOML file because it needs no file I/O in a pack module, it is
inside the content-hash closure of every check that imports it (CF §4.7), and the gate's literal lint covers it. The
builder `_overlay.py` validates the rows (AC2) and turns them into a core `Overlay` (CF §4.11):

| Row status | Core entry | Behavior |
|---|---|---|
| `inherited` | `Inherited(base_check_id, clause=sbc_clause)` | Base body, inputs and preconditions; SBC code and clause in verdicts (CF AC18); approval only through `inherited-confirmed` (CF §4.8) |
| `unconfirmed` | `Overridden(base_check_id, check=<gap check>)` | §4.3 |
| none (base check without a row) | as `unconfirmed`, gap `G-0`, reason `SBC_ROW_MISSING` | §4.3; keeps the build green when `aci318_14` gains a check, and is listed as a gap |

`overridden`, `added` and `removed` are reserved: each needs its own SBC clause spec from an SBC source the owner
supplied, and a later version of this spec. A row cannot say `confirmed`: confirmation lives only in `approvals.yaml`
and is the owner's act (10 §5).

### 4.2 Identifiers

An unconfirmed check's clause is the provisional string `unconfirmed (ACI 318-14 <base clause>)`, mapped in
`Overlay.clause_map` to the base clause (CF AC19); its id is therefore
`sbc304_2018.unconfirmed_aci_318_14_<base clause token>.<base short name>`, for example
`sbc304_2018.unconfirmed_aci_318_14_22_6_5_2.punching_shear`. The provisional clause never looks like an SBC clause
number. When the owner confirms a row as `inherited`, the id becomes `sbc304_2018.<SBC clause token>.<base short
name>` (a major version of the pack, process/10 §5). Callers resolve ids with `check_id_for(base_check_id)` and never
hard-code SBC ids (§11 Q1).

### 4.3 The unconfirmed check

Built per row by the builder: `CheckMeta` with `pack="sbc304_2018"`, `code="SBC 304-2018"`, `edition="2018"`,
`clauses=(<provisional clause>,)`, the base `title` prefixed "SBC 304-2018, unconfirmed: ", the base `members`,
`spec="sbc304_2018/clause-map.md"`, `gaps=(GapDecl(<gap id>, <provisional clause>, <reason>),)`; the base input
model; one precondition `SBC_CONFIRMED` (outcome `NEEDS_ENGINEER`, clause the provisional clause) whose test raises
`NotImplementedGap(<gap id>, <provisional clause>, <reason>)`. No body step runs (AC4).

`GapReason` is a `StrEnum` **[added]**: `SBC_CLAUSE_UNCONFIRMED` (the row exists; the SBC clause number, content and
applicability are not confirmed against the ACI implementation) and `SBC_ROW_MISSING` (no row). The reason text is
`"<GapReason>: SBC 304-2018 clause not confirmed for <base check id> (ACI 318-14 <base clause>); to confirm:
<confirm> and the common items of clause-map §3"`.

### 4.4 Pack

`PACK = Pack("sbc304_2018", "SBC 304-2018", "2018", __version__, checks=<built>, approvals=<approvals.yaml>,
base="aci318_14", overlay=<built>)`, registered under `structural_codes.packs`. Runtime dependencies:
`structural-codes-core`, `structural-codes-aci318-14`, `eng-contract` (workspace). `approvals.yaml` ships empty; every
check is `draft` (process/10 §6, bootstrap mode).

### 4.5 Confirming a row (the owner's procedure, CM §4)

The owner, with the SBC 304-2018 text, decides per row: `inherited` (same equations, constants and applicability as the
base clause spec chain; the row gets `sbc_clause` and `sbc_source`), or a reserved status with its own clause spec.
That change is an R1 pull request reviewed by the owner. The owner's `inherited-confirmed` approval follows only after
the base check itself is `approved` (CF AC24). An agent may draft an `inherited` row only from an SBC source the owner
put in its session, citing document, edition, clause and page in `sbc_source`; it never writes an approval.

## 5. Inputs and outputs

The pack defines no tool and no new input: each check takes its base check's inputs (clause specs under
`docs/clauses/aci318_14/`, §3 of each) and returns a `verdicts.set/1` payload through `structural_codes.evaluate`
(CF §4.12). Public names: `PACK`, `check_id_for`, `GapReason`, `MapRow`, `MapStatus`, `CLAUSE_MAP`.

## 6. Errors

| Condition | Error | Contract code and fields |
|---|---|---|
| Invalid map row, unknown base check in the map | `CheckDefinitionError` (at import) | not a `ContractError`; a definition defect |
| Unknown base check id in `check_id_for` | `ContractError` | `NOT_FOUND`, `field: base_check_id` |
| Unconfirmed check evaluated | verdict | `NEEDS_ENGINEER` with the gap (AC4) |
| Inputs, mode, approvals | as the core | CF §6 |

## 7. Non-goals

- Any SBC-specific check (overridden or added), and any claim about SBC 304-2018 clause numbers or content.
- SBC local modifications outside the check equations (durability, hot weather, local materials, 10 §2), which reach
  the footing through design-basis values (cover, concrete strength) rather than the checks (§11 Q6).
- Load factors and combinations (the design basis and the workflow, B-075); the footing block and workflow (B-075).
- Worked examples from books or the code's own examples (owner-supplied, G-WE); program comparisons (none is
  meaningful while every check returns `NEEDS_ENGINEER`).

## 8. Risks

| Risk | Class | Mitigation |
|---|---|---|
| An SBC verdict runs ACI equations that SBC changed | R1 | No row is `inherited` without an SBC source; unconfirmed checks never give `PASS` or `FAIL` (AC4, AC5) |
| A row is marked confirmed by an agent | R1 | No `confirmed` status exists (AC2); confirmation only in `approvals.yaml`, a protected path (CF §4.8) |
| A new ACI check silently runs under SBC | R1 | Missing row defaults to unconfirmed `G-0` (AC3), never to inherited |
| Map and spec drift apart | R1 | AC1 compares the module with the CM §3 table |
| Callers hard-code provisional ids that change on confirmation | R2 | `check_id_for` (AC9); B-075 uses it (§11 Q1) |

## 9. Test strategy

| Criteria | Layer | Location |
|---|---|---|
| AC1 to AC4, AC6 to AC14, AC17 | Unit | `tests/unit/` |
| AC15 | Contract (against eng-contract models) | `tests/contract/` |
| AC16 | Replay | `tests/replay/` |
| AC5 | Property | `tests/property/` |

One `boundary` case per check in `tests/data/golden/verification/<check_id>.yaml` expects `NEEDS_ENGINEER` (the gap
path, CF §4.9.4 (3)); `program_comparison: {not_available: "returns NEEDS_ENGINEER until the SBC row is confirmed"}`.
No hand check exists: the pack evaluates no SBC equation. No fake-host workflow test applies (no host).

## 10. Version impact

New package `structural-codes-sbc304-2018` 0.1.0. Turning a row `inherited`, or any reserved status, changes that
check's id and output: a major version with a changelog entry per `check_id` and a golden diff report (process/10 §5).

## 11. Open questions, gaps and additions

| Id | Question or gap | Owner | Recommendation |
|---|---|---|---|
| Q1 | Unconfirmed ids are provisional and change when a row is confirmed | Owner, B-075 | Accept; the footing workflow resolves SBC ids with `check_id_for` |
| Q2 | The core has no "unconfirmed" entry kind, so an `Overridden` entry carries the gap, and its clause is a provisional string, not a clause "as printed in the code" (CF §4.2) | Owner | Accept for v1; add an `Unconfirmed` entry kind to the core in a minor version if more overlays appear |
| Q3 | No SBC 304-2018 text was available; every row is unconfirmed (CM §3, G-1 to G-9) | Owner | Provide the SBC text (C1, process/10 §3) and confirm rows in the order of CM §3; until then every SBC footing check gives `NEEDS_ENGINEER` |
| Q4 | Which SBC 304-2018 document is authoritative (language, print, errata) | Owner | Name it once; each `sbc_source` cites document, edition, clause and page |
| Q5 | An `approved` entry for an unconfirmed check is accepted by the core (it is an `Overridden` check) and would only make `NEEDS_ENGINEER` usable in production | Owner | Never approve unconfirmed checks; a later core rule may refuse it |
| Q6 | SBC local modifications (10 §2) may change design-basis values the ACI checks read (cover, minimum concrete strength, steel grades) | Owner | Review the SBC design-basis template (B-063) separately from the check rows |
| Q7 | The three column checks are in the map although B-072 covers footings, because the core requires an entry for every base check (CF AC17) | Owner | Accept; their rows are confirmed with the column workflow |
| Q8 | The ACI clause specs carry their own open C items (plan 0002 §6.2, plan 0004); an SBC row can only be `inherited-confirmed` after its base check is `approved` | Owner | Confirm the ACI C items first |
| G-WE | No worked example from a book or the code's own examples for any SBC check | Owner | Supply book, edition, page and example per check once its row is confirmed |
| A1 | **[added]** Data-module clause map (§4.1), provisional ids (§4.2), `GapReason` and the missing-row default (§4.3) | Owner | Accept with this spec |
