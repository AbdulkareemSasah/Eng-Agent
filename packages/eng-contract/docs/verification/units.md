# Verification record: units of canonical/1 (plan T5, spec 4.7.3)

Status: **draft, not verified by an independent verifier** (process/10 §3). The owner confirms the factor table (OQ-G4).

## 1. Gap G-4: citations not confirmed

The cited documents (BIPM, *SI Brochure*, 9th edition (2019); NIST SP 811, 2008 edition) were not readable here: they
are outside the allowed services and no copy is in the workspace. No table, section or page below is confirmed; they
are the spec's. The values are the exact definitions the spec names, not read from a document either. The independent
verifier compares each row with the document before approval. The spec says to remove an unconfirmable entry; the base
lengths and forces stay (nothing could convert without them), marked unconfirmed, for the owner to decide.

| Entry | Exact value typed in `_unit_table.py` | Cited location (spec 4.7.3) | Checked |
|---|---|---|---|
| `m`, `kg`, `s`, `K` | coherent SI units | SI Brochure 9th ed., Table 2 | no |
| `rad`, `N`, `Pa` | rad; kg m/s2; N/m2 | SI Brochure 9th ed., Table 4 | no |
| prefixes `m` `c` `k` `M`, and `G` (for `GPa`; not in the spec's row) | 1/1000, 1/100, 10^3, 10^6, 10^9 | SI Brochure 9th ed., Table 7 | no |
| `t`, `deg`, `min`, `h` | 1000 kg; (pi/180) rad; 60 s; 3600 s | SI Brochure 9th ed., Table 8 | no |
| `degC` | T/K = t/degC + 273.15 | SI Brochure 9th ed., 2.3.1; NIST SP 811 4.2.1.1 | no |
| `in`, `ft`, `lb`, `g_n`, `degF` | 0.0254 m; 0.3048 m; 0.45359237 kg; 9.80665 m/s2; (t/degF - 32)/1.8 | NIST SP 811 (2008), Appendix B.8 (`g_n`: 3rd CGPM (1901)) | no |

Derived, never typed: `kgf` = kg x g_n; `lbf` = lb x g_n (4.4482216152605 N); `kip` = 1000 lbf; `tonf` = t x g_n
(9806.65 N; its use for CSI `Ton` is gap G-1); every other unit is a product or quotient of these, in `Fraction`.

## 2. Tests

`tests/data/units/factors.json` holds the expected exact factor, dimension, pi power and offset of 93 units, derived
once outside the package with plain `Fraction` arithmetic from the decimals above (derivation in each row). Hand-run
mutants (g_n, both temperature offsets, the pi power of `deg`, an alias, the dimension and finite checks) were all caught;
the gate's mutation tool is not available yet.

## 3. Deviations from the spec text

- The spec says four `Ton_*` systems; the 16 CSI names (as in the Sasaah CSI engine's mirror) hold three: `Ton_mm_C`,
  `Ton_m_C`, `Ton_cm_C`. All raise `UnitGapError`, a `UnitError` (code `UNIT_MISMATCH`; spec 6 has no other unit code).
- `UNITS` holds every force x length moment, line load, stress and unit weight (a superset of the spec's list) so every
  derived CSI symbol (for example `lbf/in2`) exists; `cm/s2` is also present.
- "Longest suffix wins" has no effect: no suffix of the table ends another (a test asserts it).
