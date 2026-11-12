"""Calc 2, difference report `harness.model_diff` v1 (spec 0003 4.7, rules D1 to D7).

Purpose: report every engineer change between two model state reads with basis tolerances. Units: tolerances follow
§4.4 `compare.*` fields; display floats are only where the payload names them. Errors: `INVALID_ARGUMENT` for a basis
field that is missing, unconfirmed, wrongly unitled or negative.
"""

from __future__ import annotations

from collections.abc import Iterator
from fractions import Fraction
from typing import Any, Self, cast

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import DesignBasis
from eng_contract.kinds.model import (
    AreaPlacements,
    FramePlacements,
    GridSystem,
    JointRestraints,
    LoadSet,
    Materials,
    Sections,
    Stories,
)
from eng_contract.params import eng_param
from eng_contract.units import kind_for_field
from pydantic import JsonValue, model_validator

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder, calc
from eng_harness.calcs._compare import as_fraction, within_tolerance
from eng_harness.calcs._state import ORDER, SECTIONS, canonical_state, list_at, row_key
from eng_harness.kinds.calcs import Change, DiffBody, PropertyRow, SectionCounts, Side, Tolerance, WithinRow

__all__ = ["DiffInput", "model_diff"]

_BASIS: tuple[tuple[str, str, str], ...] = (
    ("compare.length", "length", "mm"),
    ("compare.angle", "angle", "deg"),
    ("compare.stress", "stress", "MPa"),
    ("compare.unit_weight", "unit_weight", "kN/m3"),
    ("compare.line_load", "line_load", "kN/m"),
    ("compare.area_load", "area_load", "kPa"),
    ("compare.ratio", "dimensionless", "1"),
)
_SIDE = ("before", "after")


def _zero() -> int:
    return len(())


def _one() -> int:
    return len((False,))


class DiffInput(CalcInput):
    """Two read-set groups (`before_*`, `after_*`) and the design basis (`basis`). At least one section on each side."""

    before_stories: Stories | None = eng_param(
        None, ref_capable=True, ref_kinds={"model.stories/1"}, engineering_quantity=True, stale_ok=True
    )
    before_grids: GridSystem | None = eng_param(
        None, ref_capable=True, ref_kinds={"model.grid_system/1"}, engineering_quantity=True, stale_ok=True
    )
    before_frames: FramePlacements | None = eng_param(
        None, ref_capable=True, ref_kinds={"model.frame_placements/1"}, engineering_quantity=True, stale_ok=True
    )
    before_areas: AreaPlacements | None = eng_param(
        None, ref_capable=True, ref_kinds={"model.area_placements/1"}, engineering_quantity=True, stale_ok=True
    )
    before_sections: Sections | None = eng_param(
        None, ref_capable=True, ref_kinds={"model.sections/1"}, engineering_quantity=True, stale_ok=True
    )
    before_materials: Materials | None = eng_param(
        None, ref_capable=True, ref_kinds={"model.materials/1"}, engineering_quantity=True, stale_ok=True
    )
    before_loads: LoadSet | None = eng_param(
        None, ref_capable=True, ref_kinds={"model.load_set/1"}, engineering_quantity=True, stale_ok=True
    )
    before_restraints: JointRestraints | None = eng_param(
        None, ref_capable=True, ref_kinds={"model.joint_restraints/1"}, engineering_quantity=True, stale_ok=True
    )
    after_stories: Stories | None = eng_param(
        None, ref_capable=True, ref_kinds={"model.stories/1"}, engineering_quantity=True
    )
    after_grids: GridSystem | None = eng_param(
        None, ref_capable=True, ref_kinds={"model.grid_system/1"}, engineering_quantity=True
    )
    after_frames: FramePlacements | None = eng_param(
        None, ref_capable=True, ref_kinds={"model.frame_placements/1"}, engineering_quantity=True
    )
    after_areas: AreaPlacements | None = eng_param(
        None, ref_capable=True, ref_kinds={"model.area_placements/1"}, engineering_quantity=True
    )
    after_sections: Sections | None = eng_param(
        None, ref_capable=True, ref_kinds={"model.sections/1"}, engineering_quantity=True
    )
    after_materials: Materials | None = eng_param(
        None, ref_capable=True, ref_kinds={"model.materials/1"}, engineering_quantity=True
    )
    after_loads: LoadSet | None = eng_param(
        None, ref_capable=True, ref_kinds={"model.load_set/1"}, engineering_quantity=True
    )
    after_restraints: JointRestraints | None = eng_param(
        None, ref_capable=True, ref_kinds={"model.joint_restraints/1"}, engineering_quantity=True
    )
    basis: DesignBasis = eng_param(ref_capable=True, ref_kinds={"basis.design_basis/1"})

    @model_validator(mode="before")
    @classmethod
    def _flatten_nested(cls, data: Any) -> Any:
        if not isinstance(data, dict) or "before" not in data:
            return data
        flat = dict(data)
        for side in _SIDE:
            group = flat.pop(side, None)
            if isinstance(group, dict):
                for name, value in group.items():
                    flat[f"{side}_{name}"] = value
        return flat

    @model_validator(mode="after")
    def _one_each_side(self) -> Self:
        if not any(getattr(self, f"before_{n}") is not None for n, _ in SECTIONS):
            raise ValueError("at least one before section must be set")
        if not any(getattr(self, f"after_{n}") is not None for n, _ in SECTIONS):
            raise ValueError("at least one after section must be set")
        return self


def _read_basis(basis: DesignBasis, meta: InputMeta, trace: TraceBuilder) -> dict[str, tuple[Fraction, Tolerance]]:
    tolerances: dict[str, tuple[Fraction, Tolerance]] = {}
    ref = meta.refs.get("basis")
    if ref is None:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "basis must be a record reference", field="basis")
    for path, kind, unit in _BASIS:
        if path not in basis.fields:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, f"missing basis field {path}", field=f"basis.{path}")
        field = basis.fields[path]
        if field.unit != unit:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT, f"wrong unit on {path}", field=f"basis.{path}", expected={"unit": unit}
            )
        if not field.confirmed:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, f"{path} is not confirmed", field=f"basis.{path}")
        number = as_fraction(field.value)
        if number is None or number < _zero():
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT, f"{path} must be a non-negative number", field=f"basis.{path}"
            )
        tolerances[kind] = (
            number,
            Tolerance(value=float(number), unit=unit, ref=f"{ref.result_id}#/fields/{path}"),
        )
        trace.input(path.replace(".", "_"), float(number), unit=unit, ref=f"{ref.result_id}#/fields/{path}")
    return tolerances


def _walk_leaves(before: Any, after: Any, pointer: str) -> Iterator[tuple[str, Any, Any]]:
    if isinstance(before, dict) and isinstance(after, dict):
        keys = sorted(set(before) | set(after), key=lambda k: k.encode("utf-16-be", "surrogatepass"))
        for key in keys:
            yield from _walk_leaves(before.get(key), after.get(key), f"{pointer}/{key}")
        return
    if isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            yield pointer, before, after
            return
        for index, (left, right) in enumerate(zip(before, after, strict=True)):
            yield from _walk_leaves(left, right, f"{pointer}/{index}")
        return
    yield pointer, before, after


def _quantity_kind(pointer: str) -> tuple[str | None, str | None]:
    leaf = pointer.rsplit("/", len((False,)))[-1]
    found = kind_for_field(leaf)
    if found is None:
        return None, None
    return found.name, found.canonical_unit


def _diff_object(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    tolerances: dict[str, tuple[Fraction, Tolerance]],
) -> tuple[list[PropertyRow], list[PropertyRow]]:
    props: list[PropertyRow] = []
    near: list[PropertyRow] = []
    for pointer, left, right in _walk_leaves(before, after, ""):
        if left == right:
            continue
        kind, unit = _quantity_kind(pointer)
        tol_pair = tolerances.get(kind) if kind else None
        tol_value = float(tol_pair[0]) if tol_pair else None
        if kind and tol_pair and as_fraction(left) is not None and as_fraction(right) is not None:
            if within_tolerance(left, right, tol_pair[0]):
                near.append(
                    PropertyRow(
                        pointer=pointer,
                        before=left,
                        after=right,
                        unit=unit,
                        quantity_kind=kind,
                        tolerance=tol_value,
                        rule="D3",
                    )
                )
                continue
            props.append(
                PropertyRow(
                    pointer=pointer,
                    before=left,
                    after=right,
                    unit=unit,
                    quantity_kind=kind,
                    tolerance=tol_value,
                    rule="D3",
                )
            )
            continue
        props.append(
            PropertyRow(
                pointer=pointer, before=left, after=right, unit=unit, quantity_kind=kind, tolerance=None, rule="D4"
            )
        )
    return props, near


def _tally() -> dict[str, int]:
    z = _zero()
    return {"added": z, "removed": z, "changed": z, "ambiguous": z, "unchanged": z, "within_tolerance": z}


def _bump(tally: dict[str, int], key: str) -> None:
    tally[key] = tally[key] + _one()


def _index_rows(
    rows: list[dict[str, Any]], list_name: str, key: str | None
) -> dict[tuple[str, ...], list[dict[str, Any]]]:
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(row_key(list_name, key, row), []).append(row)
    return groups


def _compare_list(
    section: str,
    list_name: str,
    path: tuple[str, ...],
    key: str | None,
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    tolerances: dict[str, tuple[Fraction, Tolerance]],
) -> tuple[list[Change], list[WithinRow], dict[str, int]]:
    rows_b = list_at(before, path)
    rows_a = list_at(after, path)
    index_b = _index_rows(rows_b, list_name, key)
    index_a = _index_rows(rows_a, list_name, key)
    changes: list[Change] = []
    within: list[WithinRow] = []
    tally = _tally()
    keys = sorted(set(index_b) | set(index_a), key=lambda k: (len(k), k))
    for object_key in keys:
        left, right = index_b.get(object_key, []), index_a.get(object_key, [])
        if len(left) > len((False,)) or len(right) > len((False,)):
            if left == right:
                _bump(tally, "unchanged")
                continue
            changes.append(
                Change(
                    section=section,
                    key=list(object_key),
                    change="ambiguous",
                    before=cast(JsonValue, left if left else None),
                    after=cast(JsonValue, right if right else None),
                    properties=[],
                )
            )
            _bump(tally, "ambiguous")
            continue
        if not left:
            changes.append(
                Change(
                    section=section, key=list(object_key), change="added", before=None, after=right[0], properties=[]
                )
            )
            _bump(tally, "added")
            continue
        if not right:
            changes.append(
                Change(
                    section=section, key=list(object_key), change="removed", before=left[0], after=None, properties=[]
                )
            )
            _bump(tally, "removed")
            continue
        if left[0] == right[0]:
            _bump(tally, "unchanged")
            continue
        props, near = _diff_object(left[0], right[0], tolerances=tolerances)
        for row in near:
            within.append(
                WithinRow(
                    section=section,
                    key=list(object_key),
                    pointer=row.pointer,
                    before=row.before,
                    after=row.after,
                    unit=row.unit,
                    quantity_kind=row.quantity_kind,
                    tolerance=row.tolerance,
                    rule=row.rule,
                )
            )
            _bump(tally, "within_tolerance")
        if props:
            changes.append(
                Change(
                    section=section,
                    key=list(object_key),
                    change="changed",
                    before=None,
                    after=None,
                    properties=props,
                )
            )
            _bump(tally, "changed")
        elif near:
            _bump(tally, "unchanged")
    return changes, within, tally


def _side_meta(inp: DiffInput, meta: InputMeta, prefix: str) -> tuple[Side, bool]:
    covered: list[str] = []
    complete = True
    model_id: str | None = None
    revision: int | None = None
    for name, kind in SECTIONS:
        if getattr(inp, f"{prefix}_{name}") is None:
            continue
        covered.append(kind)
        ref = meta.refs.get(f"{prefix}_{name}")
        if ref is None:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT, "a section must be a record reference", field=f"{prefix}_{name}"
            )
        complete = complete and ref.complete
        if ref.model_id is None or ref.model_revision is None:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "the record names no host model", field=f"{prefix}_{name}")
        identity = (ref.model_id, ref.model_revision)
        if model_id is None:
            model_id, revision = identity
        elif identity != (model_id, revision):
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT,
                "the records belong to different models or revisions",
                field=f"{prefix}_{name}",
            )
    if model_id is None or revision is None:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "at least one section must be set")
    return Side(model_id=model_id, model_revision=revision, covered=sorted(covered)), complete


@calc(
    id="harness.model_diff",
    version=1,
    output_kind="harness.model_diff/1",
    title="Difference report between two model states",
    method_source="eng-harness spec 0003 §4.7 (D1 to D7); 18 §4 step 4",
    verification="draft",
)
def model_diff(inp: DiffInput, meta: InputMeta, trace: TraceBuilder) -> DiffBody:
    """Compare each shared section (D1 to D5) and build the report (D6, D7)."""
    tol_pairs = _read_basis(inp.basis, meta, trace)
    tolerances = {kind: pair[1] for kind, pair in tol_pairs.items()}
    before_side, before_complete = _side_meta(inp, meta, "before")
    after_side, after_complete = _side_meta(inp, meta, "after")
    all_changes: list[Change] = []
    all_within: list[WithinRow] = []
    not_compared: list[str] = []
    counts: dict[str, SectionCounts] = {}
    for name, kind in SECTIONS:
        before_payload = getattr(inp, f"before_{name}")
        after_payload = getattr(inp, f"after_{name}")
        if before_payload is None or after_payload is None:
            if before_payload is not None or after_payload is not None:
                not_compared.append(kind)
            continue
        before_norm = canonical_state(kind, before_payload.model_dump(mode="json", by_alias=True, exclude_none=False))
        after_norm = canonical_state(kind, after_payload.model_dump(mode="json", by_alias=True, exclude_none=False))
        section_tally = _tally()
        for kind_name, path, key in ORDER:
            if kind_name != kind:
                continue
            list_name = path[-1]
            changes, within, tally = _compare_list(
                kind, list_name, path, key, before_norm, after_norm, tolerances=tol_pairs
            )
            all_changes.extend(changes)
            all_within.extend(within)
            for key_name, value in tally.items():
                section_tally[key_name] += value
        counts[kind] = SectionCounts(
            added=section_tally["added"],
            removed=section_tally["removed"],
            changed=section_tally["changed"],
            ambiguous=section_tally["ambiguous"],
            unchanged=section_tally["unchanged"],
            within_tolerance=section_tally["within_tolerance"],
        )
        trace.step(
            f"{name}_counts",
            section_tally["changed"],
            formula="per-list tallies of D2 to D5",
            source="§4.7 D1 to D5",
            uses=[path.replace(".", "_") for path, _, _ in _BASIS],
        )
    ambiguous = any(change.change == "ambiguous" for change in all_changes)
    complete = before_complete and after_complete and not not_compared and not ambiguous
    identical = complete and not all_changes and not not_compared
    return DiffBody(
        before=before_side,
        after=after_side,
        tolerances=tolerances,
        changes=sorted(all_changes, key=lambda row: (row.section, tuple(row.key))),
        within_tolerance=sorted(all_within, key=lambda row: (row.section, tuple(row.key), row.pointer)),
        not_compared=sorted(not_compared),
        counts=counts,
        identical=identical,
        complete=complete,
    )
