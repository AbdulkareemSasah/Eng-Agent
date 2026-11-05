# Changelog

## Unreleased

- Package skeleton: `pyproject.toml`, empty `approvals.yaml`, `__version__`, empty `checks` package (B-270).
- Shared footing statics FS S1 to S5, the one-way shear and flexure integrals, shared constants and preconditions (B-271).
- Check `aci318_14.13_3_1_1.bearing_pressure_service` (13.3.1.1), draft: service soil pressure against the permissible gross pressure of the design basis; gaps G-1 (partial contact) and G-2 (net allowable) give `NEEDS_ENGINEER` (B-272).
- Check `aci318_14.22_5_5_1.one_way_shear`: one-way shear at `d` from the column face, X and Y verdicts, draft (B-273).
