# Changelog

## Unreleased

- Package skeleton: `pyproject.toml`, empty `approvals.yaml`, `__version__`, empty `checks` package (B-270).
- Shared footing statics FS S1 to S5, the one-way shear and flexure integrals, shared constants and preconditions (B-271).
- Check `aci318_14.22_5_5_1.one_way_shear`: one-way shear at `d` from the column face, X and Y verdicts, draft (B-273).
- Check `aci318_14.22_6_5_2.punching_shear`: concentric punching shear at `d/2` from the column faces, one verdict; base moments return `NEEDS_ENGINEER` (gap G-4), draft (B-274).
- Check `aci318_14.8_6_1_1.min_flexural_reinforcement`: two-way slab minimum of Table 8.6.1.1 on the gross footing section, X and Y verdicts, draft (B-276).
