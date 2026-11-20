"""Replay test: the payloads do not depend on the hash seed (plan 0003 T3; AC16)."""

import os
import subprocess  # B-327: the test runs this interpreter with a fixed environment
import sys

_SCRIPT = """
import sys
from eng_contract.canonical import canonical_json
from eng_contract.verdicts import Subject, SubjectKind
from structural_codes import evaluate
from structural_codes.pack import Registry
from sbc304_2018 import PACK, check_id_for

# Inputs only, transcribed from ACI HC-1 cases (clause specs §8); same set as test_pack_payloads.
_CASES = {
    "aci318_14.10_6_1_1.longitudinal_reinforcement_limits": ("frame", {"Ag_mm2": 250000, "Ast_mm2": 4000}),
    "aci318_14.13_2_7_1.flexure_at_column_face": (
        "footing",
        {
            "As_x_mm2": 2800, "As_y_mm2": 2800, "FX_kN": 0, "FY_kN": 0, "FZ_kN": 1700,
            "Lx_mm": 2500, "Ly_mm": 2500, "MX_kNm": 0, "MY_kNm": 0, "cx_mm": 400, "cy_mm": 400,
            "d_x_mm": 500, "d_y_mm": 500, "fc_MPa": 28, "fy_MPa": 420, "reaction_height_mm": 0,
        },
    ),
    "aci318_14.13_3_1_1.bearing_pressure_service": (
        "footing",
        {
            "FX_kN": 0.0, "FY_kN": 0.0, "FZ_kN": 1200.0, "Lx_mm": 2500.0, "Ly_mm": 2500.0,
            "MX_kNm": 0.0, "MY_kNm": 0.0, "allowable_kind": "gross", "gamma_c_kN_m3": 24.0,
            "gamma_s_kN_m3": 18.0, "h_mm": 600.0, "q_allow_kPa": 250.0, "reaction_height_mm": 0.0,
            "soil_depth_mm": 1000.0, "surcharge_kPa": 0.0,
        },
    ),
    "aci318_14.22_4_1_1.axial_flexure_uniaxial": (
        "frame",
        {
            "A_bar_mm2": 500, "Mu_kNm": 300, "Mu_other_kNm": 0, "Pu_kN": 1500, "b_mm": 500,
            "d_prime_mm": 60, "fc_MPa": 28, "fy_MPa": 420, "h_mm": 500, "k_factor": 1,
            "lu_mm": 3000, "n_bars_b": 3, "n_bars_h": 3, "transverse_kind": "tied",
        },
    ),
    "aci318_14.22_4_2_1.max_axial_strength": (
        "frame",
        {
            "Ast_mm2": 4000, "Pu_kN": 3000, "b_mm": 500, "fc_MPa": 28, "fy_MPa": 420, "h_mm": 500,
            "k_factor": 1, "lu_mm": 3000, "transverse_kind": "tied",
        },
    ),
    "aci318_14.22_5_5_1.one_way_shear": (
        "footing",
        {
            "FX_kN": 0, "FY_kN": 0, "FZ_kN": 1700, "Lx_mm": 2500, "Ly_mm": 2500, "MX_kNm": 0,
            "MY_kNm": 0, "concrete_class": "normalweight", "cx_mm": 400, "cy_mm": 400,
            "d_x_mm": 500, "d_y_mm": 500, "fc_MPa": 28, "reaction_height_mm": 0,
        },
    ),
    "aci318_14.22_6_5_2.punching_shear": (
        "footing",
        {
            "FX_kN": 0, "FY_kN": 0, "FZ_kN": 1700, "Lx_mm": 2500, "Ly_mm": 2500, "MX_kNm": 0,
            "MY_kNm": 0, "concrete_class": "normalweight", "cx_mm": 400, "cy_mm": 400,
            "d_mm": 500, "fc_MPa": 28, "reaction_height_mm": 0,
        },
    ),
    "aci318_14.25_4_2_3.development_length_bottom_bars": (
        "footing",
        {
            "Lx_mm": 2500, "Ly_mm": 2500, "coating": "uncoated", "concrete_class": "normalweight",
            "cover_x_mm": 75, "cover_y_mm": 75, "cx_mm": 400, "cy_mm": 400, "db_x_mm": 16,
            "db_y_mm": 16, "end_cover_mm": 75, "fc_MPa": 28, "fy_MPa": 420, "s_x_mm": 200, "s_y_mm": 200,
        },
    ),
    "aci318_14.8_6_1_1.min_flexural_reinforcement": (
        "footing",
        {"As_x_mm2": 2800, "As_y_mm2": 2800, "Lx_mm": 2500, "Ly_mm": 2500, "fy_MPa": 420, "h_mm": 600},
    ),
}

base = next(p for p in Registry.discover().packs if p.name == "aci318_14")
registry = Registry.of([base, PACK])
for base_id in sorted(_CASES):
    kind, inputs = _CASES[base_id]
    payload = evaluate(
        check_id_for(base_id),
        inputs,
        subject=Subject(kind=SubjectKind(kind), id="F1"),
        registry=registry,
    ).payload
    sys.stdout.buffer.write(canonical_json(payload.model_dump(mode="json")) + b"\\n")
"""


def _run(seed: str) -> bytes:
    env = {**os.environ, "PYTHONHASHSEED": seed}
    done = subprocess.run(  # noqa: S603  # B-327: fixed arguments, no shell, no untrusted input
        [sys.executable, "-c", _SCRIPT], env=env, capture_output=True, check=True
    )
    return done.stdout


def test_identical_across_hash_seeds() -> None:
    """Canonical JSON of all nine payloads is byte-identical under PYTHONHASHSEED 0 and 1 (AC16)."""
    first = _run("0")
    assert len(first.splitlines()) == 9
    assert first == _run("1")
