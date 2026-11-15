# harness.design_summary

- Calc id, version and content hash: `harness.design_summary` v1; the hash is the entry in `src/eng_harness/calcs/calcs.lock.json`
- Status: draft (bootstrap mode, ADR-0028 section 4; owner approval awaited, spec 0003 Q10)
- Method source: spec 0003 section 4.9, rules S1 to S6; `report.top_n` from the basis (section 4.4: an integer >= 1, no unit, confirmed, no default); no field is `stale_ok` (section 4.13); the calc holds no constant and no numeric literal
- Golden cases (`tests/data/golden/calcs/`; each derived by hand in its `derivation` field):
  - `summary-basic.json` (S3, AC35): three verdicts on both sides of their own `ratio_limit`; governing, failing, failing members and "top 2 of 3 by ratio". Result: pass.
  - `summary-tie.json` (S2): two equal ratios ordered by subject id, not input order; a verdict without a ratio ranks last and never governs. Result: pass.
  - `summary-not-designed.json` (S4, S6, AC36): a frame without any verdict is `not_designed` and the status is `NEEDS_ENGINEER`; `top_n` 5 over 2 verdicts gives "top 2 of 2". Result: pass.
  - `summary-previous.json` (S5, AC37): newly failing, newly passing, `FAIL` to `NEEDS_ENGINEER` (other change), appeared, disappeared, and a ratio-only change not listed. Result: pass.
  - `summary-member-worst.json` (S5, AC50): one member with a `PASS` and a `FAIL` verdict at two stations is `FAIL` with the larger ratio and appears once in `members` and `failing_members`. Result: pass.
- Boundary and unit tests: `tests/unit/calcs/test_summary.py` (empty set, AC38; S2 order with null station and case first and the canonical-bytes tie; exact ratio comparison one binary64 step apart; verdicts without a ratio; member status order in both input orders; no previous; S6 reasons; `report.top_n` refusals; basis as a record; trace and schema marks; every golden expectation is a valid `DesignSummary`); `tests/contract/test_calc_lock.py::test_stale_ok_fields_match_spec` (AC49)
- Reviewer and date: awaiting review
- Findings and open gaps: the kind has no message field, so the S6 message ("no design results" and the other reasons) is the trace step `status_reasons`. A group of `governing_by_group` whose verdicts all lack a ratio has no row (S2: such verdicts never govern). Without `previous`, every change list is empty (nothing is compared). `complete` is false when any referenced record is incomplete. The calc does not filter by `source`; spec 0002 supplies host verdicts. The live check is local-testing item 16c (spec L-3).
