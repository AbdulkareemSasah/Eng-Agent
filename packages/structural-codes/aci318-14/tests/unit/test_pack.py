"""Pack-level tests (plan 0002 T9; PK-AC3, PK-AC4, PK-AC6)."""

import importlib
import os
import pkgutil
from collections.abc import Mapping
from importlib import resources
from pathlib import Path
from typing import Any

import pytest
from eng_contract.cited import Cited
from eng_contract.verdicts import Subject, SubjectKind
from structural_codes import evaluate
from structural_codes.content_hash import lint_scope_violations
from structural_codes.errors import CheckNotUsable
from structural_codes.lifecycle import resolve_state
from structural_codes.pack import Registry

import aci318_14
from aci318_14 import PACK

_IDS = [
    "aci318_14.13_2_7_1.flexure_at_column_face",
    "aci318_14.13_3_1_1.bearing_pressure_service",
    "aci318_14.22_5_5_1.one_way_shear",
    "aci318_14.22_6_5_2.punching_shear",
    "aci318_14.25_4_2_3.development_length_bottom_bars",
    "aci318_14.8_6_1_1.min_flexural_reinforcement",
]
_CLAUSES = Path(__file__).parents[3] / "docs" / "clauses"
_PREFIXES = ("ACI 318-14 ", "SI prefix", "Mechanics of materials", "Statics", "Geometry")
_MODULES = ["src/aci318_14/**/*.py"]


def test_registry_and_specs() -> None:
    """Discovery finds the pack with exactly the six checks, each naming an existing clause spec (PK-AC3).

    The clause specs sit outside the member; mutmut's copy of it (``MUTANT_UNDER_TEST`` set) lacks them, so only there,
    after the registry assertions, a missing folder skips; in every other run it fails (as B-369 and B-423).
    """
    registry = Registry.discover()
    pack = next(p for p in registry.packs if p.name == "aci318_14")
    assert pack is PACK
    assert (pack.code, pack.edition, pack.version) == ("ACI 318-14", "2014", aci318_14.__version__)
    assert [c.meta.check_id for c in registry.checks if c.meta.pack == "aci318_14"] == _IDS
    if not _CLAUSES.is_dir() and "MUTANT_UNDER_TEST" in os.environ:
        pytest.skip("the clause specs are outside the copy the mutation step runs (B-444); expires 2026-12-31")
    for c in pack.checks:
        assert (_CLAUSES / c.meta.spec).is_file(), c.meta.spec


def _cited() -> list[Cited]:
    found: list[Cited] = []
    for info in pkgutil.walk_packages(aci318_14.__path__, "aci318_14."):
        for value in vars(importlib.import_module(info.name)).values():
            if isinstance(value, Cited):
                found.append(value)
            elif isinstance(value, Mapping):
                found.extend(v for v in value.values() if isinstance(v, Cited))
    return found


def test_lint_scope_and_citations() -> None:
    """No check reaches outside the pack source; every Cited source has an allowed origin (PK-AC4)."""
    for c in PACK.checks:
        assert lint_scope_violations(c, _MODULES) == (), c.meta.check_id
    cited = _cited()
    assert len(cited) > 20
    assert [x.source for x in cited if not x.source.startswith(_PREFIXES)] == []


def test_all_draft() -> None:
    """The shipped approvals file is empty, so every check is draft and production mode refuses it (PK-AC6)."""
    assert resources.files(PACK.name).joinpath(PACK.approvals).is_file()
    registry = Registry.discover()
    subject = Subject(kind=SubjectKind.FOOTING, id="F1")
    for c in PACK.checks:
        assert resolve_state(c, registry) == "draft"
        inputs: dict[str, Any] = {}
        with pytest.raises(CheckNotUsable):
            evaluate(c.meta.check_id, inputs, subject=subject, mode="production", registry=registry)
