# harness.column_change_set

- Calc id, version and content hash: `harness.column_change_set` v1; the hash is the entry in `src/eng_harness/calcs/calcs.lock.json`
- Status: draft (bootstrap mode, ADR-0028 section 4; owner approval awaited, spec 0013 CW-G12)
- Method source: spec 0013 section 4.4.4 and gap CW-G3. Input: `matches` (each entry is a frame id with the body of `harness.column_match/1`) and `accepted` (frame ids whose decision is `change_section`). Output `harness.generated_change_set/1` with `source` `harness.column_change_set`, one `frame_section` item (`id` and `frames: [id]`, `section`) per accepted frame whose match status is `matched`, sorted by frame id; every other accepted frame is an issue `NOT_IMPLEMENTED` with gap CW-G3 and no item. The set holds names only; no engineering constant.
- Tests: `tests/unit/calcs/test_column_change_set.py::test_items_and_refusals` (AC10: two matched accepted frames become items sorted by id; `no_section_in_model` and `ambiguous` accepted frames are CW-G3 issues)
- Reviewer and date: awaiting review
- Findings and open gaps: a duplicate `frame_id` in `matches` is `INVALID_ARGUMENT`. An accepted frame with no match entry is refused CW-G3 (same as a non-matched status). Deviation from spec 0013 §4.4.4: the spec says `matches` (references), whereas this calc takes inline `MatchEntry` payloads (`frame_id` plus `harness.column_match/1` body) because the top-level contract pipeline cannot resolve a list of references and `harness.column_match/1` carries no `frame_id`; the input shape should be settled before T10 wires it.
