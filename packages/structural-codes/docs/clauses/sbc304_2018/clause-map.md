---
id: clause-map-sbc304_2018
issue: "B-072"
status: draft        # draft | approved (approved only by merging this file's own pull request)
size: standard
risk: r1
---

# Data-file spec: SBC 304-2018 clause map

Pack: sbc304_2018 · Base: aci318_14 · Author: agent identity (bootstrap mode,
[ADR-0028](../../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §4) · Independent verifier: pending
(C3, [process/10](../../../../../design/process/10-engineering-verification.md) §3) · Owner confirmation: awaiting owner

This file specifies `packages/structural-codes/sbc304-2018/src/sbc304_2018/clause_map.py` and is the `CheckMeta.spec`
of every SBC check. Design: [spec 0003](../../specs/0003-sbc304-2018-footing-overlay.md) ("SP §n"); overlay rules:
[10](../../../../../design/docs/architecture/10-structural-codes.md) §5 and
[core spec 0001](../../specs/0001-core-framework.md) §4.11. Base checks:
[ACI clause specs](../aci318_14/).

## 1. Source statement

No SBC 304-2018 text was available to the author, and memory is not a source (process/10 §2). This file therefore
states **no SBC clause number and no SBC content**. Every row is `unconfirmed`. The base clause chains in §3 are copied
from the header of each ACI clause spec; they say what the owner must compare, not what SBC contains.

## 2. Row format

`MapRow` is a frozen dataclass with string fields only (no numbers):

| Field | Type | Rule |
|---|---|---|
| `base_check_id` | `str` | An existing `aci318_14` check id; unique in the map |
| `status` | `MapStatus` | `inherited` or `unconfirmed`; nothing else is accepted (SP §4.1) |
| `sbc_clause` | `str` or `None` | `inherited`: the SBC 304-2018 clause number as printed, 1 to 40 characters; `unconfirmed`: `None` |
| `sbc_source` | `str` or `None` | `inherited`: document, edition, clause and page the row was checked against (8 to 500 characters); `unconfirmed`: `None` |
| `gap_id` | `str` or `None` | `unconfirmed`: `^G-[1-9][0-9]*$`, unique in the map (`G-0` is reserved for the missing-row default, SP §4.3); `inherited`: `None` |
| `base_clauses` | `tuple[str, ...]` | The base clause chain of §3, first entry the base check's first clause |
| `confirm` | `str` | The row's "Also confirm" cell of §3, verbatim, 1 to 500 characters; goes into the gap reason, which adds "and the common items of clause-map §3" |

Rules (SP AC2): any other status, a missing or extra field for the status, or a duplicate raises
`CheckDefinitionError` at import. Changing a row changes the content hash of its check (SP AC10). Rows are ordered as
in §3; the test of SP AC1 compares them with the table of §3 field by field, so this file and the module change in the
same pull request.

## 3. Rows

Common to every row (stated once; the gap reason refers to them): (a) the SBC 304-2018 clause
number that corresponds to each clause of the base chain; (b) that the equations, constants, table rows and limits in
§4 and §5 of the base clause spec are the same in SBC 304-2018 in SI form; (c) that no SBC local modification
(10 §2: durability, hot weather, local materials and others) changes the check's applicability or inputs; (d) the
resulting status: `inherited` with `sbc_clause` and `sbc_source`, or a reserved status with its own clause spec.

<!-- clause-map-rows:start -->
| Gap | Base check | Status | Base clause chain | Also confirm |
|---|---|---|---|---|
| G-1 | `aci318_14.13_3_1_1.bearing_pressure_service` | unconfirmed | 13.3.1.1 | The SBC rule for sizing the base area from service loads and the allowable soil pressure, and whether the allowable pressure comes from the geotechnical report as in the base spec |
| G-2 | `aci318_14.22_5_5_1.one_way_shear` | unconfirmed | 22.5.5.1, 22.5.1.1, 22.5.3.1, 13.3.3.1, 13.2.7.2, 21.2.1, 19.2.1.1, 19.2.4.2 | The one-way shear strength expression, the shear strength reduction factor, the location of the critical section and the concrete strength limits |
| G-3 | `aci318_14.22_6_5_2.punching_shear` | unconfirmed | 22.6.5.2, 22.6.1, 22.6.4.1, 22.6.5.3, 22.6.3.1, 13.3.3.1, 21.2.1, 19.2.1.1, 19.2.4.2 | The three two-way shear stress expressions and their location factor, the critical perimeter, the strength reduction factor and the concrete strength limits |
| G-4 | `aci318_14.13_2_7_1.flexure_at_column_face` | unconfirmed | 13.2.7.1, 13.3.3.1, 22.3.1.1, 22.2.2.1, 22.2.2.4.1, 22.2.2.4.3, 21.2.1, 21.2.2, 20.2.2.4, 19.2.1.1 | The moment section, the stress-block assumptions and factor table, the strength reduction factors and their strain limits, and the steel strength limit |
| G-5 | `aci318_14.8_6_1_1.min_flexural_reinforcement` | unconfirmed | 8.6.1.1, 13.3.3.1, 20.2.2.4 | The minimum flexural reinforcement rows and the referral from footings to the two-way slab minimum |
| G-6 | `aci318_14.25_4_2_3.development_length_bottom_bars` | unconfirmed | 25.4.2.3, 25.4.2.1, 25.4.2.4, 25.4.1.4, 13.2.7.1, 19.2.1.1, 19.2.4.2, 20.2.2.4 | The development length expression, its modification factors and their limits, the limit on the square root of concrete strength and the minimum length |
| G-7 | `aci318_14.22_4_2_1.max_axial_strength` | unconfirmed | 22.4.2.1, 22.4.2.2, 10.5.1.1, 21.2.1, 21.2.2, 6.2.5, 6.2.5.1, 19.2.1.1, 20.2.2.4 | The nominal axial strength expression, the maximum axial strength factors, the strength reduction factor and the slenderness limit |
| G-8 | `aci318_14.22_4_1_1.axial_flexure_uniaxial` | unconfirmed | 22.4.1.1, 10.5.1.1, 10.5.2.1, 22.2.1, 22.2.2.1, 22.2.2.2, 22.2.2.4.1, 22.2.2.4.3, 20.2.2.1, 20.2.2.2, 21.2.1, 21.2.2, 21.2.2.1, 22.4.2.1, 22.4.2.2, 6.2.5, 6.2.5.1, 19.2.1.1, 20.2.2.4 | The strain-compatibility assumptions, the strength reduction factor transition, the axial cap and the slenderness limit |
| G-9 | `aci318_14.10_6_1_1.longitudinal_reinforcement_limits` | unconfirmed | 10.6.1.1, 10.3.1.2 | The minimum and maximum longitudinal reinforcement ratios for columns |
<!-- clause-map-rows:end -->

Rows G-1 to G-6 are the footing scope of B-072 (10 §9); rows G-7 to G-9 exist because the core requires an entry for
every base check (core AC17) and are added when the column checks are registered (plan 0003 T4).

## 4. Confirmation procedure (owner)

1. Compare the SBC 304-2018 text with the base clause spec of the row, item by item (§3 common items and the row's
   own items).
2. If everything matches: change the row to `inherited` with `sbc_clause` and `sbc_source`, remove `gap_id`, and
   update §3 in the same R1 pull request. The check id changes (SP §4.2): major version and changelog.
3. If SBC differs or has no corresponding clause: leave the row `unconfirmed` and open a task for an SBC clause spec
   (overridden or added) or for a removal with its reason; these statuses need a later version of SP.
4. After the base check is `approved`, add the `inherited-confirmed` entry to `approvals.yaml` (core §4.8). Only the
   owner does this step.

## 5. Owner queue

Each row G-1 to G-9 is one owner-queue item: "confirm SBC 304-2018 against `<base check id>`: the common items and
the row's items". Until a row is confirmed its check returns `NEEDS_ENGINEER` (`SBC_CLAUSE_UNCONFIRMED`).
