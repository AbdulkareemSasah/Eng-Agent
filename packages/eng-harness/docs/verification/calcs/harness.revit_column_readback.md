# harness.revit_column_readback

- Version and content hash: v1, pinned in `src/eng_harness/calcs/calcs.lock.json`.
- Status: draft, awaiting owner approval (ADR-0028 §4 and spec 0013 CW-G12).
- Method source: spec 0013 §4.4.6 B1–B4, as amended by B-621, with the U7 identities and Q17 from B-610. Compare the same Revit model's recorded revisions. Only `before` allows stale references. Resolve U1 role pointers against the explicit ETABS `model.sections/1` record and compare exact lengths in mm using the confirmed `compare.length_mm` from the basis.
- Attribution: each present planned assignee gets one issue per applicable new-type issue code. A missing planned element gets only `ELEMENT_MISSING`. Check type changes outside the plan only for elements present in both reads. Sort issues by `(unique_id, code)`. PASS requires no issues and a later after revision.
- AC12 golden cases, with synthetic inputs and hand-derived oracles in `tests/data/golden/column_design/revit-readback-*.json`:
  - `pass`: matching identities and a role difference exactly at the basis tolerance.
  - `wrong-type`: wrong family for a new type and wrong ID for reuse, despite matching names.
  - `value-mismatch`: two role differences over tolerance, deduplicated per assignee, including an assignee with a type mismatch.
  - `unexpected-change`: a type change outside the plan, with an addition and a removal excluded.
  - `missing-and-not-read`: a missing planned element, an unread role set, and an absent type row.
- Reviewer and date: awaiting review.
