"""SBC overlay tests through the core registry and evaluator (spec 0003 AC3, AC8 and AC10)."""

from dataclasses import replace

import pytest
from eng_contract.verdicts import Subject, SubjectKind, VerdictStatus
from structural_codes import evaluate
from structural_codes.check import Check
from structural_codes.content_hash import content_hash
from structural_codes.errors import CheckNotUsable
from structural_codes.meta import CheckMeta
from structural_codes.overlay import Inherited, InheritedCheck, Overlay, Overridden
from structural_codes.pack import Pack, Registry

from sbc304_2018._overlay import MapRow, MapStatus, build_overlay
from sbc304_2018.clause_map import CLAUSE_MAP

_BASE_PACK = next(pack for pack in Registry.discover().packs if pack.name == "aci318_14")

_COLUMN_ID = "aci318_14.10_6_1_1.longitudinal_reinforcement_limits"
_PROVISIONAL_ID = "sbc304_2018.unconfirmed_aci_318_14_10_6_1_1.longitudinal_reinforcement_limits"
_PROVISIONAL_CLAUSE = "unconfirmed (ACI 318-14 10.6.1.1)"
_COLUMN = Subject(kind=SubjectKind.FRAME, id="C1")
# ACI longitudinal reinforcement limits clause spec §8, HC-1.
_INPUTS = {"Ag_mm2": 250000, "Ast_mm2": 4000}
_SYNTHETIC_CLAUSE = "Synthetic fixture"
_SYNTHETIC_SOURCE = "synthetic test fixture, no engineering meaning"


def _column_row() -> MapRow:
    return next(row for row in CLAUSE_MAP if row.base_check_id == _COLUMN_ID)


def _registry(checks: tuple[Check, ...], overlay: Overlay, base: Pack = _BASE_PACK) -> Registry:
    pack = Pack("sbc304_2018", "SBC 304-2018", "2018", "0.1.0.dev0", checks, "approvals.yaml", base.name, overlay)
    return Registry.of((base, pack))


def _inherited(row: MapRow) -> MapRow:
    return replace(
        row, status=MapStatus.INHERITED, sbc_clause=_SYNTHETIC_CLAUSE, sbc_source=_SYNTHETIC_SOURCE, gap_id=None
    )


def test_missing_row_default() -> None:
    rows = tuple(row for row in CLAUSE_MAP if row.base_check_id != _COLUMN_ID)
    # Simulate two missing rows in one pack. G-0 is reserved per check, so both entries must remain complete.
    checks, overlay = build_overlay(rows[1:], _BASE_PACK)
    registry = _registry(checks, overlay)
    assert overlay.base == "aci318_14"
    assert overlay.clause_map == {
        f"unconfirmed (ACI 318-14 {base.meta.clauses[0]})": base.meta.clauses[0] for base in _BASE_PACK.checks
    }
    assert len(overlay.entries) == len(checks) == len(_BASE_PACK.checks)

    by_base = {}
    for entry in overlay.entries:
        assert isinstance(entry, Overridden)
        by_base[entry.base_check_id] = entry
        expected = next((row.gap_id for row in rows[1:] if row.base_check_id == entry.base_check_id), "G-0")
        (gap,) = entry.check.meta.gaps
        assert gap.id == expected
    assert set(by_base) == {check.meta.check_id for check in _BASE_PACK.checks}

    expected_reason = (
        "SBC_ROW_MISSING: SBC 304-2018 clause not confirmed for "
        f"{_COLUMN_ID} (ACI 318-14 10.6.1.1); to confirm: "
        "add a clause map row for this base check and the common items of clause-map §3"
    )
    result = evaluate(_PROVISIONAL_ID, _INPUTS, subject=_COLUMN, registry=registry)
    (verdict,) = result.payload.verdicts
    (trace,) = result.payload.traces
    assert verdict.status == VerdictStatus.NEEDS_ENGINEER
    assert trace.messages == [f"G-0 ({_PROVISIONAL_CLAUSE}): {expected_reason}"]
    assert trace.steps == []


def test_inherited_row() -> None:
    checks, overlay = build_overlay((_inherited(_column_row()),), _BASE_PACK)
    assert Inherited(_COLUMN_ID, _SYNTHETIC_CLAUSE) in overlay.entries
    assert len(checks) == len(_BASE_PACK.checks) - 1
    assert overlay.clause_map[_SYNTHETIC_CLAUSE] == "10.6.1.1"
    registry = _registry(checks, overlay)
    check_id = "sbc304_2018.synthetic_fixture.longitudinal_reinforcement_limits"
    check = registry.get(check_id)
    assert isinstance(check, InheritedCheck)
    assert check.base is registry.get(_COLUMN_ID)
    result = evaluate(check_id, _INPUTS, subject=_COLUMN, registry=registry)
    assert result.state == "draft"
    assert result.payload.draft is True
    # ACI clause spec §§4 and 8, HC-1: Ast/Ag = 4000/250000 = 0.016, inside [0.01, 0.08].
    assert [(v.status, v.code, v.clause) for v in result.payload.verdicts] == [
        (VerdictStatus.PASS, "SBC 304-2018", _SYNTHETIC_CLAUSE),
        (VerdictStatus.PASS, "SBC 304-2018", _SYNTHETIC_CLAUSE),
    ]
    with pytest.raises(CheckNotUsable, match="not usable"):
        evaluate(check_id, _INPUTS, subject=_COLUMN, mode="production", registry=registry)


def test_row_changes_change_hash() -> None:
    row = _column_row()
    checks, overlay = build_overlay((row,), _BASE_PACK)
    original = _registry(checks, overlay).get(_PROVISIONAL_ID)
    digest = content_hash(original)
    for updated in (replace(row, confirm="Synthetic confirmation text"), replace(row, gap_id="G-10")):
        checks, overlay = build_overlay((updated,), _BASE_PACK)
        check = _registry(checks, overlay).get(_PROVISIONAL_ID)
        assert check.meta.check_id == original.meta.check_id
        assert content_hash(check) != digest

    checks, overlay = build_overlay((_inherited(row),), _BASE_PACK)
    inherited = _registry(checks, overlay).get("sbc304_2018.synthetic_fixture.longitudinal_reinforcement_limits")
    assert content_hash(inherited) != digest

    base_check = Registry.of((_BASE_PACK,)).get(_COLUMN_ID)
    renamed_id = "aci318_14.10_6_1_1.synthetic_reinforcement"
    renamed = replace(base_check, meta=CheckMeta(**(base_check.meta.model_dump() | {"check_id": renamed_id})))
    base = replace(_BASE_PACK, checks=(renamed,))
    checks, overlay = build_overlay((replace(row, base_check_id=renamed_id),), base)
    assert (
        content_hash(
            _registry(checks, overlay, base).get("sbc304_2018.unconfirmed_aci_318_14_10_6_1_1.synthetic_reinforcement")
        )
        != digest
    )
