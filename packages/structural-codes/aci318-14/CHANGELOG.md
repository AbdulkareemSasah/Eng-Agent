# Changelog

## Unreleased

- Pack assembly: `PACK` with the six footing checks, entry point `structural_codes.packs`, README usage, pack-level tests (B-278).
- Package skeleton: `pyproject.toml`, empty `approvals.yaml`, `__version__`, empty `checks` package (B-270).
- Shared footing statics FS S1 to S5, the one-way shear and flexure integrals, shared constants and preconditions (B-271).
- Check `aci318_14.13_3_1_1.bearing_pressure_service` (13.3.1.1), draft: service soil pressure against the permissible gross pressure of the design basis; gaps G-1 (partial contact) and G-2 (net allowable) give `NEEDS_ENGINEER` (B-272).
- Check `aci318_14.22_5_5_1.one_way_shear`: one-way shear at `d` from the column face, X and Y verdicts, draft (B-273).
- Check `aci318_14.13_2_7_1.flexure_at_column_face`: flexure at the column face, X and Y verdicts, tension-controlled sections only (gap G-2 otherwise), draft (B-275).
- Check `aci318_14.22_6_5_2.punching_shear`: concentric punching shear at `d/2` from the column faces, one verdict; base moments return `NEEDS_ENGINEER` (gap G-4), draft (B-274).
- Check `aci318_14.8_6_1_1.min_flexural_reinforcement`: two-way slab minimum of Table 8.6.1.1 on the gross footing section, X and Y verdicts, draft (B-276).
- Check `aci318_14.25_4_2_3.development_length_bottom_bars`: straight bottom-bar development length (eq. 25.4.2.3a, SI, `Ktr = 0`, 25.4.2.1 floor) against the length beyond the column face, X and Y verdicts; `psi_s = 1.0` for every bar (plan Q10); coated bars and lightweight concrete return `NEEDS_ENGINEER` (gaps G-2, G-1), draft (B-277).
- Shared constants `c_half` and `sf_max` carry the citation texts of their clause spec rows (plan 0002 §1.1); no value changes (B-423).
