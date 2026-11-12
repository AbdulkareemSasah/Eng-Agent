"""Pack-level tests of the three column checks (plan 0004 T5; CK-AC2, CK-AC3, CK-AC5, CK-AC7)."""

import importlib
import os
import re
import subprocess  # B-334: the test runs this interpreter with fixed arguments
import sys
from collections.abc import Mapping
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

from aci318_14 import PACK

_COLUMN_IDS = [
    "aci318_14.10_6_1_1.longitudinal_reinforcement_limits",
    "aci318_14.22_4_1_1.axial_flexure_uniaxial",
    "aci318_14.22_4_2_1.max_axial_strength",
]
_FOOTING_COUNT = 6
_COLUMN_MODULES = ("_column", "checks.axial_flexure", "checks.max_axial", "checks.reinforcement_limits")
_CLAUSES = Path(__file__).parents[3] / "docs" / "clauses"
_ROOT = Path(__file__).parents[2]
_PREFIXES = ("ACI 318-14 ", "SI prefix", "Statics", "Geometry", "Numerical method")
_MODULES = ["src/aci318_14/**/*.py"]


def _column_checks() -> list[Any]:
    return [c for c in PACK.checks if c.meta.check_id in _COLUMN_IDS]


def test_registry_and_specs() -> None:
    """The pack holds the six footing ids and the three column ids; each column spec file exists (CK-AC2).

    The clause specs sit outside the member; in the mutation step's copy (``MUTANT_UNDER_TEST`` set) a missing folder
    skips after the registry assertions (as test_pack.py, B-444).
    """
    registry = Registry.discover()
    ids = [c.meta.check_id for c in registry.checks if c.meta.pack == "aci318_14"]
    assert len(ids) == _FOOTING_COUNT + len(_COLUMN_IDS)
    assert sorted(set(ids) & set(_COLUMN_IDS)) == _COLUMN_IDS
    assert [c.meta.check_id for c in _column_checks()] == [
        "aci318_14.22_4_2_1.max_axial_strength",
        "aci318_14.22_4_1_1.axial_flexure_uniaxial",
        "aci318_14.10_6_1_1.longitudinal_reinforcement_limits",
    ]
    if not _CLAUSES.is_dir() and "MUTANT_UNDER_TEST" in os.environ:
        pytest.skip("the clause specs are outside the copy the mutation step runs (B-444); expires 2026-12-31")
    for c in _column_checks():
        assert c.meta.spec == f"aci318_14/{c.meta.check_id}.md"
        assert (_CLAUSES / c.meta.spec).is_file(), c.meta.spec


def _cited(names: tuple[str, ...]) -> list[Cited]:
    found: list[Cited] = []
    for name in names:
        module = importlib.import_module(f"aci318_14.{name}")
        for value in vars(module).values():
            if isinstance(value, Cited):
                found.append(value)
            elif isinstance(value, Mapping):
                found.extend(v for v in value.values() if isinstance(v, Cited))
    return found


def test_lint_scope_and_citations() -> None:
    """No column check reaches outside the pack source; every Cited source has an allowed origin (CK-AC3)."""
    checks = _column_checks()
    assert len(checks) == len(_COLUMN_IDS)
    for c in checks:
        assert lint_scope_violations(c, _MODULES) == (), c.meta.check_id
    cited = _cited(_COLUMN_MODULES)
    assert len(cited) > 10
    assert [x.source for x in cited if not x.source.startswith(_PREFIXES)] == []


def test_all_draft() -> None:
    """Every column check is draft with the shipped approvals file; production mode refuses it (CK-AC5)."""
    registry = Registry.discover()
    subject = Subject(kind=SubjectKind.FRAME, id="C1")
    checks = _column_checks()
    assert len(checks) == len(_COLUMN_IDS)
    for c in checks:
        assert resolve_state(c, registry) == "draft"
        with pytest.raises(CheckNotUsable):
            evaluate(c.meta.check_id, {}, subject=subject, mode="production", registry=registry)


def test_verify_reports_unverified() -> None:
    """Verify exits 0; every column hand check passes, program comparisons are pending, none is verified (CK-AC7)."""
    done = subprocess.run(  # noqa: S603  # B-334: fixed arguments, no shell, no untrusted input
        [sys.executable, "-m", "structural_codes", "verify", "--pack", str(_ROOT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert (done.returncode, done.stderr) == (0, "")
    lines = {line.split(" ", 1)[0]: line for line in done.stdout.splitlines()}
    assert set(_COLUMN_IDS) <= set(lines)
    for check_id in _COLUMN_IDS:
        line = lines[check_id]
        assert " not verified " in line
        assert "fail=0" in line
        assert "no passing worked_example" in line
        assert re.search(r"pass=[1-9]\d*\b", line)
        assert not re.search(r"pending=0\b", line), check_id
