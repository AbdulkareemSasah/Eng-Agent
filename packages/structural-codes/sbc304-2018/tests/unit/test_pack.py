"""Pack-level tests (plan 0003 T3; AC9, AC12, AC13, AC14)."""

import ast
import os
from importlib import resources
from pathlib import Path
from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.verdicts import Subject, SubjectKind
from structural_codes import evaluate
from structural_codes.content_hash import lint_scope_violations
from structural_codes.errors import CheckNotUsable
from structural_codes.lifecycle import resolve_state
from structural_codes.pack import Registry

import sbc304_2018
from sbc304_2018 import PACK, check_id_for

_CLAUSES = Path(__file__).parents[3] / "docs" / "clauses"
_MODULES = ["src/sbc304_2018/**/*.py"]
_SRC = Path(__file__).parents[2] / "src" / "sbc304_2018"

# Provisional overlay ids from clause-map rows G-1 to G-9 (spec 0003 §4.2); short names match the ACI base checks.
_IDS = [
    "sbc304_2018.unconfirmed_aci_318_14_10_6_1_1.longitudinal_reinforcement_limits",
    "sbc304_2018.unconfirmed_aci_318_14_13_2_7_1.flexure_at_column_face",
    "sbc304_2018.unconfirmed_aci_318_14_13_3_1_1.bearing_pressure_service",
    "sbc304_2018.unconfirmed_aci_318_14_22_4_1_1.axial_flexure_uniaxial",
    "sbc304_2018.unconfirmed_aci_318_14_22_4_2_1.max_axial_strength",
    "sbc304_2018.unconfirmed_aci_318_14_22_5_5_1.one_way_shear",
    "sbc304_2018.unconfirmed_aci_318_14_22_6_5_2.punching_shear",
    "sbc304_2018.unconfirmed_aci_318_14_25_4_2_3.development_length_bottom_bars",
    "sbc304_2018.unconfirmed_aci_318_14_8_6_1_1.min_flexural_reinforcement",
]

_BASE_TO_OVERLAY = {
    "aci318_14.10_6_1_1.longitudinal_reinforcement_limits": _IDS[0],
    "aci318_14.13_2_7_1.flexure_at_column_face": _IDS[1],
    "aci318_14.13_3_1_1.bearing_pressure_service": _IDS[2],
    "aci318_14.22_4_1_1.axial_flexure_uniaxial": _IDS[3],
    "aci318_14.22_4_2_1.max_axial_strength": _IDS[4],
    "aci318_14.22_5_5_1.one_way_shear": _IDS[5],
    "aci318_14.22_6_5_2.punching_shear": _IDS[6],
    "aci318_14.25_4_2_3.development_length_bottom_bars": _IDS[7],
    "aci318_14.8_6_1_1.min_flexural_reinforcement": _IDS[8],
}


def test_check_id_for() -> None:
    """Every base check id maps to its provisional overlay id; an unknown id is NOT_FOUND (AC9)."""
    for base_id, overlay_id in _BASE_TO_OVERLAY.items():
        assert check_id_for(base_id) == overlay_id
    with pytest.raises(ContractError) as caught:
        check_id_for("aci318_14.missing.check")
    assert caught.value.detail.code == ErrorCode.NOT_FOUND
    assert caught.value.detail.field == "base_check_id"


def test_registry_and_specs() -> None:
    """Discovery finds the overlay pack with one check per base check and the clause-map spec (AC12).

    The clause map sits outside the member; mutmut's copy of it (``MUTANT_UNDER_TEST`` set) lacks it, so only there,
    after the registry assertions, a missing folder skips; in every other run it fails (as B-369 and B-444).
    """
    registry = Registry.discover()
    pack = next(p for p in registry.packs if p.name == "sbc304_2018")
    assert pack is PACK
    assert pack.base == "aci318_14"
    assert (pack.code, pack.edition, pack.version) == ("SBC 304-2018", "2018", sbc304_2018.__version__)
    assert [c.meta.check_id for c in registry.checks if c.meta.pack == "sbc304_2018"] == _IDS
    assert len({c.meta.check_id for c in registry.checks if c.meta.pack == "sbc304_2018"}) == len(_IDS)
    if not _CLAUSES.is_dir() and "MUTANT_UNDER_TEST" in os.environ:
        pytest.skip("the clause map is outside the copy the mutation step runs (B-444); expires 2026-12-31")
    for c in (c for c in registry.checks if c.meta.pack == "sbc304_2018"):
        assert c.meta.spec == "sbc304_2018/clause-map.md"
        assert (_CLAUSES / c.meta.spec).is_file(), c.meta.spec


def test_all_draft() -> None:
    """The shipped approvals file is empty, so every check is draft and production mode refuses it (AC13)."""
    assert resources.files(PACK.name).joinpath(PACK.approvals).is_file()
    registry = Registry.discover()
    subject = Subject(kind=SubjectKind.FOOTING, id="F1")
    for c in (c for c in registry.checks if c.meta.pack == "sbc304_2018"):
        assert resolve_state(c, registry) == "draft"
        inputs: dict[str, Any] = {}
        with pytest.raises(CheckNotUsable):
            evaluate(c.meta.check_id, inputs, subject=subject, mode="production", registry=registry)


def test_no_engineering_numbers() -> None:
    """No check reaches outside the pack source; no module holds a Cited value or a numeric literal (AC14)."""
    registry = Registry.discover()
    for c in (c for c in registry.checks if c.meta.pack == "sbc304_2018"):
        assert lint_scope_violations(c, _MODULES) == (), c.meta.check_id
    for path in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, int | float)
                and not isinstance(node.value, bool)
            ):
                pytest.fail(f"{path.relative_to(_SRC)}:{node.lineno}: numeric literal {node.value!r}")
            if isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
                if name == "Cited":
                    pytest.fail(f"{path.relative_to(_SRC)}:{node.lineno}: Cited value")
