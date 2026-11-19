"""Clause-map parity and definition errors (spec 0003 AC1 and AC2, clause map §§2 and 3)."""

import os
import re
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any

import pytest
from aci318_14 import PACK
from structural_codes.errors import CheckDefinitionError
from structural_codes.overlay import Overridden

from sbc304_2018._overlay import MapRow, MapStatus, build_overlay
from sbc304_2018.clause_map import CLAUSE_MAP

_DOC = Path(__file__).parents[3] / "docs" / "clauses" / "sbc304_2018" / "clause-map.md"
_SYNTHETIC = "synthetic test fixture, no engineering meaning"


def test_rows_match_clause_map_doc() -> None:
    known = {check.meta.check_id for check in PACK.checks}
    assert isinstance(CLAUSE_MAP, tuple)
    assert {row.base_check_id for row in CLAUSE_MAP} == known
    assert all(row.status is MapStatus.UNCONFIRMED for row in CLAUSE_MAP)
    assert all(row.sbc_clause is None and row.sbc_source is None for row in CLAUSE_MAP)
    row: Any = CLAUSE_MAP[0]
    with pytest.raises(FrozenInstanceError):
        row.confirm = _SYNTHETIC  # write attempt must fail for a frozen row

    if not _DOC.is_file() and "MUTANT_UNDER_TEST" in os.environ:
        pytest.skip("the clause map document is outside the mutation member copy")
    table = (
        _DOC.read_text(encoding="utf-8")
        .split("<!-- clause-map-rows:start -->")[1]
        .split("<!-- clause-map-rows:end -->")[0]
    )
    expected = []
    for line in table.strip().splitlines()[2:]:
        gap, base, status, clauses, confirm = (cell.strip() for cell in line.strip("|").split("|"))
        if base.strip("`") in known:
            expected.append(
                MapRow(base.strip("`"), MapStatus(status), None, None, gap, tuple(clauses.split(", ")), confirm)
            )
    assert tuple(expected) == CLAUSE_MAP


def test_column_rows_explicit() -> None:
    """ACI plan 0004 T5 is already merged, so plan 0003 §1 folds these rows into T2."""
    columns = {
        "aci318_14.22_4_2_1.max_axial_strength": "G-7",
        "aci318_14.22_4_1_1.axial_flexure_uniaxial": "G-8",
        "aci318_14.10_6_1_1.longitudinal_reinforcement_limits": "G-9",
    }
    checks, overlay = build_overlay(CLAUSE_MAP, PACK)
    assert len(checks) == len(overlay.entries) == len(PACK.checks)
    for entry in overlay.entries:
        assert isinstance(entry, Overridden)
        (gap,) = entry.check.meta.gaps
        assert gap.id != "G-0"
        if entry.base_check_id in columns:
            assert gap.id == columns[entry.base_check_id]


_INVALID_INHERITED_ROWS: list[tuple[dict[str, str | None], str]] = [
    ({"sbc_clause": ""}, "inherited rows require sbc_clause and sbc_source"),
    ({"sbc_source": None}, "inherited rows require sbc_clause and sbc_source"),
    ({"gap_id": ""}, "inherited rows cannot declare gap_id"),
    ({"gap_id": "G-1"}, "inherited rows cannot declare gap_id"),
    ({"confirm": ""}, "confirm must be non-empty"),
]


_INVALID_ROWS: list[tuple[dict[str, Any], str]] = [
    *[
        ({"status": status}, "status must be inherited or unconfirmed")
        for status in ("inherited-confirmed", "confirmed", "overridden", "added", "removed", "")
    ],
    ({"sbc_clause": ""}, "unconfirmed rows cannot declare sbc_clause or sbc_source"),
    ({"sbc_clause": "Synthetic"}, "unconfirmed rows cannot declare sbc_clause or sbc_source"),
    ({"sbc_source": ""}, "unconfirmed rows cannot declare sbc_clause or sbc_source"),
    ({"sbc_source": _SYNTHETIC}, "unconfirmed rows cannot declare sbc_clause or sbc_source"),
    *[
        ({"gap_id": gap}, "unconfirmed gap_id must match ^G-[1-9][0-9]*$")
        for gap in (None, "", "G-0", "G-01", "G-1\n", "G-\u0661", "G-x")
    ],
    ({"confirm": ""}, "confirm must be non-empty"),
    ({"base_clauses": ()}, "base_clauses must contain non-empty clauses"),
    ({"base_clauses": ("13.3.1.1", "")}, "base_clauses must contain non-empty clauses"),
    ({"base_clauses": ("Synthetic",)}, "base_clauses must start with '13.3.1.1'"),
    ({"base_check_id": "aci318_14.synthetic.absent"}, "base check is absent from the base pack"),
    *[
        (
            {
                "status": "inherited",
                "sbc_clause": "Synthetic",
                "sbc_source": _SYNTHETIC,
                "gap_id": None,
                **bad_field,
            },
            problem,
        )
        for bad_field, problem in _INVALID_INHERITED_ROWS
    ],
]


def test_row_rules() -> None:
    first, second, *_ = CLAUSE_MAP
    for updates, problem in _INVALID_ROWS:
        row = replace(first, **updates)
        with pytest.raises(CheckDefinitionError, match=re.escape(f"{row.base_check_id}: {problem}") + "$"):
            build_overlay((row,), PACK)

    for duplicate in ("base_check_id", "gap_id"):
        value = getattr(first, duplicate)
        row = replace(second, **{duplicate: value})
        if duplicate == "base_check_id":
            row = replace(row, base_clauses=first.base_clauses)
        problem = f"duplicate {duplicate} {value!r}"
        with pytest.raises(CheckDefinitionError, match=re.escape(f"{row.base_check_id}: {problem}") + "$"):
            build_overlay((first, row), PACK)
