# harness.analysis_summary

- Calc id, version and content hash: `harness.analysis_summary` v1; the hash is the entry in `src/eng_harness/calcs/calcs.lock.json`
- Status: draft (bootstrap mode, ADR-0028 section 4; owner approval awaited, spec 0007 EC-G4)
- Method source: spec 0007 section 4.4.4 with gap EC-G3. Every analysis message is `unclassified`: the severity column of the `Analysis Messages` table is not known from the sources, so no column is read and no classification is invented (counts of `error`, `warning` and `info` stay 0 until the local test confirms the columns). Drift rows are reduced to one per direction, story and case with the highest ratio of their points; the governing drift of a direction is its highest row (a tie goes to the first by story, then case) and a row exceeds when its ratio is strictly above `limits.drift_ratio`, compared exactly. The case is named by its case name (type and step are not part of the key). Status: `FAIL` on an error message, else `NEEDS_ENGINEER` on an unclassified message or a row above the limit, else `PASS`.
- Golden cases (`tests/data/golden/edit_cycle/`; each derived by hand in its `derivation` field, synthetic rows):
  - `analysis-clean.json` (§4.4.4): no message, drifts at or below the limit (a ratio equal to the limit does not exceed). Result: pass.
  - `analysis-messages-unclassified.json` (§4.4.4, EC-G3): four messages, three with a severity-like column, all `unclassified`. Result: needs engineer.
  - `analysis-drift-exceeding.json` (§4.4.4): two points of one story and case, a tie for the governing X drift, a row at the limit left out, two directions. Result: needs engineer.
  - `analysis-no-drifts.json` (§4.4.4): no message, no drift row. Result: pass.
- Boundary and contract tests: `tests/golden/edit_cycle/test_analysis_summary.py` (registration and inputs, trace, the limit boundary on both sides, the exact limit, input order, error and warning severities through the classifier, the refusals with their fields, valid payloads of the kind)
- Reviewer and date: awaiting review
- Findings and open gaps: (1) EC-G3 is open: `has_errors` stays false in every real run until the severity column is confirmed, so an analysis error shows as `unclassified` and goes to the engineer. (2) A cycle with no drift row passes on drifts: reading a missing result is the workflow's step (spec 0007 4.5 step 13), not this calc's. (3) The limit is read as stored (its name carries the canonical unit suffix, as for `harness.change_set_check`).
