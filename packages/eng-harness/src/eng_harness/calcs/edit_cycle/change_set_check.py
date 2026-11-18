"""Calc `harness.change_set_check` v1: the change set against the model and the basis (spec 0007 4.4.1, K1 to K7).

Purpose: resolve each item's selection to sorted explicit names (K1), check every name (K2), refuse two items on one
target and property and an item id that is not a page token (K3), check each value's source, unit and bounds (K4), name
the gap of a refused kind (K5), warn where the engineer changed a property an item also sets (K6), and fail on any
error (K7).
Inputs: `change_set` (the answer field), the step 3 read set as flat fields (`frames`, `areas`, `sections`,
`restraints`), `names` (`harness.csi_name_lists/1`), `diff` (the step 4 `harness.model_diff/1`) and `basis`.
Units: a value is compared exactly in the canonical unit of its quantity kind (the unit of its bounds), converted by
`eng_contract.units`; the bounds are the `bounds.*` fields of spec 0007 4.8. Resolved values hold references only, each
pointing at the number: `.../value` of a basis field, `.../value_<suffix>` of an input (K4), so step 8 passes it as the
engineering argument.
Errors: `ContractError` `INVALID_ARGUMENT` (with `field`) for a bounds field that is missing, unconfirmed or not a
number (no default), or an input given without a record. Every finding about the change set is an issue.
"""

from collections.abc import Sequence
from fractions import Fraction
from typing import Any, Literal

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import DesignBasis
from eng_contract.kinds.model import AreaPlacements, FramePlacements, JointRestraints, Sections
from eng_contract.params import eng_param
from eng_contract.units import kind_for_field, unit
from pydantic import BaseModel, ConfigDict

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder, calc
from eng_harness.calcs._compare import as_fraction
from eng_harness.kinds.calcs import Change, ModelDiff
from eng_harness.kinds.edit_cycle import CsiNameLists, Issue, ResolvedItem, ResolvedValue
from eng_harness.workflows.model_edit_cycle._change_set import ChangeSetDraft, refused_gap

__all__ = ["ANSWER_FIELD", "BASIS_FIELDS", "BOUNDS", "CheckBody", "CheckInput", "change_set_check"]

BOUNDS: tuple[tuple[str, str, str], ...] = (
    ("length", "bounds.thickness_min_mm", "bounds.thickness_max_mm"),
    ("line_load", "bounds.line_load_min_kN_m", "bounds.line_load_max_kN_m"),
    ("area_load", "bounds.area_load_min_kPa", "bounds.area_load_max_kPa"),
    ("dimensionless", "bounds.ratio_min_ratio", "bounds.ratio_max_ratio"),
)
"""Spec 0007 4.8 and K4: the quantity kind of a value and the basis paths of its lower and upper bound."""
_NUMBER = {
    quantity: f"value{kind.suffix}"
    for quantity, low, _ in BOUNDS
    if (kind := kind_for_field(low.rpartition(".")[2])) is not None
}
"""The key under which an input value holds its number in the canonical unit of its quantity kind (spec 0007 4.3.1)."""
BASIS_FIELDS = tuple(path for _, low, high in BOUNDS for path in (low, high))
"""The basis paths this calc reads (`CalcInfo.basis_fields`); the workflow declares them required."""
ANSWER_FIELD = "fields/change_set/value"
"""Where the change set sits in its `basis.engineer_input/1` record (`Answered.field_ref("change_set")`)."""
_FRAMES, _AREAS = "model.frame_placements/1", "model.area_placements/1"
_SECTIONS, _LOADS, _JOINTS = "model.sections/1", "model.load_set/1", "model.joint_restraints/1"
_GRAVITY = "gravity"
_ID_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
_RESERVED_IDS = ("revision", "unlock")
"""K3 (spec 0007 4.4.1): an item id is a page token of spec 0006 AC49 (`[A-Za-z0-9_.-]`, at most 64) less the 7 of the
field prefix `reject_` and `reason_` (1 to 57 characters), and not an id step 6 adds to the preview itself."""
_REFS = ("change_set", "frames", "areas", "sections", "restraints", "names", "diff", "basis")
_VALUES = (
    ("wall_section", "thickness", "length", "/thickness_mm"),
    ("frame_uniform_load", "w", "line_load", "/w_kN_m"),
    ("area_uniform_load", "q", "area_load", "/q_kPa"),
    ("load_pattern_add", "self_weight", "dimensionless", "/self_weight_ratio"),
)
"""The kinds that have a value field: kind, field name, quantity kind and the property pointer it sets."""

Claim = tuple[str, tuple[str, ...], str, str]
"""Section, reported key (spec 0003 4.7 D2, list name first), property pointer and the value the item sets."""
Bounds = dict[str, tuple[Fraction, Fraction, str]]
"""Per quantity kind: exact lower and upper bound and their (canonical) unit."""


def _is_page_token(text: str) -> bool:
    return 0 < len(text) <= 57 and all(char in _ID_CHARS for char in text)  # K3: 64 less the 7 of the prefix


def _ref(kind: str, default: Any = ...) -> Any:
    return eng_param(default, ref_capable=True, ref_kinds={kind}, engineering_quantity=True)


class CheckInput(CalcInput):
    """The change set, the step 3 read set, the name lists, the step 4 difference report and the basis."""

    change_set: ChangeSetDraft = _ref("basis.engineer_input/1")
    frames: FramePlacements = _ref(_FRAMES)
    areas: AreaPlacements = _ref(_AREAS)
    sections: Sections | None = _ref(_SECTIONS, None)
    restraints: JointRestraints = _ref(_JOINTS)
    names: CsiNameLists = _ref("harness.csi_name_lists/1")
    diff: ModelDiff = _ref("harness.model_diff/1")
    basis: DesignBasis = _ref("basis.design_basis/1")


class CheckBody(BaseModel):
    """The payload of `harness.change_set_check/1` without `calc`, `draft` and `trace`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["PASS", "FAIL"]
    resolved: list[ResolvedItem]
    issues: list[Issue]
    complete: bool


def _refuse(path: str, why: str) -> ContractError:
    message = f"basis field {path} {why}"
    return ContractError(ErrorCode.INVALID_ARGUMENT, message, field=f"basis.fields.{path}", hint=f"confirm {path}")


def read_bounds(basis: DesignBasis, basis_id: str, trace: TraceBuilder) -> Bounds:
    """K4: the exact bounds of each quantity kind; each field present, confirmed and a number (no default)."""
    bounds: Bounds = {}
    for kind, low, high in BOUNDS:
        exact: list[Fraction] = []
        for path in (low, high):
            field = basis.fields.get(path)
            if field is None or not field.confirmed:
                raise _refuse(path, "is missing or not confirmed (no default)")
            if (value := as_fraction(field.value)) is None:
                raise _refuse(path, "is not a number")
            exact.append(value)
            trace.input(path.replace(".", "_"), float(value), unit=field.unit, ref=f"{basis_id}#/fields/{path}")
        bounds[kind] = (exact[0], exact[1], str(basis.fields[low].unit))
    return bounds


class _Check:
    """The lookups of one run and the issues and claimed properties found so far, in item order."""

    def __init__(self, inp: CheckInput, refs: dict[str, str], bounds: Bounds) -> None:
        self.inp, self.refs, self.bounds = inp, refs, bounds
        self.issues: list[Issue] = []
        self.claims: dict[tuple[str, tuple[str, ...], str], str] = {}
        self.added: dict[str, set[str]] = {"section": set(), "pattern": set(), "combination": set()}
        frames, areas, names = inp.frames.frames, inp.areas.areas, inp.names
        self.known = {
            "frame": {f.id for f in frames},
            "area": {a.id for a in areas},
            "joint": {r.joint for r in inp.restraints.joints}
            | {j for f in frames for j in (f.i_joint, f.j_joint) if j is not None}
            | {j for a in areas for j in a.joints or ()},
            "frame_section": set(names.frame_sections),
            "section": set(names.area_sections),
            "material": set(names.materials),
            "pattern": set(names.patterns),
            "combination": set(names.combinations),
        }

    def issue(self, item: str, code: str, detail: str, *, gap: str | None = None, warn: bool = False) -> None:
        severity: Literal["error", "warning"] = "warning" if warn else "error"
        self.issues.append(Issue(item_id=item, severity=severity, code=code, detail=detail, gap=gap))

    def name(self, item: str, what: str, value: str) -> None:
        """K2: `value` is in the model state or name lists, or an earlier item of the set adds it."""
        if value not in self.known[what] and value not in self.added.get(what, ()):
            code = "SECTION" if what == "frame_section" else what.upper()
            self.issue(item, f"UNKNOWN_{code}", f"{what.replace('_', ' ')} {value} is not in the model")

    def targets(self, item: Any, what: str) -> list[str]:
        """K1 and K2: explicit names (each must exist) or the members of a selection (an empty one is an error)."""
        if (given := getattr(item, f"{what}s")) is not None:
            for value in given:
                self.name(item.id, what, value)
            return sorted(set(given))
        rows: Sequence[Any] = self.inp.frames.frames if what == "frame" else self.inp.areas.areas
        sections = self.inp.sections  # optional (spec 0007 4.4.1): no record, no area kind is known
        kinds = {} if sections is None else {s.name: s.kind.value for s in sections.area_sections}
        sel = item.select
        found = sorted(
            row.id
            for row in rows
            if sel.story in (None, row.story)
            and sel.section in (None, row.section)
            and getattr(sel, "area_kind", None) in (None, kinds.get(row.section))
        )
        if not found:
            unread = (
                ": the area kinds were not read (no model.sections/1)"
                if getattr(sel, "area_kind", None) and sections is None
                else ""
            )
            self.issue(item.id, "EMPTY_SELECTION", f"the selection of item {item.id} matches no {what}{unread}")
        return found

    def value(self, index: int, field: str, value: Any, quantity: str, pointer: str) -> tuple[ResolvedValue, str]:
        """K4: the value's source, unit and bounds; the resolved value holds the reference, never the number."""
        item = self.inp.change_set.items[index].id
        low, high, canonical = self.bounds[quantity]
        exact: Fraction | None
        if value.source == "basis":
            path, shown = value.path, f"basis {value.path}"
            ref, stored = f"{self.refs['basis']}#/fields/{path}/value", self.inp.basis.fields.get(path)
            kind = kind_for_field(path.rpartition(".")[2])
            exact = as_fraction(stored.value) if stored is not None and stored.confirmed else None
            if exact is None:
                self.issue(item, "SOURCE_MISSING", f"basis field {path} is absent, unconfirmed or not a number")
            elif kind is None or kind.name != quantity:
                self.issue(item, "UNIT_MISMATCH", f"the unit of basis field {path} is not of kind {quantity}")
                exact = None
        else:
            shown, ref = (
                f"{value.value} {value.unit}",
                f"{self.refs['change_set']}#/{ANSWER_FIELD}/items/{index}/{field}/{_NUMBER[quantity]}",
            )
            exact = Fraction(value.value) * unit(value.unit).factor / unit(canonical).factor  # no offset, no pi
        if exact is not None and not low <= exact <= high:
            bounds = f"[{float(low)}, {float(high)}] {canonical}"
            detail = f"{field} {float(exact)} {canonical} is outside {bounds} (spec 0007 4.8)"
            self.issue(item, "OUT_OF_BOUNDS", detail)
        return ResolvedValue(pointer=pointer, ref=ref, unit=canonical), shown


def _item(check: _Check, index: int, item: Any) -> tuple[ResolvedItem, list[Claim]]:
    """K1, K2 and K4 for one accepted item: its targets, values and the properties it sets."""
    kind, values, shown = item.kind, [], ""
    for _, field, quantity, pointer in (row for row in _VALUES if row[0] == kind):
        resolved, shown = check.value(index, field, getattr(item, field), quantity, pointer)
        values.append(resolved)
    what = "frame" if kind.startswith("frame") else "area"
    claims: list[Claim]
    if kind in ("frame_section", "area_section"):
        targets = check.targets(item, what)
        check.name(item.id, "frame_section" if what == "frame" else "section", item.section)
        claims = [(_FRAMES if what == "frame" else _AREAS, (f"{what}s", t), "/section", item.section) for t in targets]
    elif kind in ("frame_uniform_load", "area_uniform_load"):
        targets = check.targets(item, what)
        check.name(item.id, "pattern", item.pattern)
        claims = [(_LOADS, (f"{what}_loads", t, item.pattern, _GRAVITY), values[0].pointer, shown) for t in targets]
    elif kind == "joint_restraints":
        targets = sorted(set(item.joints))
        for joint in targets:
            check.name(item.id, "joint", joint)
        claims = [(_JOINTS, ("joints", t), "", "restraints") for t in targets]
    else:
        targets = [item.name]
        claims = _named(check, index, item, values, shown)
    return ResolvedItem(item_id=item.id, kind=kind, targets=targets, values=values), claims


def _named(check: _Check, index: int, item: Any, values: list[ResolvedValue], shown: str) -> list[Claim]:
    """K2 and K4 for the kinds that name one object: wall section, load pattern, combination set or delete."""
    kind, name = item.kind, item.name
    if kind == "wall_section":
        check.name(item.id, "material", item.material)
        check.added["section"].add(name)
        return [(_SECTIONS, ("area_sections", name), "/thickness_mm", shown)]
    if kind == "load_pattern_add":
        check.added["pattern"].add(name)
        return [(_LOADS, ("patterns", name), "", f"a new pattern, self weight {shown}")]
    if kind == "load_combination_delete":
        check.name(item.id, "combination", name)
        return [(_LOADS, ("combinations", name), "", "its deletion")]
    for number, term in enumerate(item.items):
        if term.case.case_type != "load_case":  # no load-case name list exists (verification record)
            check.name(item.id, term.case.case_type.removeprefix("load_"), term.case.case)
        scale = f"/items/{number}/scale_ratio"
        values.append(check.value(index, f"items/{number}/scale", term.scale, "dimensionless", scale)[0])
    check.added["combination"].add(name)
    return [(_LOADS, ("combinations", name), "", "a new definition")]


def _conflicts(
    check: _Check, item: str, claim: Claim, changes: dict[tuple[str, tuple[str, ...]], list[Change]]
) -> None:
    """K6: a change of the step 4 report on the claimed object and property is a warning with both values.

    A whole-object claim (pointer "") also covers the rows nested in that object (spec 0003 D2 keys them under it).
    """
    section, key, pointer, shown = claim
    whole = pointer == ""
    found = [
        change
        for (where, at), listed in changes.items()
        if where == section and (at == key or (whole and at[: len(key)] == key))
        for change in listed
    ]
    for change in found:
        name = "/".join(change.key)
        rows = [r for r in change.properties if pointer in ("", r.pointer) or r.pointer.startswith(pointer + "/")]
        if change.change != "changed":
            engineer = f"{change.change} {name}"
        elif rows:
            engineer = "changed " + "; ".join(f"{name}{r.pointer} from {r.before} to {r.after}" for r in rows)
        else:
            continue
        check.issue(item, "CONFLICTS_WITH_ENGINEER_CHANGE", f"the engineer {engineer}; item sets {shown}", warn=True)


@calc(
    id="harness.change_set_check",
    version=1,
    output_kind="harness.change_set_check/1",
    title="Change-set check against the model state, the names and the basis bounds",
    method_source="eng-harness spec 0007 §4.4.1 (K1 to K7); 18 §4 step 5",
    verification="draft",
)
def change_set_check(inp: CheckInput, meta: InputMeta, trace: TraceBuilder) -> CheckBody:
    """Check every item of the change set (K1 to K6) and give the status (K7)."""
    refs: dict[str, str] = {}
    for name in _REFS:
        if name == "sections" and inp.sections is None:  # optional (spec 0007 4.4.1)
            continue
        if (ref := meta.refs.get(name)) is None:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "each input must be a record reference", field=name)
        refs[name] = ref.result_id
    check = _Check(inp, refs, read_bounds(inp.basis, refs["basis"], trace))
    items = inp.change_set.items
    trace.input("items", len(items), ref=f"{refs['change_set']}#/{ANSWER_FIELD}")
    changes: dict[tuple[str, tuple[str, ...]], list[Change]] = {}
    for change in inp.diff.changes:
        changes.setdefault((change.section, tuple(change.key)), []).append(change)
    resolved: list[ResolvedItem] = []
    for index, item in enumerate(items):
        if "/" in item.id:  # K3: effect ids join the item id with `/` (spec 0007 4.4.2)
            check.issue(item.id, "INVALID_ITEM_ID", f"item id {item.id} contains / (spec 0007 4.4.1 K3)")
        elif not _is_page_token(item.id) or item.id in _RESERVED_IDS:  # K3: the change-set screen's field names
            check.issue(
                item.id,
                "INVALID_ITEM_ID",
                f"item id {item.id} is not 1 to 57 ASCII letters, digits, _, . or -, or is revision or unlock"
                " (spec 0007 4.4.1 K3)",
            )
        if (gap := refused_gap(item)) is not None:  # K5
            check.issue(item.id, "NOT_IMPLEMENTED", f"{item.kind} is refused in v1 (spec 0007 4.3.2)", gap=gap)
            continue
        done, claims = _item(check, index, item)
        resolved.append(done)
        for claim in claims:
            section, key, pointer, _ = claim
            if (first := check.claims.setdefault((section, key, pointer), item.id)) != item.id:  # K3
                where = "/".join(key) + pointer
                check.issue(item.id, "DUPLICATE_TARGET", f"{where} is also set by item {first}")
            _conflicts(check, item.id, claim, changes)
    errors = sum(issue.severity == "error" for issue in check.issues)
    uses = ["items", *(path.replace(".", "_") for path in BASIS_FIELDS)]
    trace.step("errors", errors, formula="error issues of K1 to K5", source="spec 0007 4.4.1 K1 to K5", uses=uses)
    warnings = len(check.issues) - errors
    trace.step("warnings", warnings, formula="warning issues of K6", source="spec 0007 4.4.1 K6", uses=["items"])
    status: Literal["PASS", "FAIL"] = "FAIL" if errors else "PASS"
    trace.step(
        "status", status, formula="FAIL when errors > 0, else PASS", source="spec 0007 4.4.1 K7", uses=["errors"]
    )
    trace.output("status")
    complete = all(meta.refs[name].complete for name in refs) and inp.diff.complete
    return CheckBody(status=status, resolved=resolved, issues=check.issues, complete=complete)
