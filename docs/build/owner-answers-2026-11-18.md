# Owner answers of 2026-11-18 (lead record)

## OQ-Q60: footing spec 0010 4.4.3 rule L1 (bar count of the footing layout, B-396)

The lead put the question to the owner in Arabic in the live session: rule L1 (`n = floor((L - 2c - db) / s) + 1`)
contradicts AC8 and the basis field `reinforcement.max_spacing` (actual spacing at most `s`); the B-396 calc takes the
ceiling (`n = ceil(span / s) + 1`), more steel, the safe side. Options: the ceiling (amend the spec), or keep the floor
(amend AC8).

ANSWERED by the owner: «التقريب للأعلى (ceil)» ("the ceiling").

Consequences (lead): a documents amendment of spec 0010 4.4.3 rule L1 to the ceiling, which also records the two
OQ-Q63 points (a depth with no room for both layers is refused with `OUT_OF_RANGE`, field `dims`; the numbers of a
`WIDTH_TOO_SMALL` row are informative only and T8 never uses them). Under the ceiling, `WIDTH_TOO_SMALL` applies to a
span of zero or less, as the B-396 calc and its verified golden values already do; no new number is introduced. Work
item B-568 (documents), then B-396 (X.T5) is rewritten on the amended spec (its earlier branch was not pushed).

## B-578 re-review B1: ratio_limit of the ACI column checks (2026-11-19)

Question (put in Arabic in the live session): every ACI column check input model accepts an optional `ratio_limit`. In the footing workflow it comes from the confirmed basis field `limits.ratio_limit_ratio`; the column design left it out, so the column checks would silently use the contract default. Options: the basis field, as in the footing workflow (recommended), or the contract default in v1.

ANSWERED by the owner: «حقل الأساس مثل القواعد» (the basis field, as in the footing workflow).

Consequence: harness.column_check_items/1 items carry `ratio_limit` as `{"$ref": "res_<basis id>#/fields/limits.ratio_limit_ratio/value"}` (a fourth reference-object field beside fc_MPa, fy_MPa and k_factor), and plan 0013 T3 emits it. Carried by amendment B-578.
