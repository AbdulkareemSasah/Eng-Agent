# Golden data for the calcs

One JSON file per case, named `<calc>-<case>.json` (prefixes: fingerprint, diff, readback, summary, round, placement).
Fields, and no others: `source`, `method_ref` (a rule of spec 0003 sections 4.6 to 4.11, such as `§4.7 D3`),
`synthetic` (always `true`), `derivation` (the hand derivation, never computed by the implementation), `inputs`
(`input` and `meta`) and `expected`. Inputs are synthetic and none is a proposed project value. Protected path (R1).
